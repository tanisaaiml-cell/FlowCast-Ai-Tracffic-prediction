"""Quick installation validation."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db import init_db, query_df  # noqa: E402
from app.services.model_service import model_service  # noqa: E402

init_db()
count = query_df("SELECT COUNT(*) AS n FROM traffic_observations").iloc[0]["n"]
print(f"FlowCast setup OK. Demo observations: {count:,}")
print(f"Model version: {model_service.model_version}")
print("Run: python -m uvicorn main:app --reload")
