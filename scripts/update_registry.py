from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from sklearn.metrics import (
    mean_absolute_error,
    mean_squared_error,
    r2_score,
)


# ---------------------------------------------------------
# Project paths
# ---------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[1]

ARTIFACT_DIR = PROJECT_ROOT / "model_artifacts"

BUNDLE_PATH = (
    ARTIFACT_DIR
    / "flowcast_tabular_bundle.joblib"
)

REGISTRY_PATH = (
    ARTIFACT_DIR
    / "registry.json"
)

REGRESSION_RESULTS_PATH = (
    PROJECT_ROOT
    / "data"
    / "exports"
    / "regression_model_results.csv"
)

CLASSIFICATION_RESULTS_PATH = (
    PROJECT_ROOT
    / "data"
    / "exports"
    / "classification_model_results.csv"
)

LSTM_RESULTS_PATH = (
    PROJECT_ROOT
    / "data"
    / "exports"
    / "lstm_predictions_with_uncertainty.csv"
)


# ---------------------------------------------------------
# Helper functions
# ---------------------------------------------------------

def require_file(
    file_path: Path,
    description: str
) -> None:
    if not file_path.exists():
        raise FileNotFoundError(
            f"{description} not found:\n{file_path}"
        )


def get_metric_value(
    row: pd.Series,
    possible_column_names: list[str]
) -> float | None:

    for column_name in possible_column_names:

        if column_name not in row.index:
            continue

        value = row[column_name]

        if pd.notna(value):
            return float(value)

    return None


def find_result_row(
    results_df: pd.DataFrame,
    target_name: str,
    model_name: str
) -> pd.Series | None:

    required_columns = [
        "Target",
        "Model"
    ]

    for column in required_columns:
        if column not in results_df.columns:
            raise KeyError(
                f"Required column '{column}' is missing.\n"
                f"Available columns: "
                f"{results_df.columns.tolist()}"
            )

    target_values = (
        results_df["Target"]
        .astype(str)
        .str.strip()
        .str.casefold()
    )

    model_values = (
        results_df["Model"]
        .astype(str)
        .str.strip()
        .str.casefold()
    )

    matching_rows = results_df[
        (
            target_values
            == target_name.strip().casefold()
        )
        &
        (
            model_values
            == model_name.strip().casefold()
        )
    ]

    if matching_rows.empty:
        print(
            f"Warning: No result found for "
            f"target='{target_name}', "
            f"model='{model_name}'."
        )

        return None

    return matching_rows.iloc[0]


def get_regression_metrics(
    results_df: pd.DataFrame,
    target_name: str,
    model_name: str
) -> dict[str, float | None]:

    row = find_result_row(
        results_df=results_df,
        target_name=target_name,
        model_name=model_name
    )

    if row is None:
        return {
            "mae": None,
            "rmse": None,
            "r2": None
        }

    return {
        "mae": get_metric_value(
            row,
            ["MAE", "mae"]
        ),

        "rmse": get_metric_value(
            row,
            ["RMSE", "rmse"]
        ),

        "r2": get_metric_value(
            row,
            [
                "R2",
                "R²",
                "r2",
                "R_Squared"
            ]
        )
    }


def get_classification_metrics(
    results_df: pd.DataFrame,
    target_name: str,
    model_name: str
) -> dict[str, float | None]:

    row = find_result_row(
        results_df=results_df,
        target_name=target_name,
        model_name=model_name
    )

    if row is None:
        return {
            "accuracy": None,
            "balanced_accuracy": None,
            "f1_macro": None,
            "roc_auc": None
        }

    return {
        "accuracy": get_metric_value(
            row,
            [
                "Accuracy",
                "accuracy"
            ]
        ),

        "balanced_accuracy": get_metric_value(
            row,
            [
                "Balanced Accuracy",
                "balanced_accuracy",
                "Balanced_Accuracy"
            ]
        ),

        "f1_macro": get_metric_value(
            row,
            [
                "Macro F1",
                "F1 Macro",
                "f1_macro",
                "Macro_F1"
            ]
        ),

        "roc_auc": get_metric_value(
            row,
            [
                "ROC AUC",
                "ROC_AUC",
                "roc_auc"
            ]
        )
    }


def get_lstm_metrics(
    results_path: Path
) -> dict[str, float | None]:

    if not results_path.exists():
        print(
            "Warning: LSTM prediction file not found:",
            results_path
        )

        return {
            "mae": None,
            "rmse": None,
            "r2": None
        }

    results_df = pd.read_csv(results_path)

    required_columns = [
        "actual_traffic_volume",
        "predicted_traffic_volume"
    ]

    missing_columns = [
        column
        for column in required_columns
        if column not in results_df.columns
    ]

    if missing_columns:
        print(
            "Warning: Missing LSTM columns:",
            missing_columns
        )

        print(
            "Available columns:",
            results_df.columns.tolist()
        )

        return {
            "mae": None,
            "rmse": None,
            "r2": None
        }

    evaluation_df = results_df[
        required_columns
    ].copy()

    for column in required_columns:
        evaluation_df[column] = pd.to_numeric(
            evaluation_df[column],
            errors="coerce"
        )

    evaluation_df = evaluation_df.dropna()

    if evaluation_df.empty:
        print(
            "Warning: No valid LSTM prediction rows found."
        )

        return {
            "mae": None,
            "rmse": None,
            "r2": None
        }

    actual = evaluation_df[
        "actual_traffic_volume"
    ].to_numpy()

    predicted = evaluation_df[
        "predicted_traffic_volume"
    ].to_numpy()

    mae = mean_absolute_error(
        actual,
        predicted
    )

    rmse = np.sqrt(
        mean_squared_error(
            actual,
            predicted
        )
    )

    r2 = r2_score(
        actual,
        predicted
    )

    return {
        "mae": round(float(mae), 6),
        "rmse": round(float(rmse), 6),
        "r2": round(float(r2), 6)
    }


