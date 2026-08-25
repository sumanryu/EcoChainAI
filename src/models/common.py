"""Shared helpers for the modeling phase."""

from datetime import timedelta

import pandas as pd

from src import config

CATEGORICAL_COLS = ["item_id", "dept_id", "cat_id", "store_id", "state_id"]

FEATURE_COLS = CATEGORICAL_COLS + [
    "sell_price",
    "price_change_7d",
    "wday",
    "month",
    "year",
    "is_weekend",
    "has_event",
    "snap_active",
] + [f"lag_{lag}" for lag in config.LAG_DAYS] + [
    f"roll_{stat}_{w}" for w in config.ROLL_WINDOWS for stat in ("mean", "std")
]

TARGET_COL = "sales"


def load_features() -> pd.DataFrame:
    df = pd.read_parquet(config.FEATURES_PARQUET)
    for col in CATEGORICAL_COLS:
        df[col] = df[col].astype("category")
    return df


def time_split(df: pd.DataFrame, validation_days: int = config.VALIDATION_DAYS):
    """Split by date, not randomly — this is a forecasting problem."""
    cutoff = df["date"].max() - timedelta(days=validation_days)
    train = df[df["date"] <= cutoff]
    val = df[df["date"] > cutoff]
    return train, val
