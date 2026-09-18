"""
Day 2, Phase 1 — Insight card generation (v1.1: rolled up).

v1 produced one card per (item_id, store_id, date) — a daily event log.
For a chronically at-risk series, that meant a new near-duplicate card every
single day it stayed flagged, ballooning to 128,165 cards from 853,720 rows —
unusable by a human, and noisy for agents/RAG (which saw "flagged again" as
if it were new information every day).

v1.1: one card per (item_id, store_id) — the LATEST state within the window,
plus days_flagged / first_flagged_date to capture persistence. A chronic
6-day stockout risk is now one card saying "flagged for 6 days," not six
separate cards.

Run:
    python -m src.insights.generate_cards
"""

import json

import pandas as pd

from src import config


def safe_int(value, default: int = 0) -> int:
    """Coerce to int, defaulting to 0 for NaN/None instead of crashing.
    Last line of defense — upstream fillna() should already have caught
    this, but pandas .last() (per-column, not per-row) can still surface
    an unexpected NaN in edge cases, so this makes card generation
    unconditionally robust rather than chasing every possible source."""
    return default if pd.isna(value) else int(value)


def summarize(row: pd.Series) -> str:
    parts = [
        f"Item {row['item_id']} at store {row['store_id']}, latest as of {row['date']}: "
        f"forecasted demand {row['forecast']:.1f}, actual {row['actual_sales']:.1f}."
    ]
    if row["stockout_risk_flag"] == 1:
        persistence = (
            f"flagged for {row['days_flagged']} of the last 28 days (since {row['first_flagged_date']})"
            if row["days_flagged"] > 1 else "flagged today"
        )
        parts.append(
            f"Stockout risk: P90 demand ({row['p90_forecast']:.1f}) exceeds "
            f"on-hand inventory ({row['on_hand_inventory']:.1f}) — {persistence}."
        )
    if row["anomaly_flag"] == 1:
        direction = "higher" if row["normalized_residual"] > 0 else "lower"
        parts.append(f"Anomalous demand detected — actual sales were unusually {direction} than expected.")
    return " ".join(parts)


def build_cards(df: pd.DataFrame) -> list[dict]:
    df = df.copy()
    # Guard: the risk and anomaly models were validated on slightly
    # different row sets in Day 1 (separate merges in run_day1.py), so a
    # row can have one flag present and the other NaN (missing from that
    # merge). Coerce both to a clean 0/1 before filtering/casting, so a
    # NaN never reaches int() below.
    df["stockout_risk_flag"] = df["stockout_risk_flag"].fillna(0).astype(int)
    df["anomaly_flag"] = df["anomaly_flag"].fillna(0).astype(int)

    active = df[(df["stockout_risk_flag"] == 1) | (df["anomaly_flag"] == 1)].copy()
    if active.empty:
        return []

    active = active.sort_values("date")

    # persistence: how many days (within this window) has each series been
    # flagged for stockout risk, and since when
    risk_days = active[active["stockout_risk_flag"] == 1]
    persistence = risk_days.groupby(["item_id", "store_id"]).agg(
        days_flagged=("date", "count"),
        first_flagged_date=("date", "min"),
    ).reset_index()

    # latest row per series = the current state we want to summarize.
    # NOTE: deliberately NOT using groupby(...).last() — that picks the
    # last NON-NULL value independently PER COLUMN, which can silently mix
    # fields from different rows within the same group if any column has a
    # null partway through. sort + drop_duplicates(keep="last") guarantees
    # every field in the resulting row comes from the SAME actual row.
    latest = active.sort_values("date").drop_duplicates(subset=["item_id", "store_id"], keep="last")
    latest = latest.merge(persistence, on=["item_id", "store_id"], how="left")
    latest["days_flagged"] = latest["days_flagged"].fillna(0).astype(int)

    cards = []
    for _, row in latest.iterrows():
        card = {
            "id": f"{row['item_id']}_{row['store_id']}",  # no longer date-suffixed — one card per series
            "item_id": row["item_id"],
            "store_id": row["store_id"],
            "date": str(row["date"]),  # latest date this state reflects
            "forecast": float(row["forecast"]),
            "actual_sales": float(row["actual_sales"]),
            "p90_forecast": float(row["p90_forecast"]),
            "on_hand_inventory": float(row["on_hand_inventory"]),
            "stockout_risk_flag": safe_int(row["stockout_risk_flag"]),
            "days_flagged": safe_int(row["days_flagged"]),
            "first_flagged_date": str(row["first_flagged_date"]) if pd.notna(row.get("first_flagged_date")) else None,
            "anomaly_flag": safe_int(row["anomaly_flag"]),
            "anomaly_score": float(row["anomaly_score"]),
            "summary": summarize(row),
        }
        cards.append(card)
    return cards


def run() -> list[dict]:
    df = pd.read_parquet(config.FORECASTS_PARQUET)
    cards = build_cards(df)

    with open(config.INSIGHTS_JSON, "w") as f:
        json.dump(cards, f, indent=2)

    n_series_flagged = df[(df["stockout_risk_flag"] == 1) | (df["anomaly_flag"] == 1)][
        ["item_id", "store_id"]
    ].drop_duplicates().shape[0]

    print(f"Generated {len(cards):,} insight cards (one per flagged series) "
          f"from {len(df):,} rows — {n_series_flagged:,} distinct series had an active signal")
    print(f"Written to {config.INSIGHTS_JSON}")
    return cards


if __name__ == "__main__":
    run()