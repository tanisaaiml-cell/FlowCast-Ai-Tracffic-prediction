"""Benchmark 150,000-row in-memory batch inference for the NFR target."""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.model_service import model_service  # noqa: E402


def main() -> None:
    rows = 150_000
    rng = np.random.default_rng(42)
    frame = pd.DataFrame({
        "datetime": pd.date_range("2026-01-01", periods=rows, freq="30min", tz="UTC").astype(str),
        "segment_id": np.resize([f"SEG-{n:02d}" for n in range(1, 9)], rows),
        "segment_name": "Benchmark segment",
        "speed_kmh": rng.uniform(10, 60, rows),
        "volume": rng.uniform(100, 1400, rows),
        "occupancy": rng.uniform(0.1, 0.95, rows),
        "temp_c": rng.uniform(18, 42, rows),
        "rain_mm": rng.uniform(0, 8, rows),
        "visibility_km": rng.uniform(2, 14, rows),
        "event_flag": rng.integers(0, 2, rows),
        "distance_km": rng.uniform(1, 5, rows),
    })
    started = time.perf_counter()
    result = model_service.predict_dataframe(frame, source="benchmark")
    elapsed = time.perf_counter() - started
    print(f"Rows: {len(result):,}")
    print(f"Elapsed: {elapsed:.3f} seconds")
    print(f"Target <= 30s: {'PASS' if elapsed <= 30 else 'REVIEW'}")
    print(f"Approx result memory: {result.memory_usage(deep=True).sum() / 1024 ** 2:.1f} MB")


if __name__ == "__main__":
    main()
