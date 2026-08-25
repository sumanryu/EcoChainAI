"""
Phase 3 — Point forecast model.

One global LightGBM model across all item-store series (store_id/item_id as
categoricals) rather than one model per series — this is the stronger
portfolio story and scales to the full M5 series count.

Run:
    python -m src.models.train_forecast
"""

import lightgbm as lgb
import matplotlib.pyplot as plt
import mlflow
import numpy as np
from sklearn.metrics import mean_absolute_error, mean_absolute_percentage_error, mean_squared_error

from src import config
from src.models.common import FEATURE_COLS, TARGET_COL, load_features, time_split

PARAMS = {
    "objective": "regression",
    "metric": "rmse",
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


def train() -> lgb.Booster:
    mlflow.set_tracking_uri(config.MLFLOW_TRACKING_URI)
    mlflow.set_experiment(config.MLFLOW_EXPERIMENT)

    df = load_features()
    train_df, val_df = time_split(df)

    cat_cols = [c for c in FEATURE_COLS if df[c].dtype.name == "category"]
    train_set = lgb.Dataset(train_df[FEATURE_COLS], label=train_df[TARGET_COL], categorical_feature=cat_cols)
    val_set = lgb.Dataset(val_df[FEATURE_COLS], label=val_df[TARGET_COL], categorical_feature=cat_cols, reference=train_set)

    with mlflow.start_run(run_name="lgbm_point_forecast"):
        mlflow.log_params(PARAMS)
        mlflow.log_param("num_boost_round", NUM_BOOST_ROUND)
        mlflow.log_param("validation_days", config.VALIDATION_DAYS)

        model = lgb.train(
            PARAMS,
            train_set,
            num_boost_round=NUM_BOOST_ROUND,
            valid_sets=[val_set],
            callbacks=[lgb.early_stopping(EARLY_STOPPING_ROUNDS), lgb.log_evaluation(50)],
        )

        preds = model.predict(val_df[FEATURE_COLS], num_iteration=model.best_iteration)
        preds = np.clip(preds, 0, None)  # sales can't be negative

        rmse = float(np.sqrt(mean_squared_error(val_df[TARGET_COL], preds)))
        mae = float(mean_absolute_error(val_df[TARGET_COL], preds))
        # MAPE is unstable near zero sales (common in retail) — add small epsilon
        mape = float(mean_absolute_percentage_error(val_df[TARGET_COL] + 1e-6, preds + 1e-6))

        mlflow.log_metric("rmse", rmse)
        mlflow.log_metric("mae", mae)
        mlflow.log_metric("mape", mape)
        mlflow.log_metric("best_iteration", model.best_iteration)

        print(f"Validation — RMSE: {rmse:.3f}  MAE: {mae:.3f}  MAPE: {mape:.3f}")

        # feature importance plot for the "report"
        fig, ax = plt.subplots(figsize=(8, 6))
        lgb.plot_importance(model, ax=ax, max_num_features=20, importance_type="gain")
        plt.tight_layout()
        mlflow.log_figure(fig, "feature_importance.png")
        plt.close(fig)

        mlflow.lightgbm.log_model(model, artifact_path="model", registered_model_name="demand_forecast_lgbm")

        # residuals table feeds the anomaly detector — save alongside model artifacts
        val_df = val_df.copy()
        val_df["forecast"] = preds
        val_df["residual"] = val_df[TARGET_COL] - val_df["forecast"]
        val_df[["item_id", "store_id", "date", TARGET_COL, "forecast", "residual"]].to_parquet(
            config.ROOT / "data" / "val_residuals.parquet"
        )

    return model


if __name__ == "__main__":
    train()
