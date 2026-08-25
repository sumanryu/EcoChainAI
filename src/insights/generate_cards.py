"""
Day 2, Phase 1 — Insight card generation.

Converts forecasts.parquet rows into structured "insight cards": one card
per (item_id, store_id) with the latest signal state, plus a short
natural-language summary. Only series with at least one active signal
(stockout risk or anomaly) become cards — this keeps the RAG index focused
on things worth surfacing, not 30k routine rows.

Run:
    python -m src.insights.generate_cards
"""

import json

import pandas as pd

from src import config


def summarize(row: pd.Series) -> str:
    parts = [
        f"Item {row['item_id']} at store {row['store_id']} on {row['date']}: "
        f"forecasted demand {row['forecast']:.1f}, actual {row['actual_sales']:.1f}."
    ]
    if row["stockout_risk_flag"] == 1:
        parts.append(
            f"Stockout risk flagged: P90 demand ({row['p90_forecast']:.1f}) "
            f"exceeds on-hand inventory ({row['on_hand_inventory']:.1f})."
        )
    if row["anomaly_flag"] == 1:
        direction = "higher" if row["normalized_residual"] > 0 else "lower"
        parts.append(f"Anomalous demand detected — actual sales were unusually {direction} than expected.")
    return " ".join(parts)


def build_cards(df: pd.DataFrame) -> list[dict]:
    # focus on series-days with an active signal — this is what agents/RAG act on
    active = df[(df["stockout_risk_flag"] == 1) | (df["anomaly_flag"] == 1)].copy()

    cards = []
    for _, row in active.iterrows():
        card = {
            "id": f"{row['item_id']}_{row['store_id']}_{row['date']}",
            "item_id": row["item_id"],
            "store_id": row["store_id"],
            "date": str(row["date"]),
            "forecast": float(row["forecast"]),
            "actual_sales": float(row["actual_sales"]),
            "p90_forecast": float(row["p90_forecast"]),
            "on_hand_inventory": float(row["on_hand_inventory"]),
            "stockout_risk_flag": int(row["stockout_risk_flag"]),
            "anomaly_flag": int(row["anomaly_flag"]),
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

    print(f"Generated {len(cards):,} insight cards from {len(df):,} rows "
          f"({len(cards) / len(df):.1%} of series-days had an active signal)")
    print(f"Written to {config.INSIGHTS_JSON}")
    return cards


if __name__ == "__main__":
    run()