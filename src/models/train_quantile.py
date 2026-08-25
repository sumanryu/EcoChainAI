"""
Phase 4 — Quantile risk model.

Trains a LightGBM quantile regressor (alpha=0.9) to estimate P90 demand.
We don't have real inventory data in M5, so "stockout risk" is derived by
comparing P90 demand against a SYNTHETIC on-hand inventory level. This is
a clearly-labeled modeling assumption for the portfolio writeup, not a
claim about real inventory.

Run:
    python -m src.models.train_quantile
"""

import lightgbm as lgb
import mlflow
import numpy as np
import pandas as pd

from src import config
from src.models.common import FEATURE_COLS, TARGET_COL, load_features, time_split

PARAMS = {
    "objective": "quantile",
    "alpha": config.RISK_QUANTILE,
    "metric": "quantile",
    "num_leaves": 128,
    "learning_rate": 0.05,
    "feature_fraction": 0.8,
    "bagging_fraction": 0.8,
    "bagging_freq": 5,
    "min_data_in_leaf": 50,
    "verbose": -1,
}
NUM_BOOST_ROUND = 500
EARLY_STOPPING_ROUNDS = 30


def pinball_loss(y_true: np.ndarray, y_pred: np.ndarray, alpha: float) -> float:
    diff = y_true - y_pred
    return float(np.mean(np.maximum(alpha * diff, (alpha - 1) * diff)))


def simulate_inventory(df: pd.DataFrame, seed: int = 42) -> pd.DataFrame:
    """Synthetic on-hand inventory: rolling 14-day avg demand x a coverage
    factor with noise, clipped to be non-negative. Clearly a stand-in for
    a real inventory feed — swap this for actual ERP data if available."""
    rng = np.random.default_rng(seed)
    coverage_days = rng.uniform(5, 12, size=len(df))
    noise = rng.normal(1.0, 0.15, size=len(df))
    df = df.copy()
    df["on_hand_inventory"] = np.clip(
        df["roll_mean_28"].fillna(df["roll_mean_28"].median()) * coverage_days * noise,
        0, None,
    )
    return df


def train() -> lgb.Booster:
    mlflow.set_tracking_uri(config.MLFLOW_TRACKING_URI)
    mlflow.set_experiment(config.MLFLOW_EXPERIMENT)

    df = load_features()
    train_df, val_df = time_split(df)

    cat_cols = [c for c in FEATURE_COLS if df[c].dtype.name == "category"]
    train_set = lgb.Dataset(train_df[FEATURE_COLS], label=train_df[TARGET_COL], categorical_feature=cat_cols)
    val_set = lgb.Dataset(val_df[FEATURE_COLS], label=val_df[TARGET_COL], categorical_feature=cat_cols, reference=train_set)

    with mlflow.start_run(run_name="lgbm_p90_risk"):
        mlflow.log_params(PARAMS)

        model = lgb.train(
            PARAMS,
            train_set,
            num_boost_round=NUM_BOOST_ROUND,
            valid_sets=[val_set],
            callbacks=[lgb.early_stopping(EARLY_STOPPING_ROUNDS), lgb.log_evaluation(50)],
        )

        p90_preds = model.predict(val_df[FEATURE_COLS], num_iteration=model.best_iteration)
        p90_preds = np.clip(p90_preds, 0, None)

        loss = pinball_loss(val_df[TARGET_COL].values, p90_preds, config.RISK_QUANTILE)
        # calibration check: what fraction of actuals fall at or below P90 pred?
        # for a well-calibrated P90 model this should be close to 0.90
        coverage = float((val_df[TARGET_COL].values <= p90_preds).mean())

        mlflow.log_metric("pinball_loss", loss)
        mlflow.log_metric("p90_coverage", coverage)
        print(f"P90 pinball loss: {loss:.3f}  |  empirical coverage: {coverage:.3f} (target 0.90)")

        val_df = val_df.copy()
        val_df["p90_forecast"] = p90_preds
        val_df = simulate_inventory(val_df)
        val_df["stockout_risk_flag"] = (val_df["p90_forecast"] > val_df["on_hand_inventory"]).astype(int)

        stockout_rate = float(val_df["stockout_risk_flag"].mean())
        mlflow.log_metric("flagged_stockout_rate", stockout_rate)
        print(f"Series-days flagged at stockout risk: {stockout_rate:.1%}")

        mlflow.lightgbm.log_model(model, artifact_path="model", registered_model_name="demand_risk_p90_lgbm")

        val_df[[
            "item_id", "store_id", "date", TARGET_COL,
            "p90_forecast", "on_hand_inventory", "stockout_risk_flag",
        ]].to_parquet(config.ROOT / "data" / "val_risk.parquet")

    return model


if __name__ == "__main__":
    train()
