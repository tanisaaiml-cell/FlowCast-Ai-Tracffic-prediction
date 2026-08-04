"""Open-Meteo weather integration with a safe fallback."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx

from app.config import OPEN_METEO_TIMEOUT_SECONDS

WEATHER_URL = "https://api.open-meteo.com/v1/forecast"


async def get_current_weather(latitude: float, longitude: float) -> dict[str, Any]:
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "current": "temperature_2m,precipitation,weather_code,wind_speed_10m,visibility",
        "hourly": "temperature_2m,precipitation_probability,precipitation,visibility",
        "forecast_days": 2,
        "timezone": "auto",
    }
    try:
        async with httpx.AsyncClient(timeout=OPEN_METEO_TIMEOUT_SECONDS) as client:
            response = await client.get(WEATHER_URL, params=params)
            response.raise_for_status()
            payload = response.json()
        current = payload.get("current", {})
        return {
            "source": "Open-Meteo",
            "latitude": payload.get("latitude", latitude),
            "longitude": payload.get("longitude", longitude),
            "timezone": payload.get("timezone", "UTC"),
            "temperature_c": current.get("temperature_2m"),
            "precipitation_mm": current.get("precipitation"),
            "wind_speed_kmh": current.get("wind_speed_10m"),
            "visibility_km": round((current.get("visibility") or 10000) / 1000, 2),
            "weather_code": current.get("weather_code"),
            "observed_at": current.get("time") or datetime.now(timezone.utc).isoformat(),
            "hourly": payload.get("hourly", {}),
        }
    except Exception as exc:
        return {
            "source": "fallback",
            "latitude": latitude,
            "longitude": longitude,
            "timezone": "UTC",
            "temperature_c": 29.0,
            "precipitation_mm": 0.0,
            "wind_speed_kmh": 8.0,
            "visibility_km": 10.0,
            "weather_code": 0,
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "hourly": {},
            "warning": f"Live weather unavailable: {type(exc).__name__}",
        }
