"""FlowCast REST API routes."""

from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, Response

from app.config import DEFAULT_LATITUDE, DEFAULT_LONGITUDE, EXPORT_DIR, QUARANTINE_DIR
from app.db import SEGMENTS, execute, query_df
from app.schemas import SinglePredictionRequest
from app.services.analytics_service import (
    generated_alerts,
    heatmap,
    historical,
    near_term_predictions,
    overview,
    road_comparison,
    weather_impact,
)
from app.services.model_service import model_service
from app.services.report_service import build_csv_report, build_html_report
from app.services.upload_service import process_upload
from app.services.weather_service import get_current_weather

router = APIRouter(prefix="/api")

ROLE_CAPABILITIES = {
    "traffic_analyst": {
    "label": "Traffic Operations Analyst",
    "default_view": "overview",
    "views": [
        "overview",
        "live",
        "historical",
        "map",
        "weather",
        "alerts",
        "reports",
    ],
    "goal": "Anticipate congestion and act before it forms.",
},
    "incident_coordinator": {
    "label": "Incident Response Coordinator",
    "default_view": "alerts",
    "views": [
        "overview",
        "live",
        "map",
        "alerts",
    ],
    "goal": "Position patrols where risk is rising.",
},
    "transport_planner": {
    "label": "Transport Planner",
    "default_view": "historical",
    "views": [
        "overview",
        "historical",
        "map",
        "weather",
        "reports",
    ],
    "goal": "Make evidence-based infrastructure decisions.",
    },
   "system_owner": {
    "label": "System Owner / Reviewer",
    "default_view": "model",
    "views": [
        "overview",
        "live",
        "historical",
        "map",
        "weather",
        "model",
        "upload",
        "alerts",
        "reports",
    ],
    "goal": "Trust and audit the model.",
},

  
}


@router.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "service": "FlowCast API",
        "time": datetime.now(timezone.utc).isoformat(),
        "model_version": model_service.model_version,
        "model_mode": "demo_fallback" if model_service.using_demo_fallback else "loaded_artifacts",
    }


@router.get("/metadata")
def metadata() -> dict:
    return {
        "segments": [
            {
                "segment_id": segment_id,
                "segment_name": name,
                "latitude": lat,
                "longitude": lon,
                "distance_km": distance,
            }
            for segment_id, name, lat, lon, distance in SEGMENTS
        ],
        "roles": ROLE_CAPABILITIES,
        "model_version": model_service.model_version,
    }


@router.get("/dashboard/overview")
def dashboard_overview(hours: int = Query(default=24, ge=1, le=720)) -> dict:
    return overview(hours)


@router.get("/predictions/near-term")
def predictions_near_term(
    horizon_minutes: int = Query(default=60, ge=30, le=180),
    segment_id: str | None = Query(default=None),
) -> dict:
    return {"predictions": near_term_predictions(horizon_minutes, segment_id)}


@router.post("/predict/single")
def predict_single(payload: SinglePredictionRequest) -> dict:
    import pandas as pd

    frame = pd.DataFrame([payload.model_dump(mode="json")])
    result = model_service.predict_dataframe(frame, source="single_prediction")
    return result.iloc[0].to_dict()


@router.post("/predict/upload")
def predict_upload(file: UploadFile = File(...)) -> dict:
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Please upload a CSV file.")
    try:
        return process_upload(file.file, file.filename)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Prediction run failed: {type(exc).__name__}") from exc


@router.get("/analytics/historical")
def analytics_historical(
    start: str | None = None,
    end: str | None = None,
    segment_id: str | None = None,
) -> dict:
    return {"series": historical(start, end, segment_id)}


@router.get("/analytics/heatmap")
def analytics_heatmap(start: str | None = None, end: str | None = None) -> dict:
    return heatmap(start, end)


@router.get("/analytics/road-comparison")
def analytics_road_comparison(start: str | None = None, end: str | None = None) -> dict:
    return {"roads": road_comparison(start, end)}

@router.get("/map/traffic")
def traffic_map() -> dict:
    """Return the latest traffic condition for every road segment."""

    frame = query_df(
        """
        SELECT
            traffic.segment_id,
            traffic.segment_name,
            traffic.latitude,
            traffic.longitude,
            traffic.distance_km,
            traffic.datetime,
            traffic.speed_kmh,
            traffic.volume,
            traffic.occupancy,
            traffic.predicted_volume,
            traffic.predicted_travel_time,
            traffic.predicted_congestion,
            traffic.predicted_accident_risk,
            traffic.model_version
        FROM traffic_observations AS traffic

        INNER JOIN (
            SELECT
                segment_id,
                MAX(datetime) AS latest_datetime
            FROM traffic_observations
            GROUP BY segment_id
        ) AS latest
            ON traffic.segment_id = latest.segment_id
            AND traffic.datetime = latest.latest_datetime

        ORDER BY traffic.segment_id
        """
    )

    return {
        "segments": frame.to_dict(orient="records"),
        "total_segments": int(len(frame)),
    }

