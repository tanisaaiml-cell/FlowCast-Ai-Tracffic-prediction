"""Analytics queries for dashboard visualizations and alerts."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any

import numpy as np
import pandas as pd

from app.db import SEGMENTS, connection, query_df
from app.services.model_service import model_service


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _range(start: str | None, end: str | None, default_days: int = 7) -> tuple[str, str]:
    now = datetime.now(timezone.utc)
    end_dt = pd.to_datetime(end, utc=True).to_pydatetime() if end else now
    start_dt = pd.to_datetime(start, utc=True).to_pydatetime() if start else end_dt - timedelta(days=default_days)
    return _iso(start_dt), _iso(end_dt)


def overview(hours: int = 24) -> dict[str, Any]:
    cutoff = _iso(datetime.now(timezone.utc) - timedelta(hours=hours))
    frame = query_df(
        """
        SELECT * FROM traffic_observations
        WHERE datetime >= ?
        ORDER BY datetime ASC
        """,
        (cutoff,),
    )
    if frame.empty:
        return {"kpis": {}, "recent": [], "trend": []}

    severe_share = float((frame["predicted_congestion"] == "Severe").mean() * 100)
    latest = frame.sort_values("datetime").groupby("segment_id", as_index=False).tail(1)
    trend = (
        frame.assign(bucket=pd.to_datetime(frame["datetime"], utc=True).dt.floor("2h").astype(str))
        .groupby("bucket", as_index=False)
        .agg(
            predicted_volume=("predicted_volume", "mean"),
            predicted_travel_time=("predicted_travel_time", "mean"),
            predicted_accident_risk=("predicted_accident_risk", "mean"),
        )
        .tail(18)
    )
    return {
        "kpis": {
            "average_speed_kmh": round(float(frame["speed_kmh"].mean()), 1),
            "average_volume": round(float(frame["predicted_volume"].mean()), 0),
            "average_travel_time_min": round(float(frame["predicted_travel_time"].mean()), 1),
            "high_risk_segments": int((latest["predicted_accident_risk"] >= 0.55).sum()),
            "severe_congestion_share": round(severe_share, 1),
            "active_segments": int(latest["segment_id"].nunique()),
        },
        "latest_segments": latest[
            [
                "segment_id", "segment_name", "latitude", "longitude", "speed_kmh",
                "predicted_volume", "predicted_travel_time", "predicted_congestion",
                "predicted_accident_risk", "model_version", "datetime",
            ]
        ].to_dict(orient="records"),
        "trend": trend.to_dict(orient="records"),
        "model_mode": "demo_fallback" if model_service.using_demo_fallback else "loaded_artifacts",
        "model_version": model_service.model_version,
    }


def near_term_predictions(horizon_minutes: int = 60, segment_id: str | None = None) -> list[dict[str, Any]]:
    base = query_df(
        """
        SELECT t.* FROM traffic_observations t
        INNER JOIN (
            SELECT segment_id, MAX(datetime) AS max_dt
            FROM traffic_observations GROUP BY segment_id
        ) latest
        ON t.segment_id = latest.segment_id AND t.datetime = latest.max_dt
        ORDER BY t.segment_id
        """
    )
    if segment_id and segment_id.lower() != "all":
        base = base[base["segment_id"] == segment_id]
    if base.empty:
        return []

    steps = max(1, min(6, horizon_minutes // 30))
    future_rows: list[pd.DataFrame] = []
    for step in range(1, steps + 1):
        future = base.copy()
        future["datetime"] = (
            pd.to_datetime(future["datetime"], utc=True) + pd.to_timedelta(step * 30, unit="m")
        ).astype(str)
        hour = pd.to_datetime(future["datetime"], utc=True).dt.hour
        peak_change = np.where(hour.isin([8, 9, 10, 17, 18, 19]), 1.06, 0.98)
        future["volume"] = future["volume"] * peak_change
        future["occupancy"] = (future["occupancy"] * peak_change).clip(0, 1)
        future_rows.append(future)
    forecast_input = pd.concat(future_rows, ignore_index=True)
    forecast = model_service.predict_dataframe(forecast_input, source="near_term_forecast")
    keep = [
        "prediction_id", "run_id", "datetime", "segment_id", "segment_name", "latitude",
        "longitude", "predicted_volume", "predicted_travel_time", "predicted_congestion",
        "predicted_accident_risk", "confidence", "model_version", "input_hash", "created_at",
    ]
    return forecast[keep].to_dict(orient="records")


def historical(start: str | None, end: str | None, segment_id: str | None = None) -> list[dict[str, Any]]:
    start_iso, end_iso = _range(start, end)
    params: list[Any] = [start_iso, end_iso]
    condition = ""
    if segment_id and segment_id.lower() != "all":
        condition = " AND segment_id = ?"
        params.append(segment_id)
    frame = query_df(
        f"""
        SELECT datetime, segment_id, segment_name, speed_kmh, volume,
               predicted_volume, travel_time_min, predicted_travel_time,
               predicted_accident_risk, temp_c, rain_mm
        FROM traffic_observations
        WHERE datetime BETWEEN ? AND ? {condition}
        ORDER BY datetime
        """,
        tuple(params),
    )
    if frame.empty:
        return []
    frame["bucket"] = pd.to_datetime(frame["datetime"], utc=True).dt.floor("2h").astype(str)
    grouped = (
        frame.groupby(["bucket", "segment_id", "segment_name"], as_index=False)
        .agg(
            speed_kmh=("speed_kmh", "mean"),
            volume=("volume", "mean"),
            predicted_volume=("predicted_volume", "mean"),
            travel_time_min=("travel_time_min", "mean"),
            predicted_travel_time=("predicted_travel_time", "mean"),
            predicted_accident_risk=("predicted_accident_risk", "mean"),
            temp_c=("temp_c", "mean"),
            rain_mm=("rain_mm", "mean"),
        )
    )
    numeric = grouped.select_dtypes(include="number").columns
    grouped[numeric] = grouped[numeric].round(3)
    return grouped.to_dict(orient="records")


def heatmap(start: str | None, end: str | None) -> dict[str, Any]:
    start_iso, end_iso = _range(start, end)
    frame = query_df(
        """
        SELECT datetime, segment_id, segment_name, predicted_travel_time,
               predicted_accident_risk, predicted_congestion
        FROM traffic_observations
        WHERE datetime BETWEEN ? AND ?
        """,
        (start_iso, end_iso),
    )
    if frame.empty:
        return {"segments": [], "hours": [], "cells": []}
    frame["hour"] = pd.to_datetime(frame["datetime"], utc=True).dt.hour
    congestion_score = {"Low": 1, "Moderate": 2, "High": 3, "Severe": 4}
    frame["score"] = frame["predicted_congestion"].map(congestion_score).fillna(1)
    grouped = (
        frame.groupby(["segment_id", "segment_name", "hour"], as_index=False)
        .agg(
            congestion_score=("score", "mean"),
            travel_time_min=("predicted_travel_time", "mean"),
            accident_risk=("predicted_accident_risk", "mean"),
        )
    )
    grouped = grouped.round(3)
    return {
        "segments": [
            {"segment_id": segment_id, "segment_name": name}
            for segment_id, name, *_ in SEGMENTS
        ],
        "hours": list(range(24)),
        "cells": grouped.to_dict(orient="records"),
    }


def road_comparison(start: str | None, end: str | None) -> list[dict[str, Any]]:
    start_iso, end_iso = _range(start, end)
    frame = query_df(
        """
        SELECT segment_id, segment_name,
               AVG(speed_kmh) AS average_speed_kmh,
               AVG(predicted_volume) AS average_volume,
               AVG(predicted_travel_time) AS average_travel_time_min,
               AVG(predicted_accident_risk) AS average_accident_risk,
               SUM(CASE WHEN predicted_congestion IN ('High','Severe') THEN 1 ELSE 0 END) * 1.0 / COUNT(*) AS high_congestion_share
        FROM traffic_observations
        WHERE datetime BETWEEN ? AND ?
        GROUP BY segment_id, segment_name
        ORDER BY average_travel_time_min DESC
        """,
        (start_iso, end_iso),
    )
    if frame.empty:
        return []
    numeric = frame.select_dtypes(include="number").columns
    frame[numeric] = frame[numeric].round(3)
    return frame.to_dict(orient="records")


def weather_impact(start: str | None, end: str | None) -> dict[str, Any]:
    start_iso, end_iso = _range(start, end, default_days=14)
    frame = query_df(
        """
        SELECT rain_mm, temp_c, visibility_km, speed_kmh, predicted_volume,
               predicted_travel_time, predicted_accident_risk
        FROM traffic_observations
        WHERE datetime BETWEEN ? AND ?
        """,
        (start_iso, end_iso),
    )
    if frame.empty:
        return {"buckets": [], "correlations": {}}
    frame["rain_bucket"] = pd.cut(
        frame["rain_mm"],
        bins=[-0.1, 0.01, 2, 5, 15, float("inf")],
        labels=["Dry", "Light", "Moderate", "Heavy", "Extreme"],
    ).astype(str)
    grouped = (
        frame.groupby("rain_bucket", observed=False, as_index=False)
        .agg(
            average_speed_kmh=("speed_kmh", "mean"),
            average_volume=("predicted_volume", "mean"),
            average_travel_time_min=("predicted_travel_time", "mean"),
            average_accident_risk=("predicted_accident_risk", "mean"),
            observations=("rain_mm", "size"),
        )
        .round(3)
    )
    corr = frame.corr(numeric_only=True)["rain_mm"].drop("rain_mm").round(3).to_dict()
    return {"buckets": grouped.to_dict(orient="records"), "correlations": corr}


def generated_alerts() -> list[dict[str, Any]]:
    predictions = near_term_predictions(60)
    alerts: list[dict[str, Any]] = []
    with connection() as conn:
        acknowledged = {
            row["alert_id"] for row in conn.execute("SELECT alert_id FROM acknowledged_alerts").fetchall()
        }
    for row in predictions:
        risk = float(row["predicted_accident_risk"])
        congestion = row["predicted_congestion"]
        if risk < 0.50 and congestion not in {"High", "Severe"}:
            continue
        severity = "critical" if risk >= 0.72 or congestion == "Severe" else "warning"
        raw_id = f"{row['segment_id']}|{row['datetime']}|{severity}"
        alert_id = hashlib.sha1(raw_id.encode("utf-8")).hexdigest()[:16]
        if alert_id in acknowledged:
            continue
        reasons = []
        if congestion in {"High", "Severe"}:
            reasons.append(f"{congestion.lower()} congestion")
        if risk >= 0.50:
            reasons.append(f"accident risk {risk:.0%}")
        alerts.append(
            {
                "alert_id": alert_id,
                "severity": severity,
                "segment_id": row["segment_id"],
                "segment_name": row["segment_name"],
                "forecast_time": row["datetime"],
                "message": " and ".join(reasons).capitalize(),
                "recommended_action": (
                    "Dispatch patrol and verify signal plan" if severity == "critical"
                    else "Monitor segment and prepare diversion message"
                ),
                "confidence": row["confidence"],
            }
        )
    return sorted(alerts, key=lambda item: (item["severity"] != "critical", -item["confidence"]))
