"""
Day 3 — Inventory Agent.

Consumes pending insights from the shared queue (written by the Demand
Planning Agent), grounds its reasoning with a RAG query against the same
Qdrant store, computes a reorder quantity, and writes the decision to
actions_log. This is the "agent takes an action based on another agent's
output" handoff the whole project is built to demonstrate.

Reorder quantity logic (v1, simple and stated explicitly):
    reorder_qty = max(0, (p90_forecast * lead_time_days * safety_factor) - on_hand_inventory)
This is a standard safety-stock-style heuristic, not a full inventory
optimization model — good enough to prove the pattern, and callable out as
a place to plug in a smarter policy later.

Run:
    python -m src.agents.inventory_agent
"""

from typing import TypedDict

from langgraph.graph import StateGraph, END

from src import config
from src.agents import queue
from src.rag.query import answer as rag_answer

class InventoryState(TypedDict):
    pending_cards: list[dict]
    decisions: list[dict]

def fetch_pending(state: InventoryState) -> InventoryState:
    state["pending_cards"] = queue.pop_pending_insights()
    return state

def decide_reorders(state: InventoryState) -> InventoryState:
    decisions = []
    for card in state["pending_cards"]:
        p90 = card["p90_forecast"]
        on_hand = card["on_hand_inventory"]
        reorder_qty = max(
            0.0,
            (p90 * config.REORDER_LEAD_TIME_DAYS * config.REORDER_SAFETY_FACTOR) - on_hand,
        )
        decisions.append({
            "card_id": card["id"],
            "item_id": card["item_id"],
            "store_id": card["store_id"],
            "reorder_qty": round(reorder_qty, 1),
            "p90_forecast": p90,
            "on_hand_inventory": on_hand,
        })
    state["decisions"] = decisions
    return state

def explain_and_log(state: InventoryState) -> InventoryState:
    for decision in state["decisions"]:
        if decision["reorder_qty"] <= 0:
            continue  # nothing to reorder, skip logging noise

        # ground the explanation in the RAG store — proves the agent is
        # reasoning over the shared knowledge base, not just doing arithmetic
        question = (
            f"Why is item {decision['item_id']} at store {decision['store_id']} "
            f"at stockout risk?"
        )
        try:
            rationale = rag_answer(question, top_k=2)
        except Exception as e:
            rationale = f"(RAG explanation unavailable: {e})"

        queue.log_action(
            agent="inventory_agent",
            card_id=decision["card_id"],
            action="reorder_recommended",
            details={
                "item_id": decision["item_id"],
                "store_id": decision["store_id"],
                "reorder_qty": decision["reorder_qty"],
                "rationale": rationale,
            },
        )
    return state

def build_graph():
    graph = StateGraph(InventoryState)
    graph.add_node("fetch_pending", fetch_pending)
    graph.add_node("decide_reorders", decide_reorders)
    graph.add_node("explain_and_log", explain_and_log)
    graph.set_entry_point("fetch_pending")
    graph.add_edge("fetch_pending", "decide_reorders")
    graph.add_edge("decide_reorders", "explain_and_log")
    graph.add_edge("explain_and_log", END)
    return graph.compile()

def run() -> list[dict]:
    queue.init_db()
    app = build_graph()
    result = app.invoke({"pending_cards": [], "decisions": []})
    n_reorders = sum(1 for d in result["decisions"] if d["reorder_qty"] > 0)
    print(f"Inventory Agent: processed {len(result['pending_cards'])} insights, "
          f"recommended {n_reorders} reorders")
    return result["decisions"]


if __name__ == "__main__":
    run()