@router.get("/analytics/weather-impact")
def analytics_weather_impact(start: str | None = None, end: str | None = None) -> dict:
    return weather_impact(start, end)


@router.get("/model/diagnostics")
def model_diagnostics() -> dict:
    return model_service.diagnostics()


@router.get("/alerts")
def alerts() -> dict:
    return {"alerts": generated_alerts()}


@router.post("/alerts/{alert_id}/acknowledge")
def acknowledge_alert(alert_id: str) -> dict:
    execute(
        "INSERT OR REPLACE INTO acknowledged_alerts (alert_id, acknowledged_at) VALUES (?, ?)",
        (alert_id, datetime.now(timezone.utc).isoformat()),
    )
    return {"status": "acknowledged", "alert_id": alert_id}


@router.get("/weather/current")
async def weather_current(
    latitude: float = Query(default=DEFAULT_LATITUDE, ge=-90, le=90),
    longitude: float = Query(default=DEFAULT_LONGITUDE, ge=-180, le=180),
) -> dict:
    return await get_current_weather(latitude, longitude)
@router.get("/reports/summary")
def report_summary(
    start: str | None = None,
    end: str | None = None,
) -> dict:
    conditions: list[str] = []
    parameters: list[str] = []

    if start:
        conditions.append("date(datetime) >= date(?)")
        parameters.append(start)

    if end:
        conditions.append("date(datetime) <= date(?)")
        parameters.append(end)

    where_clause = ""

    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)

    summary_frame = query_df(
        f"""
        SELECT
            COUNT(*) AS total_records,
            COUNT(DISTINCT segment_id) AS total_segments,
            COALESCE(
                ROUND(AVG(predicted_volume), 2),
                0
            ) AS average_volume,
            COALESCE(
                ROUND(AVG(predicted_travel_time), 2),
                0
            ) AS average_travel_time,
            COALESCE(
                ROUND(AVG(predicted_accident_risk) * 100, 2),
                0
            ) AS average_accident_risk
        FROM traffic_observations
        {where_clause}
        """,
        tuple(parameters),
    )

    congestion_frame = query_df(
        f"""
        SELECT
            predicted_congestion AS congestion,
            COUNT(*) AS count
        FROM traffic_observations
        {where_clause}
        GROUP BY predicted_congestion
        ORDER BY count DESC
        """,
        tuple(parameters),
    )

    if summary_frame.empty:
        summary = {
            "total_records": 0,
            "total_segments": 0,
            "average_volume": 0,
            "average_travel_time": 0,
            "average_accident_risk": 0,
        }
    else:
        row = summary_frame.iloc[0]

        summary = {
            "total_records": int(row["total_records"] or 0),
            "total_segments": int(row["total_segments"] or 0),
            "average_volume": float(row["average_volume"] or 0),
            "average_travel_time": float(
                row["average_travel_time"] or 0
            ),
            "average_accident_risk": float(
                row["average_accident_risk"] or 0
            ),
        }

    return {
        "summary": summary,
        "congestion_distribution": congestion_frame.to_dict(
            orient="records"
        ),
        "selected_range": {
            "start": start,
            "end": end,
        },
    }
    
@router.get("/reports/export")
def export_report(
    format: str = Query(default="csv", pattern="^(csv|html)$"),
    start: str | None = None,
    end: str | None = None,
) -> Response:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    if format == "html":
        return Response(
            content=build_html_report(start, end),
            media_type="text/html",
            headers={"Content-Disposition": f'attachment; filename="flowcast_report_{timestamp}.html"'},
        )
    return Response(
        content=build_csv_report(start, end),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="flowcast_report_{timestamp}.csv"'},
    )


@router.get("/exports/{filename}")
def download_export(filename: str) -> FileResponse:
    safe_name = Path(filename).name
    path = EXPORT_DIR / safe_name
    if not path.exists():
        raise HTTPException(status_code=404, detail="Export not found.")
    return FileResponse(path, filename=safe_name, media_type="text/csv")


@router.get("/quarantine/{filename}")
def download_quarantine(filename: str) -> FileResponse:
    safe_name = Path(filename).name
    path = QUARANTINE_DIR / safe_name
    if not path.exists():
        raise HTTPException(status_code=404, detail="Quarantine file not found.")
    return FileResponse(path, filename=safe_name, media_type="text/csv")


@router.get("/prediction-runs")
def prediction_runs() -> dict:
    frame = query_df("SELECT * FROM prediction_runs ORDER BY created_at DESC LIMIT 20")
    return {"runs": frame.to_dict(orient="records")}
