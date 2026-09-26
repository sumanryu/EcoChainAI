"""
Phase 9 — Marketing Agent.

Reads from topic "anomaly_drop" (Demand Planning's output — only NEGATIVE
anomalies, i.e. demand unexpectedly fell), and proposes a simple promo
action for that item/store. This is the shortest agent in the mesh: no
downstream handoff, its recommendation is a terminal action.

Run:
    python -m src.agents.marketing_agent
"""

from typing import TypedDict

from langgraph.graph import StateGraph, END

from src.agents import queue

# Simple, explicit policy — not ML-driven, but a real decision rule:
# how large a discount to propose scales with how anomalous the drop was.
def propose_discount(normalized_residual: float) -> float:
    severity = abs(normalized_residual)
    if severity >= 3:
        return 20.0
    elif severity >= 2:
        return 15.0
    else:
        return 10.0


class MarketingState(TypedDict):
    pending_cards: list[dict]
    proposals: list[dict]


def fetch_pending(state: MarketingState) -> MarketingState:
    state["pending_cards"] = queue.pop_pending("anomaly_drop")
    return state


def propose_promos(state: MarketingState) -> MarketingState:
    proposals = []
    for card in state["pending_cards"]:
        discount = propose_discount(card.get("normalized_residual", 0))
        proposals.append({
            "card_id": card["id"],
            "item_id": card["item_id"],
            "store_id": card["store_id"],
            "proposed_discount_pct": discount,
            "reason": f"Demand dropped {abs(card.get('normalized_residual', 0)):.1f} std devs "
                      f"below expected — proposing a promo to recover volume.",
        })
    state["proposals"] = proposals
    return state


def log_proposals(state: MarketingState) -> MarketingState:
    for proposal in state["proposals"]:
        queue.log_action(
            agent="marketing_agent",
            card_id=proposal["card_id"],
            action="promo_proposed",
            details=proposal,
        )
    return state


def build_graph():
    graph = StateGraph(MarketingState)
    graph.add_node("fetch_pending", fetch_pending)
    graph.add_node("propose_promos", propose_promos)
    graph.add_node("log_proposals", log_proposals)
    graph.set_entry_point("fetch_pending")
    graph.add_edge("fetch_pending", "propose_promos")
    graph.add_edge("propose_promos", "log_proposals")
    graph.add_edge("log_proposals", END)
    return graph.compile()


def run() -> list[dict]:
    queue.init_db()
    app = build_graph()
    result = app.invoke({"pending_cards": [], "proposals": []})
    print(f"Marketing Agent: proposed {len(result['proposals'])} promos for demand-drop anomalies")
    return result["proposals"]


if __name__ == "__main__":
    run()