# ---------------------------------------------------------
# Main program
# ---------------------------------------------------------

def main() -> None:

    require_file(
        BUNDLE_PATH,
        "Tabular model bundle"
    )

    require_file(
        REGRESSION_RESULTS_PATH,
        "Regression results CSV"
    )

    require_file(
        CLASSIFICATION_RESULTS_PATH,
        "Classification results CSV"
    )

    bundle = joblib.load(
        BUNDLE_PATH
    )

    regression_results = pd.read_csv(
        REGRESSION_RESULTS_PATH
    )

    classification_results = pd.read_csv(
        CLASSIFICATION_RESULTS_PATH
    )

    best_regression = bundle.get(
        "best_regression_names",
        {}
    )

    best_classification = bundle.get(
        "best_classification_names",
        {}
    )

    traffic_model_name = str(
        best_regression.get(
            "target_traffic_volume",
            "Unknown"
        )
    )

    travel_model_name = str(
        best_regression.get(
            "target_travel_time",
            "Unknown"
        )
    )

    congestion_model_name = str(
        best_classification.get(
            "target_congestion_level",
            "Unknown"
        )
    )

    accident_model_name = str(
        best_classification.get(
            "target_accident_risk",
            "Unknown"
        )
    )

    traffic_metrics = get_regression_metrics(
        results_df=regression_results,
        target_name="target_traffic_volume",
        model_name=traffic_model_name
    )

    travel_metrics = get_regression_metrics(
        results_df=regression_results,
        target_name="target_travel_time",
        model_name=travel_model_name
    )

    congestion_all_metrics = (
        get_classification_metrics(
            results_df=classification_results,
            target_name="target_congestion_level",
            model_name=congestion_model_name
        )
    )

    accident_metrics = get_classification_metrics(
        results_df=classification_results,
        target_name="target_accident_risk",
        model_name=accident_model_name
    )

    lstm_metrics = get_lstm_metrics(
        LSTM_RESULTS_PATH
    )

    congestion_metrics = {
        "accuracy": congestion_all_metrics[
            "accuracy"
        ],

        "balanced_accuracy": (
            congestion_all_metrics[
                "balanced_accuracy"
            ]
        ),

        "f1_macro": congestion_all_metrics[
            "f1_macro"
        ]
    }

    registry = {
        "schema_version": "1.0",
        "project": "FlowCast",
        "version": "1.0.0",
        "serving_strategy": "hybrid",

        "primary_artifact": (
            "flowcast_tabular_bundle.joblib"
        ),

        "models": {
            "traffic_volume": {
                "task": "regression",
                "serving_role": "primary",
                "input_mode": "single_window",
                "algorithm": traffic_model_name,

                "artifact": (
                    "flowcast_tabular_bundle.joblib"
                ),

                "target": "target_traffic_volume",
                "metrics": traffic_metrics
            },

            "travel_time": {
                "task": "regression",
                "serving_role": "primary",
                "input_mode": "single_window",
                "algorithm": travel_model_name,

                "artifact": (
                    "flowcast_tabular_bundle.joblib"
                ),

                "target": "target_travel_time",
                "metrics": travel_metrics
            },

            "congestion": {
                "task": "classification",
                "serving_role": "primary",
                "input_mode": "single_window",
                "algorithm": congestion_model_name,

                "artifact": (
                    "flowcast_tabular_bundle.joblib"
                ),

                "target": "target_congestion_level",
                "metrics": congestion_metrics
            },

            "accident_risk": {
                "task": "classification",
                "serving_role": "primary",
                "input_mode": "single_window",
                "algorithm": accident_model_name,

                "artifact": (
                    "flowcast_tabular_bundle.joblib"
                ),

                "target": "target_accident_risk",
                "metrics": accident_metrics
            },

            "traffic_volume_lstm": {
                "task": "sequence_regression",
                "serving_role": "secondary",

                "input_mode": (
                    "12_consecutive_windows"
                ),

                "algorithm": "LSTM",

                "artifact": (
                    "flowcast_traffic_lstm.keras"
                ),

                "feature_scaler": (
                    "lstm_feature_scaler.joblib"
                ),

                "target_scaler": (
                    "lstm_target_scaler.joblib"
                ),

                "metadata": (
                    "lstm_metadata.joblib"
                ),

                "sequence_length": 12,
                "window_minutes": 30,
                "forecast_horizon_minutes": 30,

                "metrics": lstm_metrics
            }
        }
    }

    ARTIFACT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    with REGISTRY_PATH.open(
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            registry,
            file,
            indent=2,
            ensure_ascii=False
        )

    print()
    print("Registry updated successfully.")
    print("Registry path:", REGISTRY_PATH)

    print()
    print("Selected regression models:")
    print(best_regression)

    print()
    print("Selected classification models:")
    print(best_classification)

    print()
    print("Traffic-volume metrics:")
    print(traffic_metrics)

    print()
    print("Travel-time metrics:")
    print(travel_metrics)

    print()
    print("Congestion metrics:")
    print(congestion_metrics)

    print()
    print("Accident-risk metrics:")
    print(accident_metrics)

    print()
    print("LSTM metrics:")
    print(lstm_metrics)


if __name__ == "__main__":
    main()