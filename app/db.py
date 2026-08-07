"""SQLite helpers and deterministic demo-data bootstrap."""

from __future__ import annotations

import math
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Iterator

import numpy as np
import pandas as pd

from app.config import DB_PATH, RANDOM_SEED

SEGMENTS = [
    ("SEG-01", "North Gate → Central Square", 22.5884, 88.3491, 1.9),
    ("SEG-02", "Central Square → River Bridge", 22.5792, 88.3554, 2.3),
    ("SEG-03", "River Bridge → Tech Park", 22.5681, 88.3697, 3.1),
    ("SEG-04", "Tech Park → South Junction", 22.5548, 88.3762, 2.7),
    ("SEG-05", "East Market → Central Square", 22.5765, 88.3893, 2.0),
    ("SEG-06", "Airport Link → Tech Park", 22.5627, 88.4021, 4.2),
    ("SEG-07", "University Road → River Bridge", 22.5902, 88.3735, 2.6),
    ("SEG-08", "Industrial Belt → South Junction", 22.5451, 88.3608, 3.8),
]


@contextmanager
def connection() -> Iterator[sqlite3.Connection]:
    """Open a SQLite connection with rows returned as mappings."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    """Create tables and seed deterministic demo data when empty."""
    with connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS traffic_observations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                datetime TEXT NOT NULL,
                segment_id TEXT NOT NULL,
                segment_name TEXT NOT NULL,
                latitude REAL NOT NULL,
                longitude REAL NOT NULL,
                distance_km REAL NOT NULL,
                speed_kmh REAL NOT NULL,
                volume REAL NOT NULL,
                occupancy REAL NOT NULL,
                travel_time_min REAL NOT NULL,
                congestion_level TEXT NOT NULL,
                accident_risk REAL NOT NULL,
                temp_c REAL NOT NULL,
                rain_mm REAL NOT NULL,
                visibility_km REAL NOT NULL,
                event_flag INTEGER NOT NULL,
                predicted_volume REAL NOT NULL,
                predicted_travel_time REAL NOT NULL,
                predicted_congestion TEXT NOT NULL,
                predicted_accident_risk REAL NOT NULL,
                model_version TEXT NOT NULL,
                input_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(datetime, segment_id)
            );

            CREATE INDEX IF NOT EXISTS idx_traffic_datetime
            ON traffic_observations(datetime);

            CREATE INDEX IF NOT EXISTS idx_traffic_segment_datetime
            ON traffic_observations(segment_id, datetime);

            CREATE TABLE IF NOT EXISTS prediction_runs (
                run_id TEXT PRIMARY KEY,
                source_file TEXT NOT NULL,
                total_rows INTEGER NOT NULL,
                valid_rows INTEGER NOT NULL,
                invalid_rows INTEGER NOT NULL,
                elapsed_seconds REAL NOT NULL,
                model_version TEXT NOT NULL,
                export_filename TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS acknowledged_alerts (
                alert_id TEXT PRIMARY KEY,
                acknowledged_at TEXT NOT NULL
            );
            """
        )
        count = conn.execute("SELECT COUNT(*) AS n FROM traffic_observations").fetchone()["n"]
        if count == 0:
            _seed_demo_data(conn)


def _seed_demo_data(conn: sqlite3.Connection) -> None:
    """Generate 30 days of half-hourly corridor observations."""
    rng = np.random.default_rng(RANDOM_SEED)
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    start = now - timedelta(days=30)
    timestamps = pd.date_range(start=start, end=now, freq="30min", tz="UTC")
    rows: list[tuple] = []

    for dt in timestamps:
        hour = dt.hour + dt.minute / 60
        weekday = dt.weekday()
        morning_peak = math.exp(-((hour - 9) ** 2) / 4.5)
        evening_peak = math.exp(-((hour - 18) ** 2) / 5.0)
        weekend_factor = 0.78 if weekday >= 5 else 1.0
        event_flag = int((weekday in (4, 5)) and (18 <= hour <= 22) and rng.random() < 0.22)
        temp_c = 28 + 5 * math.sin((hour - 8) / 24 * 2 * math.pi) + rng.normal(0, 1.3)
        rain_mm = max(0.0, rng.gamma(1.2, 1.7) - 1.8) if rng.random() < 0.18 else 0.0
        visibility_km = max(1.5, 11 - rain_mm * 1.3 + rng.normal(0, 0.7))

        for index, (segment_id, name, lat, lon, distance_km) in enumerate(SEGMENTS):
            segment_factor = 0.85 + index * 0.055
            base_volume = 430 * segment_factor * weekend_factor
            peak_factor = 1 + 1.45 * morning_peak + 1.7 * evening_peak + 0.55 * event_flag
            weather_factor = 1 - min(rain_mm * 0.015, 0.16)
            volume = max(80, base_volume * peak_factor * weather_factor + rng.normal(0, 35))
            free_speed = 50 - index * 1.2
            congestion_pressure = min(1.0, volume / (1050 + index * 45))
            speed = free_speed * (1 - 0.58 * congestion_pressure) - rain_mm * 0.85 + rng.normal(0, 2.4)
            speed = max(8.0, speed)
            occupancy = min(0.98, max(0.08, 0.12 + congestion_pressure * 0.78 + rng.normal(0, 0.035)))
            travel_time = distance_km / speed * 60 * (1 + occupancy * 0.18)
            risk = min(
                0.99,
                max(
                    0.01,
                    0.035
                    + 0.42 * congestion_pressure
                    + 0.035 * rain_mm
                    + 0.02 * max(0, 7 - visibility_km)
                    + 0.10 * event_flag
                    + rng.normal(0, 0.025),
                ),
            )
            if congestion_pressure < 0.42:
                congestion = "Low"
            elif congestion_pressure < 0.68:
                congestion = "Moderate"
            elif congestion_pressure < 0.86:
                congestion = "High"
            else:
                congestion = "Severe"

            predicted_volume = volume * (1 + rng.normal(0, 0.045))
            predicted_travel = travel_time * (1 + rng.normal(0, 0.055))
            risk_pred = min(0.99, max(0.01, risk + rng.normal(0, 0.035)))
            predicted_congestion = congestion
            input_hash = f"demo-{segment_id}-{dt.isoformat()}"
            created_at = dt.isoformat()
            rows.append(
                (
                    dt.isoformat(), segment_id, name, lat, lon, distance_km,
                    float(speed), float(volume), float(occupancy), float(travel_time),
                    congestion, float(risk), float(temp_c), float(rain_mm),
                    float(visibility_km), event_flag, float(predicted_volume),
                    float(predicted_travel), predicted_congestion, float(risk_pred),
                    "demo-1.0", input_hash, created_at,
                )
            )

    conn.executemany(
        """
        INSERT OR IGNORE INTO traffic_observations (
            datetime, segment_id, segment_name, latitude, longitude, distance_km,
            speed_kmh, volume, occupancy, travel_time_min, congestion_level,
            accident_risk, temp_c, rain_mm, visibility_km, event_flag,
            predicted_volume, predicted_travel_time, predicted_congestion,
            predicted_accident_risk, model_version, input_hash, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )


def query_df(
    query: str,
    parameters: tuple | list | None = None,
) -> pd.DataFrame:
    with connection() as conn:
        return pd.read_sql_query(
            query,
            conn,
            params=parameters or (),
        )


def execute(sql: str, params: tuple | list = ()) -> None:
    """Run a modifying statement."""
    with connection() as conn:
        conn.execute(sql, params)
