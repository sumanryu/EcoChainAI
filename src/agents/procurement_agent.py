"""
Phase 9 — Procurement Agent.

Reads from topic "reorder_request" (Inventory's output), checks the
requested quantity against a synthetic supplier capacity table, and either
CONFIRMS the order as-is or FLAGS A DELAY (splitting into what's available
now vs. a backordered remainder) if the supplier can't fulfill it in one go.
Forwards the outcome to topic "procurement_confirmed" for Finance.

Run:
    python -m src.agents.procurement_agent
"""

import json
from typing import TypedDict

from langgraph.graph import StateGraph, END

from src import config
from src.agents import queue
from src.agents.synthetic_supplier_data import SUPPLIER_DATA_PATH


class ProcurementState(TypedDict):
    pending_requests: list[dict]
    outcomes: list[dict]


def load_supplier_data() -> dict:
    if not SUPPLIER_DATA_PATH.exists():
        raise FileNotFoundError(
            "Supplier data not found — run `python -m src.agents.synthetic_supplier_data` first."
        )
    with open(SUPPLIER_DATA_PATH) as f:
        return json.load(f)


def fetch_pending(state: ProcurementState) -> ProcurementState:
    state["pending_requests"] = queue.pop_pending("reorder_request")
    return state


def check_supplier_capacity(state: ProcurementState) -> ProcurementState:
    supplier_data = load_supplier_data()
    outcomes = []

    for req in state["pending_requests"]:
        item_id = req["item_id"]
        supplier = supplier_data.get(item_id, {"max_order_capacity": 500, "lead_time_days": 7, "constrained": False})

        requested = req["reorder_qty"]
        capacity = supplier["max_order_capacity"]

        if requested <= capacity:
            outcome = {
                **req,
                "procurement_status": "confirmed",
                "fulfilled_qty": requested,
                "backordered_qty": 0.0,
                "lead_time_days": supplier["lead_time_days"],
            }
        else:
            outcome = {
                **req,
                "procurement_status": "delayed",
                "fulfilled_qty": round(capacity, 1),
                "backordered_qty": round(requested - capacity, 1),
                "lead_time_days": supplier["lead_time_days"],
            }
        outcomes.append(outcome)

    state["outcomes"] = outcomes
    return state


def log_and_forward(state: ProcurementState) -> ProcurementState:
    for outcome in state["outcomes"]:
        queue.log_action(
            agent="procurement_agent",
            card_id=outcome["card_id"],
            action=f"procurement_{outcome['procurement_status']}",
            details=outcome,
        )
        queue.push_to_topic("procurement_confirmed", outcome["card_id"], outcome)
    return state


def build_graph():
    graph = StateGraph(ProcurementState)
    graph.add_node("fetch_pending", fetch_pending)
    graph.add_node("check_supplier_capacity", check_supplier_capacity)
    graph.add_node("log_and_forward", log_and_forward)
    graph.set_entry_point("fetch_pending")
    graph.add_edge("fetch_pending", "check_supplier_capacity")
    graph.add_edge("check_supplier_capacity", "log_and_forward")
    graph.add_edge("log_and_forward", END)
    return graph.compile()


def run() -> list[dict]:
    queue.init_db()
    app = build_graph()
    result = app.invoke({"pending_requests": [], "outcomes": []})
    n_delayed = sum(1 for o in result["outcomes"] if o["procurement_status"] == "delayed")
    print(f"Procurement Agent: processed {len(result['pending_requests'])} reorder requests, "
          f"{n_delayed} delayed due to supplier capacity")
    return result["outcomes"]


if __name__ == "__main__":
    run()