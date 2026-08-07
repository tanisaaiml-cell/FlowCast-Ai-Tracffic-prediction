"""Model loading, inference, deterministic fallback, and prediction lineage."""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from app.config import (
    MODEL_DIR,
    RANDOM_SEED,
    REGISTRY_PATH,
)


LOGGER = logging.getLogger(__name__)

CONGESTION_ORDER = [
    "Low",
    "Moderate",
    "High",
    "Severe",
]


class ModelService:
    """Load FlowCast artifacts and expose unified prediction methods."""

    def __init__(self) -> None:
        self.registry = self._load_registry()

        self.models: dict[str, Any] = {}
        self.load_errors: list[str] = []

        self.tabular_bundle: dict[str, Any] | None = None

        self.lstm_model: Any | None = None
        self.lstm_feature_scaler: Any | None = None
        self.lstm_target_scaler: Any | None = None
        self.lstm_metadata: dict[str, Any] | None = None

        self._load_models()

    # -----------------------------------------------------
    # General properties
    # -----------------------------------------------------

    @property
    def model_version(self) -> str:
        return str(
            self.registry.get(
                "version",
                self.registry.get(
                    "model_version",
                    "demo-1.0",
                ),
            )
        )

    @property
    def using_demo_fallback(self) -> bool:
        return self.tabular_bundle is None

    # -----------------------------------------------------
    # Registry loading
    # -----------------------------------------------------

    def _load_registry(self) -> dict[str, Any]:
        if not REGISTRY_PATH.exists():
            LOGGER.warning(
                "Registry file not found: %s",
                REGISTRY_PATH,
            )

            return {
                "schema_version": "1.0",
                "project": "FlowCast",
                "version": "demo-1.0",
                "serving_strategy": "fallback",
                "models": {},
            }

        try:
            registry_text = REGISTRY_PATH.read_text(
                encoding="utf-8"
            )

            registry = json.loads(registry_text)

        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Invalid JSON inside registry file: "
                f"{REGISTRY_PATH}"
            ) from exc

        if not isinstance(registry, dict):
            raise TypeError(
                "The model registry must contain a JSON object."
            )

        return registry

    # -----------------------------------------------------
    # Artifact loading
    # -----------------------------------------------------

    def _record_load_error(
        self,
        message: str,
    ) -> None:
        self.load_errors.append(message)
        LOGGER.warning(message)

    def _load_models(self) -> None:
        """
        Load the saved tabular bundle and optional LSTM artifacts.

        The four primary prediction targets all use models stored
        inside flowcast_tabular_bundle.joblib.

        The LSTM remains a separate sequence model.
        """

        model_configs = self.registry.get(
            "models",
            {},
        )

        if not isinstance(model_configs, dict):
            raise TypeError(
                "registry.json field 'models' must be an object."
            )

        # -------------------------------------------------
        # Load the primary tabular bundle once
        # -------------------------------------------------

        primary_artifact = self.registry.get(
            "primary_artifact",
            "flowcast_tabular_bundle.joblib",
        )

        bundle_path = MODEL_DIR / str(
            primary_artifact
        )

        if bundle_path.exists():
            try:
                loaded_bundle = joblib.load(
                    bundle_path
                )

                if not isinstance(
                    loaded_bundle,
                    dict,
                ):
                    raise TypeError(
                        "The tabular bundle must be a dictionary."
                    )

                self.tabular_bundle = loaded_bundle

                self._register_tabular_models(
                    loaded_bundle
                )

                LOGGER.info(
                    "Loaded FlowCast tabular bundle: %s",
                    bundle_path,
                )

            except Exception as exc:
                self._record_load_error(
                    "Could not load tabular bundle "
                    f"'{bundle_path}': {exc}"
                )

        else:
            self._record_load_error(
                f"Tabular bundle not found: {bundle_path}"
            )

        # -------------------------------------------------
        # Load optional LSTM model and supporting artifacts
        # -------------------------------------------------

        lstm_config = model_configs.get(
            "traffic_volume_lstm",
            {},
        )

        if isinstance(lstm_config, dict):
            self._load_lstm_artifacts(
                lstm_config
            )

    def _register_tabular_models(
        self,
        bundle: dict[str, Any],
    ) -> None:
        """Expose selected models from the loaded bundle."""

        regression_models = bundle.get(
            "regression_models",
            {},
        )

        classification_models = bundle.get(
            "classification_models",
            {},
        )

        if isinstance(regression_models, dict):
            traffic_model = regression_models.get(
                "target_traffic_volume"
            )

            travel_model = regression_models.get(
                "target_travel_time"
            )

            if traffic_model is not None:
                self.models[
                    "traffic_volume"
                ] = traffic_model

            if travel_model is not None:
                self.models[
                    "travel_time"
                ] = travel_model

        if isinstance(classification_models, dict):
            congestion_model = (
                classification_models.get(
                    "congestion"
                )
            )

            accident_model = (
                classification_models.get(
                    "accident"
                )
            )

            if congestion_model is not None:
                self.models[
                    "congestion"
                ] = congestion_model

            if accident_model is not None:
                self.models[
                    "accident_risk"
                ] = accident_model

    def _load_lstm_artifacts(
        self,
        lstm_config: dict[str, Any],
    ) -> None:
        """Load the optional LSTM model and its supporting files."""

        model_filename = lstm_config.get(
            "artifact"
        )

        if model_filename:
            model_path = (
                MODEL_DIR / str(model_filename)
            )

            if model_path.exists():
                try:
                    import tensorflow as tf

                    self.lstm_model = (
                        tf.keras.models.load_model(
                            model_path,
                            compile=False
                        )
                    )

                    self.models[
                        "traffic_volume_lstm"
                    ] = self.lstm_model

                    LOGGER.info(
                        "Loaded LSTM model: %s",
                        model_path,
                    )

                except ImportError:
                    self._record_load_error(
                        "TensorFlow is not installed, so the "
                        "LSTM model was not loaded. The primary "
                        "tabular models can still be used."
                    )

                except Exception as exc:
                    self._record_load_error(
                        "Could not load LSTM model "
                        f"'{model_path}': {exc}"
                    )

            else:
                self._record_load_error(
                    f"LSTM model not found: {model_path}"
                )

        support_files = {
            "feature_scaler": (
                "lstm_feature_scaler"
            ),
            "target_scaler": (
                "lstm_target_scaler"
            ),
            "metadata": (
                "lstm_metadata"
            ),
        }

        for registry_key, attribute_name in (
            support_files.items()
        ):
            filename = lstm_config.get(
                registry_key
            )

            if not filename:
                continue

            artifact_path = (
                MODEL_DIR / str(filename)
            )

            if not artifact_path.exists():
                self._record_load_error(
                    "LSTM supporting artifact not found: "
                    f"{artifact_path}"
                )
                continue

            try:
                loaded_artifact = joblib.load(
                    artifact_path
                )

                setattr(
                    self,
                    attribute_name,
                    loaded_artifact,
                )

            except Exception as exc:
                self._record_load_error(
                    "Could not load LSTM supporting "
                    f"artifact '{artifact_path}': {exc}"
                )

    # -----------------------------------------------------
    # Main prediction method
    # -----------------------------------------------------

    def predict_dataframe(
        self,
        frame: pd.DataFrame,
        source: str = "api",
    ) -> pd.DataFrame:
        """Predict all four FlowCast targets."""

        if frame.empty:
            raise ValueError(
                "Prediction input cannot be empty."
            )

        prepared_data = self._prepare_features(
            frame.copy()
        )

        if self.tabular_bundle is not None:
            try:
                predictions = (
                    self._predict_with_loaded_models(
                        prepared_data
                    )
                )

            except Exception as exc:
                LOGGER.exception(
                    "Saved-model inference failed. "
                    "Using deterministic fallback."
                )

                self.load_errors.append(
                    f"Prediction error: {exc}"
                )

                predictions = (
                    self._predict_with_deterministic_fallback(
                        prepared_data
                    )
                )

        else:
            predictions = (
                self._predict_with_deterministic_fallback(
                    prepared_data
                )
            )

        run_id = str(uuid.uuid4())

        created_at = datetime.now(
            timezone.utc
        ).isoformat()

        result = frame.copy()

        result["predicted_volume"] = (
            predictions["predicted_volume"]
            .clip(lower=0)
            .round(2)
        )

        result["predicted_travel_time"] = (
    pd.to_numeric(
        predictions["predicted_travel_time"],
        errors="coerce"
    )
    .fillna(0.1)
    .clip(lower=0.1)
    .round(2)
)

        result["predicted_congestion"] = (
            predictions[
                "predicted_congestion"
            ]
        )

        result["predicted_accident_risk"] = (
            predictions[
                "predicted_accident_risk"
            ]
            .clip(0, 1)
            .round(4)
        )

        result["confidence"] = (
            predictions["confidence"]
            .clip(0, 0.99)
            .round(3)
        )

        result["prediction_id"] = [
            str(uuid.uuid4())
            for _ in range(len(result))
        ]

        result["run_id"] = run_id
        result["model_version"] = self.model_version
        result["source"] = source
        result["created_at"] = created_at

        result["input_hash"] = result.apply(
            self._row_hash,
            axis=1,
        )

        return result

    # -----------------------------------------------------
    # Input preparation
    # -----------------------------------------------------

    @staticmethod
    def _numeric_series(
        frame: pd.DataFrame,
        column: str,
        default: float = 0.0,
    ) -> pd.Series:
        if column not in frame.columns:
            return pd.Series(
                default,
                index=frame.index,
                dtype=float,
            )

        values = pd.to_numeric(
            frame[column],
            errors="coerce",
        )

        return values.fillna(default)

    @staticmethod
    def _copy_alias(
        frame: pd.DataFrame,
        target: str,
        aliases: list[str],
        default: Any,
    ) -> None:
        if target in frame.columns:
            return

        for alias in aliases:
            if alias in frame.columns:
                frame[target] = frame[alias]
                return

        frame[target] = default

    def _prepare_features(
        self,
        frame: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        Standardize API fields.

        This supports both the web API names and the original
        FlowCast training-column names.
        """

        self._copy_alias(
            frame,
            "segment_id",
            ["road_id"],
            "Unknown",
        )

        self._copy_alias(
            frame,
            "speed_kmh",
            ["avg_speed"],
            45.0,
        )

        self._copy_alias(
            frame,
            "volume",
            ["traffic_volume"],
            0.0,
        )

        self._copy_alias(
            frame,
            "temp_c",
            ["temperature"],
            20.0,
        )

        self._copy_alias(
            frame,
            "rain_mm",
            ["rainfall"],
            0.0,
        )

        self._copy_alias(
            frame,
            "visibility_km",
            ["visibility"],
            10.0,
        )

        self._copy_alias(
            frame,
            "distance_km",
            [],
            2.5,
        )

        self._copy_alias(
            frame,
            "event_flag",
            [],
            0,
        )

        self._copy_alias(
            frame,
            "occupancy",
            [],
            0.30,
        )

        if "datetime" not in frame.columns:
            frame["datetime"] = datetime.now(
                timezone.utc
            ).isoformat()

        datetime_values = pd.to_datetime(
            frame["datetime"],
            errors="coerce",
            utc=True,
        )

        current_timestamp = pd.Timestamp.now(
            tz="UTC"
        )

        datetime_values = (
            datetime_values.fillna(
                current_timestamp
            )
        )

        frame["hour"] = datetime_values.dt.hour
        frame["minute"] = datetime_values.dt.minute
        frame["day_of_week"] = (
            datetime_values.dt.dayofweek
        )
        frame["month"] = datetime_values.dt.month

        frame["is_weekend"] = (
            frame["day_of_week"] >= 5
        ).astype(int)

        frame["is_peak_hour"] = (
            frame["hour"].isin(
                [7, 8, 9, 17, 18, 19]
            )
        ).astype(int)

        frame["sin_hour"] = np.sin(
            2 * np.pi * frame["hour"] / 24
        )

        frame["cos_hour"] = np.cos(
            2 * np.pi * frame["hour"] / 24
        )

        return frame

    # -----------------------------------------------------
    # Saved tabular-model inference
    # -----------------------------------------------------

    def _build_tabular_input(
        self,
        data: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        Convert API fields into the columns used during Colab training.
        """

        if self.tabular_bundle is None:
            raise RuntimeError(
                "The tabular model bundle is not loaded."
            )

        feature_columns = self.tabular_bundle.get(
            "feature_columns",
            [],
        )

        if not feature_columns:
            raise KeyError(
                "The model bundle does not contain "
                "'feature_columns'."
            )

        model_input = pd.DataFrame(
            index=data.index
        )

        speed = self._numeric_series(
            data,
            "speed_kmh",
            45.0,
        )

        volume = self._numeric_series(
            data,
            "volume",
            0.0,
        )

        occupancy = self._numeric_series(
            data,
            "occupancy",
            0.30,
        )

        # API occupancy may be 0–1, while training occupancy
        # was stored as a percentage.
        occupancy_percentage = occupancy.copy()

        ratio_mask = (
            occupancy_percentage.abs() <= 1.5
        )

        occupancy_percentage.loc[
            ratio_mask
        ] = (
            occupancy_percentage.loc[
                ratio_mask
            ]
            * 100
        )

        rain = self._numeric_series(
            data,
            "rain_mm",
            0.0,
        )

        visibility_km = self._numeric_series(
            data,
            "visibility_km",
            10.0,
        )

        distance = self._numeric_series(
            data,
            "distance_km",
            2.5,
        )

        current_travel_time = (
            distance
            / speed.clip(lower=5)
            * 60
        )

        road_capacity = self._numeric_series(
            data,
            "road_capacity",
            1800.0,
        )

        weather_condition = np.where(
            rain > 0,
            "Rain",
            "Clear",
        )

        congestion_level = np.where(
            occupancy_percentage >= 70,
            "Heavy",
            np.where(
                occupancy_percentage >= 40,
                "Moderate",
                "Free-flow",
            ),
        )

        values: dict[str, Any] = {
            "road_id": (
                data["segment_id"]
                .fillna("Unknown")
                .astype(str)
            ),

            "latitude": (
                self._numeric_series(
                    data,
                    "latitude",
                    np.nan,
                )
            ),

            "longitude": (
                self._numeric_series(
                    data,
                    "longitude",
                    np.nan,
                )
            ),

            "traffic_volume": volume,
            "avg_speed": speed,
            "occupancy": occupancy_percentage,

            "travel_time": self._numeric_series(
                data,
                "travel_time",
                0.0,
            ),

            "accident_count": self._numeric_series(
                data,
                "accident_count",
                0.0,
            ),

            "signal_timing": self._numeric_series(
                data,
                "signal_timing",
                45.0,
            ),

            "road_capacity": road_capacity,

            "temperature": self._numeric_series(
                data,
                "temp_c",
                20.0,
            ),

            "rainfall": rain,

            # Training visibility was approximately in metres.
            "visibility": visibility_km * 1000,

            "public_holiday": self._numeric_series(
                data,
                "public_holiday",
                0.0,
            ),

            "event_flag": self._numeric_series(
                data,
                "event_flag",
                0.0,
            ),

            "roadwork_flag": self._numeric_series(
                data,
                "roadwork_flag",
                0.0,
            ),

            "hour": data["hour"],
            "minute": data["minute"],
            "day_of_week": data["day_of_week"],
            "month": data["month"],
            "is_weekend": data["is_weekend"],
            "is_peak_hour": data["is_peak_hour"],

            "weather_condition": (
                data["weather_condition"]
                if "weather_condition" in data.columns
                else pd.Series(
                    weather_condition,
                    index=data.index,
                )
            ),

            "congestion_level": (
                data["congestion_level"]
                if "congestion_level" in data.columns
                else pd.Series(
                    congestion_level,
                    index=data.index,
                )
            ),
        }

        for column in feature_columns:
            if column in values:
                model_input[column] = values[column]

            elif column in data.columns:
                model_input[column] = data[column]

            else:
                model_input[column] = np.nan

        return model_input[
            feature_columns
        ]

    def _predict_with_loaded_models(
        self,
        data: pd.DataFrame,
    ) -> pd.DataFrame:
        """Run the four selected tabular models."""

        if self.tabular_bundle is None:
            raise RuntimeError(
                "The FlowCast tabular bundle is unavailable."
            )

        preprocessor = self.tabular_bundle.get(
            "preprocessor"
        )

        regression_models = self.tabular_bundle.get(
            "regression_models",
            {},
        )

        classification_models = self.tabular_bundle.get(
            "classification_models",
            {},
        )

        classification_encoders = (
            self.tabular_bundle.get(
                "classification_encoders",
                {},
            )
        )

        if preprocessor is None:
            raise KeyError(
                "The bundle does not contain 'preprocessor'."
            )

        tabular_input = self._build_tabular_input(
            data
        )

        transformed_input = preprocessor.transform(
            tabular_input
        )

        traffic_model = regression_models.get(
            "target_traffic_volume"
        )

        travel_model = regression_models.get(
            "target_travel_time"
        )

        congestion_model = (
            classification_models.get(
                "congestion"
            )
        )

        accident_model = (
            classification_models.get(
                "accident"
            )
        )

        required_models = {
            "traffic-volume model": traffic_model,
            "travel-time model": travel_model,
            "congestion model": congestion_model,
            "accident-risk model": accident_model,
        }

        missing_models = [
            name
            for name, model in required_models.items()
            if model is None
        ]

        if missing_models:
            raise KeyError(
                "Missing models inside the tabular bundle: "
                + ", ".join(missing_models)
            )

        predicted_volume = np.maximum(
            traffic_model.predict(
                transformed_input
            ),
            0,
        )

        predicted_travel_time = np.maximum(
            travel_model.predict(
                transformed_input
            ),
            0,
        )

        congestion_encoded = (
            congestion_model.predict(
                transformed_input
            )
        )

        congestion_encoder = (
            classification_encoders.get(
                "target_congestion_level"
            )
        )

        if congestion_encoder is not None:
            predicted_congestion = (
                congestion_encoder.inverse_transform(
                    np.asarray(
                        congestion_encoded,
                        dtype=int,
                    )
                )
            )
        else:
            predicted_congestion = (
                congestion_encoded.astype(str)
            )

        congestion_confidence = (
            self._classification_confidence(
                congestion_model,
                transformed_input,
            )
        )

        accident_probability = (
            self._positive_class_probability(
                model=accident_model,
                transformed_input=transformed_input,
                encoder=classification_encoders.get(
                    "target_accident_risk"
                ),
            )
        )

        accident_confidence = (
            self._classification_confidence(
                accident_model,
                transformed_input,
            )
        )

        confidence = np.mean(
            np.vstack(
                [
                    congestion_confidence,
                    accident_confidence,
                ]
            ),
            axis=0,
        )

        return pd.DataFrame(
            {
                "predicted_volume": predicted_volume,

                "predicted_travel_time": (
                    predicted_travel_time
                ),

                "predicted_congestion": (
                    predicted_congestion
                ),

                "predicted_accident_risk": (
                    accident_probability
                ),

                "confidence": confidence,
            },
            index=data.index,
        )
        
    def diagnostics(self) -> dict[str, Any]:
            """Return model-performance and transparency information."""

            mode = (
            "demo_fallback"
            if self.using_demo_fallback
            else "loaded_artifacts"
            )

            mode_label = (
            "Deterministic demonstration model"
            if self.using_demo_fallback
            else "Trained model artifacts"
         )

            return {
            "model_version": self.model_version,
            "mode": mode,
            "mode_label": mode_label,
            "loaded_models": sorted(self.models.keys()),
            "expected_models": sorted(
                (self.registry.get("models", {}) or {}).keys()
            ),
            "prediction_targets": [
                "Traffic volume",
                "Travel time",
                "Congestion level",
                "Accident risk",
            ],
            "metrics": self.registry.get("metrics", {}),
            "feature_importance": self.registry.get(
                "feature_importance",
                [],
            ),
            "feature_order": self.registry.get(
                "feature_order",
                [],
            ),
            "forecast_horizons_minutes": self.registry.get(
                "forecast_horizons_minutes",
                [30, 60, 90],
            ),
            "seed": RANDOM_SEED,
            "lineage_fields": [
                "prediction_id",
                "run_id",
                "input_hash",
                "model_version",
                "source",
                "created_at",
            ],
            "notes": self.registry.get(
                "notes",
                "No additional model notes are available.",
            ),
            "limitations": [
                (
                    "The current prototype uses a synthetic "
                    "metropolitan traffic dataset."
                ),
                (
                    "Accident-risk probabilities require "
                    "additional calibration and validation."
                ),
                (
                    "Near-term predictions depend on the latest "
                    "available traffic observation."
                ),
                (
                    "SQLite data on free cloud hosting is not "
                    "guaranteed to persist after a restart."
                ),
            ],
        }
    

    @staticmethod
    def _classification_confidence(
        model: Any,
        transformed_input: Any,
    ) -> np.ndarray:
        if hasattr(model, "predict_proba"):
            probabilities = model.predict_proba(
                transformed_input
            )

            return np.max(
                probabilities,
                axis=1,
            )

        if hasattr(model, "decision_function"):
            scores = model.decision_function(
                transformed_input
            )

            scores = np.asarray(scores)

            if scores.ndim == 1:
                probabilities = 1 / (
                    1 + np.exp(-scores)
                )

                return np.maximum(
                    probabilities,
                    1 - probabilities,
                )

        return np.full(
            transformed_input.shape[0],
            0.5,
            dtype=float,
        )

    @staticmethod
    def _positive_class_probability(
        model: Any,
        transformed_input: Any,
        encoder: Any | None,
    ) -> np.ndarray:
        if hasattr(model, "predict_proba"):
            probabilities = model.predict_proba(
                transformed_input
            )

            positive_index = (
                probabilities.shape[1] - 1
            )

            model_classes = getattr(
                model,
                "classes_",
                None,
            )

            if (
                encoder is not None
                and model_classes is not None
            ):
                encoder_classes = [
                    str(value)
                    for value in encoder.classes_
                ]

                positive_candidates = [
                    "1",
                    "true",
                    "yes",
                    "high",
                    "accident",
                ]

                for candidate in positive_candidates:
                    if candidate in encoder_classes:
                        encoded_positive = (
                            encoder.transform(
                                [candidate]
                            )[0]
                        )

                        matching_indexes = np.where(
                            np.asarray(
                                model_classes
                            )
                            == encoded_positive
                        )[0]

                        if len(matching_indexes) > 0:
                            positive_index = int(
                                matching_indexes[0]
                            )
                            break

            return probabilities[
                :,
                positive_index,
            ]

        predictions = model.predict(
            transformed_input
        )

        return np.asarray(
            predictions,
            dtype=float,
        ).clip(0, 1)

    # -----------------------------------------------------
    # Optional LSTM inference
    # -----------------------------------------------------

    def predict_lstm_sequence(
        self,
        frame: pd.DataFrame,
    ) -> float:
        """
        Predict traffic volume from the latest consecutive
        sequence using the separately trained LSTM.
        """

        if self.lstm_model is None:
            raise RuntimeError(
                "The LSTM model is not loaded."
            )

        if self.lstm_feature_scaler is None:
            raise RuntimeError(
                "The LSTM feature scaler is not loaded."
            )

        if self.lstm_target_scaler is None:
            raise RuntimeError(
                "The LSTM target scaler is not loaded."
            )

        metadata = self.lstm_metadata or {}

        sequence_length = int(
            metadata.get(
                "sequence_length",
                12,
            )
        )

        lstm_features = metadata.get(
            "features",
            metadata.get(
                "lstm_features",
                [],
            ),
        )

        if len(frame) < sequence_length:
            raise ValueError(
                f"LSTM inference requires at least "
                f"{sequence_length} consecutive rows."
            )

        if not lstm_features:
            raise KeyError(
                "No LSTM feature list was found in "
                "lstm_metadata.joblib."
            )

        prepared = self._prepare_features(
            frame.copy()
        )

        tabular_values = (
            self._build_training_feature_values(
                prepared,
                lstm_features,
            )
        )

        scaled_values = (
            self.lstm_feature_scaler.transform(
                tabular_values
            )
        )

        sequence = scaled_values[
            -sequence_length:
        ]

        sequence = np.expand_dims(
            sequence,
            axis=0,
        )

        scaled_prediction = (
            self.lstm_model.predict(
                sequence,
                verbose=0,
            )
        )

        prediction = (
            self.lstm_target_scaler.inverse_transform(
                scaled_prediction.reshape(-1, 1)
            )
            .ravel()[0]
        )

        return max(
            float(prediction),
            0.0,
        )

    def _build_training_feature_values(
        self,
        data: pd.DataFrame,
        feature_names: list[str],
    ) -> pd.DataFrame:
        """
        Build numeric feature values for LSTM inference.
        """

        standard_input = self._build_tabular_input(
            data
        )

        result = pd.DataFrame(
            index=data.index
        )

        for feature in feature_names:
            if feature in standard_input.columns:
                result[feature] = pd.to_numeric(
                    standard_input[feature],
                    errors="coerce",
                )

            elif feature in data.columns:
                result[feature] = pd.to_numeric(
                    data[feature],
                    errors="coerce",
                )

            else:
                result[feature] = np.nan

        result = result.ffill().bfill().fillna(0)

        return result[
            feature_names
        ]

    # -----------------------------------------------------
    # Deterministic fallback inference
    # -----------------------------------------------------

    def _predict_with_deterministic_fallback(
        self,
        data: pd.DataFrame,
    ) -> pd.DataFrame:
        hour = self._numeric_series(
            data,
            "hour",
            12,
        )

        morning_peak = np.exp(
            -((hour - 9) ** 2) / 4.5
        )

        evening_peak = np.exp(
            -((hour - 18) ** 2) / 5.0
        )

        rain = self._numeric_series(
            data,
            "rain_mm",
            0,
        )

        event_flag = self._numeric_series(
            data,
            "event_flag",
            0,
        )

        volume = self._numeric_series(
            data,
            "volume",
            0,
        )

        weather_penalty = rain * 0.018
        event_boost = event_flag * 0.32

        predicted_volume = (
            volume
            * (
                1
                + 0.20 * morning_peak
                + 0.26 * evening_peak
                + event_boost
                - weather_penalty
            )
        ).clip(lower=0)

        speed = self._numeric_series(
            data,
            "speed_kmh",
            45,
        ).clip(lower=5)

        occupancy = self._numeric_series(
            data,
            "occupancy",
            0.3,
        )

        occupancy = np.where(
            occupancy > 1,
            occupancy / 100,
            occupancy,
        )

        occupancy = pd.Series(
            occupancy,
            index=data.index,
        ).clip(0, 1)

        distance = self._numeric_series(
            data,
            "distance_km",
            2.5,
        )

        predicted_speed = (
            speed
            * (1 - 0.22 * occupancy)
            - rain * 0.7
        ).clip(lower=6)

        predicted_travel = (
            distance
            / predicted_speed
            * 60
            * (1 + occupancy * 0.25)
        )

        pressure = (
            0.46 * occupancy
            + 0.30 * (
                predicted_volume / 1300
            ).clip(0, 1)
            + 0.10 * morning_peak
            + 0.12 * evening_peak
            + 0.08 * event_flag
        ).clip(0, 1)

        predicted_congestion = pd.cut(
            pressure,
            bins=[
                -0.01,
                0.36,
                0.58,
                0.78,
                1.01,
            ],
            labels=CONGESTION_ORDER,
        ).astype(str)

        visibility = self._numeric_series(
            data,
            "visibility_km",
            10,
        )

        risk = (
            0.03
            + 0.48 * pressure
            + 0.028 * rain
            + 0.025
            * (7 - visibility).clip(lower=0)
            + 0.12 * event_flag
        ).clip(0.01, 0.99)

        confidence = (
            0.92
            - 0.18
            * (pressure - 0.5).abs()
            - 0.02 * rain
        ).clip(0.62, 0.94)

        return pd.DataFrame(
            {
                "predicted_volume": predicted_volume,

                "predicted_travel_time": (
                    predicted_travel
                ),

                "predicted_congestion": (
                    predicted_congestion
                ),

                "predicted_accident_risk": risk,

                "confidence": confidence,
            },
            index=data.index,
        )

    # -----------------------------------------------------
    # Diagnostics
    # -----------------------------------------------------
        
       

    # -----------------------------------------------------
    # Prediction lineage
    # -----------------------------------------------------

    @staticmethod
    def _row_hash(
        row: pd.Series,
    ) -> str:
        keys = [
            "segment_id",
            "road_id",
            "datetime",
            "speed_kmh",
            "avg_speed",
            "volume",
            "traffic_volume",
            "occupancy",
            "temp_c",
            "temperature",
            "rain_mm",
            "rainfall",
            "visibility_km",
            "visibility",
            "event_flag",
            "distance_km",
        ]

        payload = "|".join(
            str(row.get(key, ""))
            for key in keys
        )

        return hashlib.sha256(
            payload.encode("utf-8")
        ).hexdigest()


model_service = ModelService()