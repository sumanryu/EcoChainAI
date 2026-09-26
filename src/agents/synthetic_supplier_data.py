"""
Phase 9 — Synthetic supplier & cost data.

Same honesty pattern as simulate_inventory() in train_quantile.py: M5 has
no real supplier or cost data, so we generate a plausible, clearly-labeled
synthetic dataset to demonstrate the Procurement/Finance agent LOGIC.
Swap this module for a real supplier/ERP feed if one ever exists — the
agents that consume it don't need to change, only this data source does.

Run once to generate the lookup tables:
    python -m src.agents.synthetic_supplier_data
"""

import json

import numpy as np
import pandas as pd

from src import config

SUPPLIER_DATA_PATH = config.ROOT / "data" / "supplier_capacity.json"
COST_DATA_PATH = config.ROOT / "data" / "item_costs.json"


def generate(seed: int = 7) -> None:
    df = pd.read_parquet(config.FORECASTS_PARQUET)
    items = df["item_id"].unique()
    rng = np.random.default_rng(seed)

    # Supplier capacity: each item's supplier can fulfill up to some max
    # units per order, with a lead-time variability factor. A minority of
    # items (10%) have a CONSTRAINED supplier (low capacity) — these are
    # the interesting cases where Procurement should flag a delay.
    supplier_data = {}
    for item in items:
        is_constrained = rng.random() < 0.10
        max_capacity = rng.uniform(20, 60) if is_constrained else rng.uniform(200, 1000)
        supplier_data[item] = {
            "max_order_capacity": round(float(max_capacity), 1),
            "lead_time_days": int(rng.integers(3, 14)),
            "constrained": bool(is_constrained),
        }

    with open(SUPPLIER_DATA_PATH, "w") as f:
        json.dump(supplier_data, f, indent=2)

    # Cost/margin: unit cost as a fraction of the item's average sell_price,
    # so Finance can compute (revenue - cost) x reorder_qty as a rough
    # margin-impact check.
    avg_price = df.groupby("item_id")["forecast"].mean()  # stand-in for price signal available here
    cost_data = {}
    for item in items:
        cost_ratio = rng.uniform(0.45, 0.75)  # cost as a fraction of sell price
        cost_data[item] = {"cost_ratio": round(float(cost_ratio), 3)}

    with open(COST_DATA_PATH, "w") as f:
        json.dump(cost_data, f, indent=2)

    print(f"Generated supplier data for {len(items)} items -> {SUPPLIER_DATA_PATH}")
    print(f"Generated cost data for {len(items)} items -> {COST_DATA_PATH}")
    print(f"{sum(1 for v in supplier_data.values() if v['constrained'])} items have a constrained supplier")


if __name__ == "__main__":
    generate()