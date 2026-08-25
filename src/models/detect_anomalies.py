"""
Phase 5 — Anomaly detection.

Runs Isolation Forest over the point-forecast residuals (actual - forecast)
to flag series-days where actual demand deviated from what the model
expected in a way that looks anomalous, not just "a bit off". This is a
distinct signal from stockout risk: risk is about future demand exceeding
inventory, anomaly is about the model being surprised by what happened.

Features used: the residual itself, plus its magnitude relative to that
series' own rolling volatility, so a "big" residual on a naturally spiky
series isn't flagged as aggressively as the same residual on a stable one.

Run:
    python -m src.models.detect_anomalies
"""

import mlflow
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from src import config

CONTAMINATION = 0.03  # expect ~3% of series-days to be genuinely anomalous


def build_anomaly_features(residuals: pd.DataFrame) -> pd.DataFrame:
    df = residuals.copy()
    df = df.sort_values(["item_id", "store_id", "date"])

    # rolling volatility of residuals per series, used to normalize magnitude
    df["resid_roll_std"] = (
        df.groupby(["item_id", "store_id"])["residual"]
        .transform(lambda s: s.rolling(14, min_periods=5).std())
    )
    df["resid_roll_std"] = df["resid_roll_std"].fillna(df["residual"].std())
    df["resid_roll_std"] = df["resid_roll_std"].replace(0, df["residual"].std())

    df["normalized_residual"] = df["residual"] / df["resid_roll_std"]
    df["abs_residual"] = df["residual"].abs()

    return df


def train() -> IsolationForest:
    mlflow.set_tracking_uri(config.MLFLOW_TRACKING_URI)
    mlflow.set_experiment(config.MLFLOW_EXPERIMENT)

    residuals_path = config.ROOT / "data" / "val_residuals.parquet"
    if not residuals_path.exists():
        raise FileNotFoundError(
            "val_residuals.parquet not found — run train_forecast.py first."
        )
    residuals = pd.read_parquet(residuals_path)

    df = build_anomaly_features(residuals)
    feature_cols = ["residual", "normalized_residual", "abs_residual"]

    with mlflow.start_run(run_name="isolation_forest_anomalies"):
        mlflow.log_param("contamination", CONTAMINATION)
        mlflow.log_param("features", feature_cols)

        model = IsolationForest(
            n_estimators=200,
            contamination=CONTAMINATION,
            random_state=42,
        )
        # -1 = anomaly, 1 = normal -> convert to a clean 0/1 flag
        raw_pred = model.fit_predict(df[feature_cols])
        df["anomaly_flag"] = (raw_pred == -1).astype(int)
        df["anomaly_score"] = model.decision_function(df[feature_cols])  # lower = more anomalous

        anomaly_rate = float(df["anomaly_flag"].mean())
        mlflow.log_metric("anomaly_rate", anomaly_rate)
        print(f"Flagged {anomaly_rate:.1%} of series-days as anomalous")

        mlflow.sklearn.log_model(model, artifact_path="model", registered_model_name="demand_anomaly_iforest")

        df[[
            "item_id", "store_id", "date", "residual",
            "normalized_residual", "anomaly_flag", "anomaly_score",
        ]].to_parquet(config.ROOT / "data" / "val_anomalies.parquet")

    return model


if __name__ == "__main__":
    train()
