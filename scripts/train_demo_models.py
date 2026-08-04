"""Train demonstration models from the seeded SQLite data.

Run:
    python scripts/train_demo_models.py

This creates four joblib artifacts and updates model_artifacts/registry.json.
Replace this script with your Colab-trained pipelines for your final project.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.metrics import accuracy_score, f1_score, mean_absolute_error, mean_squared_error, r2_score, roc_auc_score

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import MODEL_DIR, RANDOM_SEED, REGISTRY_PATH  # noqa: E402
from app.db import init_db, query_df  # noqa: E402

FEATURES = [
    "speed_kmh", "volume", "occupancy", "temp_c", "rain_mm", "visibility_km",
    "event_flag", "distance_km", "hour", "day_of_week", "is_weekend", "month",
    "sin_hour", "cos_hour",
]


def prepare(frame: pd.DataFrame) -> pd.DataFrame:
    dt = pd.to_datetime(frame["datetime"], utc=True)
    frame = frame.copy()
    frame["hour"] = dt.dt.hour
    frame["day_of_week"] = dt.dt.dayofweek
    frame["is_weekend"] = (frame["day_of_week"] >= 5).astype(int)
    frame["month"] = dt.dt.month
    frame["sin_hour"] = np.sin(2 * np.pi * frame["hour"] / 24)
    frame["cos_hour"] = np.cos(2 * np.pi * frame["hour"] / 24)
    return frame


def main() -> None:
    init_db()
    frame = query_df("SELECT * FROM traffic_observations ORDER BY datetime")
    frame = prepare(frame)
    split = int(len(frame) * 0.8)
    train, test = frame.iloc[:split], frame.iloc[split:]
    x_train, x_test = train[FEATURES], test[FEATURES]

    models = {
        "volume": RandomForestRegressor(n_estimators=120, random_state=RANDOM_SEED, n_jobs=-1, max_depth=16),
        "travel_time": RandomForestRegressor(n_estimators=120, random_state=RANDOM_SEED, n_jobs=-1, max_depth=16),
        "congestion": RandomForestClassifier(n_estimators=120, random_state=RANDOM_SEED, n_jobs=-1, class_weight="balanced"),
        "accident_risk": RandomForestClassifier(n_estimators=120, random_state=RANDOM_SEED, n_jobs=-1, class_weight="balanced"),
    }
    targets = {
        "volume": train["predicted_volume"],
        "travel_time": train["predicted_travel_time"],
        "congestion": train["predicted_congestion"],
        "accident_risk": (train["predicted_accident_risk"] >= 0.55).astype(int),
    }
    for name, model in models.items():
        print(f"Training {name}...")
        model.fit(x_train, targets[name])
        joblib.dump(model, MODEL_DIR / f"{name}_model.joblib")

    volume_pred = models["volume"].predict(x_test)
    travel_pred = models["travel_time"].predict(x_test)
    congestion_pred = models["congestion"].predict(x_test)
    risk_true = (test["predicted_accident_risk"] >= 0.55).astype(int)
    risk_pred = models["accident_risk"].predict(x_test)
    risk_proba = models["accident_risk"].predict_proba(x_test)[:, 1]

    metrics = {
        "traffic_volume": {
            "mae": float(mean_absolute_error(test["predicted_volume"], volume_pred)),
            "rmse": float(mean_squared_error(test["predicted_volume"], volume_pred) ** 0.5),
            "r2": float(r2_score(test["predicted_volume"], volume_pred)),
        },
        "travel_time": {
            "mae": float(mean_absolute_error(test["predicted_travel_time"], travel_pred)),
            "rmse": float(mean_squared_error(test["predicted_travel_time"], travel_pred) ** 0.5),
            "r2": float(r2_score(test["predicted_travel_time"], travel_pred)),
        },
        "congestion": {
            "accuracy": float(accuracy_score(test["predicted_congestion"], congestion_pred)),
            "f1_macro": float(f1_score(test["predicted_congestion"], congestion_pred, average="macro")),
        },
        "accident_risk": {
            "accuracy": float(accuracy_score(risk_true, risk_pred)),
            "f1": float(f1_score(risk_true, risk_pred, zero_division=0)),
            "roc_auc": float(roc_auc_score(risk_true, risk_proba)),
        },
    }

    importance = models["volume"].feature_importances_
    feature_importance = sorted(
        [{"feature": feature, "importance": round(float(value), 5)} for feature, value in zip(FEATURES, importance)],
        key=lambda item: item["importance"], reverse=True,
    )
    registry = {
        "model_version": "demo-rf-1.0",
        "forecast_horizons_minutes": [30, 60, 90, 120, 180],
        "feature_order": FEATURES,
        "models": {
            "volume": "volume_model.joblib",
            "travel_time": "travel_time_model.joblib",
            "congestion": "congestion_model.joblib",
            "accident_risk": "accident_risk_model.joblib"
        },
        "metrics": metrics,
        "feature_importance": feature_importance,
    }
    REGISTRY_PATH.write_text(json.dumps(registry, indent=2), encoding="utf-8")
    print("Models saved. Restart the API to load them.")


if __name__ == "__main__":
    main()
