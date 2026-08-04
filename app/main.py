"""FlowCast FastAPI application entry point."""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.config import ALLOWED_ORIGINS, APP_NAME, APP_VERSION, LOG_DIR, STATIC_DIR
from app.db import init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "flowcast.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("flowcast")

@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    logger.info("FlowCast started")
    yield
    logger.info("FlowCast stopped")


app = FastAPI(
    title=f"{APP_NAME} API",
    version=APP_VERSION,
    description="Traffic forecasting, analytics, alerts, model transparency and batch inference API.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(router)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.middleware("http")
async def request_logging(request: Request, call_next):
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("Unhandled request failure: %s %s", request.method, request.url.path)
        raise
    elapsed_ms = (time.perf_counter() - started) * 1000
    response.headers["X-Process-Time-Ms"] = f"{elapsed_ms:.2f}"
    logger.info("%s %s -> %s in %.1f ms", request.method, request.url.path, response.status_code, elapsed_ms)
    return response


@app.get("/", include_in_schema=False)
def frontend() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/{full_path:path}", include_in_schema=False)
def spa_fallback(full_path: str) -> FileResponse:
    candidate = STATIC_DIR / full_path
    if candidate.exists() and candidate.is_file():
        return FileResponse(candidate)
    return FileResponse(STATIC_DIR / "index.html")
