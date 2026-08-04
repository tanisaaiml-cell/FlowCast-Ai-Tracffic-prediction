"""Pydantic request and response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class SinglePredictionRequest(BaseModel):
    segment_id: str = Field(min_length=1)
    datetime: datetime
    speed_kmh: float = Field(gt=0, le=200)
    volume: float = Field(ge=0)
    occupancy: float = Field(ge=0, le=1)
    temp_c: float = Field(ge=-30, le=60)
    rain_mm: float = Field(ge=0, le=500)
    visibility_km: float = Field(gt=0, le=100)
    event_flag: int = Field(ge=0, le=1)
    distance_km: float = Field(gt=0, le=100, default=2.5)


class SinglePredictionResponse(BaseModel):
    prediction_id: str
    run_id: str
    segment_id: str
    predicted_volume: float
    predicted_travel_time: float
    predicted_congestion: Literal["Low", "Moderate", "High", "Severe"]
    predicted_accident_risk: float
    confidence: float
    model_version: str
    input_hash: str
    created_at: datetime
