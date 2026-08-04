"""Application configuration for FlowCast."""

from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
QUARANTINE_DIR = DATA_DIR / "quarantine"
EXPORT_DIR = DATA_DIR / "exports"
MODEL_DIR = BASE_DIR / "model_artifacts"
STATIC_DIR = BASE_DIR / "app" / "static"
LOG_DIR = BASE_DIR / "logs"
DB_PATH = DATA_DIR / "flowcast.db"
REGISTRY_PATH = MODEL_DIR / "registry.json"

APP_NAME = "FlowCast"
APP_VERSION = "1.0.0"
RANDOM_SEED = 42
MAX_UPLOAD_ROWS = int(os.getenv("MAX_UPLOAD_ROWS", "200000"))
BATCH_CHUNK_SIZE = int(os.getenv("BATCH_CHUNK_SIZE", "25000"))
DEFAULT_LATITUDE = float(os.getenv("FLOWCAST_LATITUDE", "22.5726"))
DEFAULT_LONGITUDE = float(os.getenv("FLOWCAST_LONGITUDE", "88.3639"))
OPEN_METEO_TIMEOUT_SECONDS = float(os.getenv("OPEN_METEO_TIMEOUT_SECONDS", "8"))

ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("ALLOWED_ORIGINS", "http://localhost:8000").split(",")
    if origin.strip()
]

for directory in (DATA_DIR, QUARANTINE_DIR, EXPORT_DIR, MODEL_DIR, LOG_DIR):
    directory.mkdir(parents=True, exist_ok=True)
