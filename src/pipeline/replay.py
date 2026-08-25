"""
Day 4 — Accelerated replay.

Simulates the "system runs 24/7" feel for a demo: replays validation-window
rows in date order, a few days at a time, re-running the agent handoff on
each batch with a short sleep between batches — so an interviewer watching
the dashboard sees the action log grow in near-real-time instead of you
having to explain "imagine this ran continuously."

This does NOT retrain models — it replays already-scored rows from
forecasts.parquet through the insight/agent pipeline in date order.

Run:
    python -m src.pipeline.replay
"""

import argparse
import json
import time

import pandas as pd

from src import config
from src.insights.generate_cards import build_cards
from src.agents import queue, demand_planning_agent, inventory_agent


def replay(batch_days: int = 1, sleep_seconds: float = 3.0, max_batches: int | None = None) -> None:
    df = pd.read_parquet(config.FORECASTS_PARQUET)
    dates = sorted(df["date"].unique())

    queue.init_db()
    batches = [dates[i:i + batch_days] for i in range(0, len(dates), batch_days)]
    if max_batches:
        batches = batches[:max_batches]

    print(f"Replaying {len(dates)} days in {len(batches)} batches "
          f"({batch_days} day(s)/batch, {sleep_seconds}s between batches)")

    for i, batch_dates in enumerate(batches):
        batch_df = df[df["date"].isin(batch_dates)]
        cards = build_cards(batch_df)

        # write this batch's cards so demand_planning_agent picks them up
        with open(config.INSIGHTS_JSON, "w") as f:
            json.dump(cards, f, indent=2)

        published = demand_planning_agent.run()
        decisions = inventory_agent.run()
        n_reorders = sum(1 for d in decisions if d["reorder_qty"] > 0)

        print(f"[batch {i+1}/{len(batches)}] dates={batch_dates} "
              f"cards={len(cards)} published={published} reorders={n_reorders}")

        time.sleep(sleep_seconds)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Replay forecast data to simulate live agent activity")
    parser.add_argument("--batch-days", type=int, default=1, help="how many days per batch")
    parser.add_argument("--sleep", type=float, default=3.0, help="seconds to sleep between batches")
    parser.add_argument("--max-batches", type=int, default=None, help="stop after N batches (for a short demo)")
    args = parser.parse_args()

    replay(batch_days=args.batch_days, sleep_seconds=args.sleep, max_batches=args.max_batches)
