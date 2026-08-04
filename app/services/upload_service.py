"""Chunked CSV validation, quarantine, inference, and export."""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, BinaryIO

import pandas as pd

from app.config import BATCH_CHUNK_SIZE, EXPORT_DIR, MAX_UPLOAD_ROWS, QUARANTINE_DIR
from app.db import execute
from app.services.model_service import model_service

REQUIRED_COLUMNS = [
    "datetime", "segment_id", "speed_kmh", "volume", "occupancy",
    "temp_c", "rain_mm", "visibility_km", "event_flag",
]
OPTIONAL_DEFAULTS = {"distance_km": 2.5, "segment_name": "Uploaded segment"}


def _validate_chunk(chunk: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    missing = [column for column in REQUIRED_COLUMNS if column not in chunk.columns]
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")

    work = chunk.copy()
    for column, default in OPTIONAL_DEFAULTS.items():
        if column not in work.columns:
            work[column] = default

    errors = pd.Series("", index=work.index, dtype="object")
    parsed_dt = pd.to_datetime(work["datetime"], errors="coerce", utc=True)
    errors = errors.mask(parsed_dt.isna(), errors + "invalid datetime; ")
    work["datetime"] = parsed_dt.astype(str)

    numeric_rules = {
        "speed_kmh": (0.01, 200),
        "volume": (0, 100000),
        "occupancy": (0, 1),
        "temp_c": (-30, 60),
        "rain_mm": (0, 500),
        "visibility_km": (0.01, 100),
        "event_flag": (0, 1),
        "distance_km": (0.01, 100),
    }
    for column, (minimum, maximum) in numeric_rules.items():
        values = pd.to_numeric(work[column], errors="coerce")
        invalid = values.isna() | (values < minimum) | (values > maximum)
        errors = errors.mask(invalid, errors + f"invalid {column}; ")
        work[column] = values

    errors = errors.mask(work["segment_id"].astype(str).str.strip().eq(""), errors + "empty segment_id; ")
    valid_mask = errors.eq("")
    valid = work.loc[valid_mask].copy()
    invalid = work.loc[~valid_mask].copy()
    invalid["_validation_error"] = errors.loc[~valid_mask].str.rstrip("; ")
    return valid, invalid


def process_upload(file_handle: BinaryIO, original_filename: str) -> dict[str, Any]:
    started = time.perf_counter()
    run_id = str(uuid.uuid4())
    predictions: list[pd.DataFrame] = []
    invalid_parts: list[pd.DataFrame] = []
    total_rows = 0

    try:
        iterator = pd.read_csv(file_handle, chunksize=BATCH_CHUNK_SIZE)
        for chunk in iterator:
            total_rows += len(chunk)
            if total_rows > MAX_UPLOAD_ROWS:
                raise ValueError(f"Upload exceeds the {MAX_UPLOAD_ROWS:,}-row safety limit.")
            valid, invalid = _validate_chunk(chunk)
            if not valid.empty:
                predictions.append(model_service.predict_dataframe(valid, source=original_filename))
            if not invalid.empty:
                invalid_parts.append(invalid)
    except pd.errors.EmptyDataError as exc:
        raise ValueError("The uploaded CSV is empty.") from exc

    result = pd.concat(predictions, ignore_index=True) if predictions else pd.DataFrame()
    invalid_result = pd.concat(invalid_parts, ignore_index=True) if invalid_parts else pd.DataFrame()

    safe_stem = Path(original_filename).stem.replace(" ", "_")[:60] or "upload"
    export_filename = f"{safe_stem}_{run_id[:8]}_predictions.csv"
    export_path = EXPORT_DIR / export_filename
    result.to_csv(export_path, index=False)

    quarantine_filename = ""
    if not invalid_result.empty:
        quarantine_filename = f"{safe_stem}_{run_id[:8]}_quarantine.csv"
        invalid_result.to_csv(QUARANTINE_DIR / quarantine_filename, index=False)

    elapsed = time.perf_counter() - started
    created_at = datetime.now(timezone.utc).isoformat()
    execute(
        """
        INSERT INTO prediction_runs (
            run_id, source_file, total_rows, valid_rows, invalid_rows,
            elapsed_seconds, model_version, export_filename, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id, original_filename, total_rows, len(result), len(invalid_result),
            elapsed, model_service.model_version, export_filename, created_at,
        ),
    )

    preview_columns = [
        "datetime", "segment_id", "predicted_volume", "predicted_travel_time",
        "predicted_congestion", "predicted_accident_risk", "confidence",
        "model_version", "input_hash",
    ]
    preview = result.reindex(columns=preview_columns).head(100).to_dict(orient="records")
    return {
        "run_id": run_id,
        "total_rows": total_rows,
        "valid_rows": len(result),
        "invalid_rows": len(invalid_result),
        "elapsed_seconds": round(elapsed, 3),
        "under_30_second_target": elapsed <= 30,
        "model_version": model_service.model_version,
        "export_filename": export_filename,
        "quarantine_filename": quarantine_filename,
        "preview": preview,
    }
