"""
Phase 7 — Orchestration.

Runs the full Day 1 pipeline end to end and merges the three model outputs
(point forecast, P90 risk, anomaly flag) into ONE table keyed by
(item_id, store_id, date). This table is the "done when" deliverable for
Day 1, and is exactly the input the Day 2 insight-card generator consumes.

Run:
    python -m src.pipeline.run_day1
"""

import time

import pandas as pd

from src import config
from src.pipeline import ingest, features
from src.models import train_forecast, train_quantile, detect_anomalies


def merge_outputs() -> pd.DataFrame:
    residuals = pd.read_parquet(config.ROOT / "data" / "val_residuals.parquet")
    risk = pd.read_parquet(config.ROOT / "data" / "val_risk.parquet")
    anomalies = pd.read_parquet(config.ROOT / "data" / "val_anomalies.parquet")

    key = ["item_id", "store_id", "date"]

    merged = residuals[key + ["sales", "forecast"]].merge(
        risk[key + ["p90_forecast", "on_hand_inventory", "stockout_risk_flag"]],
        on=key, how="left",
    ).merge(
        anomalies[key + ["anomaly_flag", "anomaly_score", "normalized_residual"]],
        on=key, how="left",
    )

    merged = merged.rename(columns={"sales": "actual_sales"})
    return merged


def run() -> pd.DataFrame:
    t0 = time.time()

    print("=" * 60)
    print("PHASE 1: Ingestion")
    print("=" * 60)
    ingest.run()

    print("\n" + "=" * 60)
    print("PHASE 2: Feature engineering")
    print("=" * 60)
    features.run()

    print("\n" + "=" * 60)
    print("PHASE 3: Point forecast model")
    print("=" * 60)
    train_forecast.train()

    print("\n" + "=" * 60)
    print("PHASE 4: Quantile risk model")
    print("=" * 60)
    train_quantile.train()

    print("\n" + "=" * 60)
    print("PHASE 5: Anomaly detection")
    print("=" * 60)
    detect_anomalies.train()

    print("\n" + "=" * 60)
    print("PHASE 6-7: Merging into final output table")
    print("=" * 60)
    final = merge_outputs()
    final.to_parquet(config.FORECASTS_PARQUET, index=False)

    elapsed = time.time() - t0
    print(f"\nDone in {elapsed / 60:.1f} min.")
    print(f"Final table: {config.FORECASTS_PARQUET}  ({len(final):,} rows)")
    print(f"Columns: {list(final.columns)}")
    print(f"\nMLflow UI: run `mlflow ui --backend-store-uri {config.MLFLOW_TRACKING_URI}`")

    return final


if __name__ == "__main__":
    run()
