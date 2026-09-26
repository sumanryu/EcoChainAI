"""
Phase 9 — Finance Agent.

Reads from topic "procurement_confirmed" (Procurement's output), computes a
rough margin-impact estimate using synthetic cost data, and either APPROVES
the spend or FLAGS it for review if the order value exceeds a threshold.
This is the end of the agent chain — Finance's decision is the final
logged action for a given reorder.

Run:
    python -m src.agents.finance_agent
"""

import json
from typing import TypedDict

from langgraph.graph import StateGraph, END

from src import config
from src.agents import queue
from src.agents.synthetic_supplier_data import COST_DATA_PATH

# Orders above this estimated cost get flagged for review rather than
# auto-approved — a simple stand-in for a real spend-approval policy.
AUTO_APPROVE_THRESHOLD = 5000.0


class FinanceState(TypedDict):
    pending_confirmations: list[dict]
    decisions: list[dict]


def load_cost_data() -> dict:
    if not COST_DATA_PATH.exists():
        raise FileNotFoundError(
            "Cost data not found — run `python -m src.agents.synthetic_supplier_data` first."
        )
    with open(COST_DATA_PATH) as f:
        return json.load(f)


def fetch_pending(state: FinanceState) -> FinanceState:
    state["pending_confirmations"] = queue.pop_pending("procurement_confirmed")
    return state


def compute_margin_impact(state: FinanceState) -> FinanceState:
    cost_data = load_cost_data()
    decisions = []

    for conf in state["pending_confirmations"]:
        item_id = conf["item_id"]
        cost_ratio = cost_data.get(item_id, {"cost_ratio": 0.6})["cost_ratio"]

        # rough estimate: use p90_forecast as a stand-in for unit price
        # (this project has no separate unit price feed at the item level
        # beyond sell_price already baked into upstream features — this is
        # a simplification, clearly flagged, same spirit as other synthetic
        # assumptions in this project)
        estimated_unit_price = conf.get("p90_forecast", 1.0) * 2  # rough placeholder scale
        estimated_cost = estimated_unit_price * cost_ratio * conf["fulfilled_qty"]

        decision = {
            **conf,
            "estimated_order_cost": round(estimated_cost, 2),
            "finance_status": "approved" if estimated_cost <= AUTO_APPROVE_THRESHOLD else "flagged_for_review",
        }
        decisions.append(decision)

    state["decisions"] = decisions
    return state


def log_decision(state: FinanceState) -> FinanceState:
    for decision in state["decisions"]:
        queue.log_action(
            agent="finance_agent",
            card_id=decision["card_id"],
            action=f"finance_{decision['finance_status']}",
            details=decision,
        )
    return state


def build_graph():
    graph = StateGraph(FinanceState)
    graph.add_node("fetch_pending", fetch_pending)
    graph.add_node("compute_margin_impact", compute_margin_impact)
    graph.add_node("log_decision", log_decision)
    graph.set_entry_point("fetch_pending")
    graph.add_edge("fetch_pending", "compute_margin_impact")
    graph.add_edge("compute_margin_impact", "log_decision")
    graph.add_edge("log_decision", END)
    return graph.compile()


def run() -> list[dict]:
    queue.init_db()
    app = build_graph()
    result = app.invoke({"pending_confirmations": [], "decisions": []})
    n_flagged = sum(1 for d in result["decisions"] if d["finance_status"] == "flagged_for_review")
    print(f"Finance Agent: processed {len(result['pending_confirmations'])} confirmations, "
          f"{n_flagged} flagged for review")
    return result["decisions"]


if __name__ == "__main__":
    run()