"""
Day 3 — Demand Planning Agent.

Reads insight cards (from insight_cards.json, the Day 2 output) and pushes
each one onto the shared insights_queue for the Inventory Agent to consume.
This is intentionally the simpler of the two agents — its job is to notice
and broadcast risk, not decide what to do about it.

Built as a small LangGraph graph (load -> filter -> publish) so the pattern
is in place before Day 3's more complex Inventory Agent, and so both agents
share the same "graph of nodes with shared state" shape.

Run:
    python -m src.agents.demand_planning_agent
"""

import json
from typing import TypedDict

from langgraph.graph import StateGraph, END

from src import config
from src.agents import queue

class DemandPlanningState(TypedDict):
    cards: list[dict]
    published_count: int

def load_cards(state: DemandPlanningState) -> DemandPlanningState:
    with open(config.INSIGHTS_JSON) as f:
        cards = json.load(f)
    state["cards"] = cards
    return state

def publish_to_queue(state: DemandPlanningState) -> DemandPlanningState:
    count = 0
    for card in state["cards"]:
        # only stockout-risk cards go to Inventory — anomaly-only cards are
        # informational and don't need a reorder decision downstream
        if card.get("stockout_risk_flag") == 1:
            queue.push_insight(card)
            count += 1
    state["published_count"] = count
    queue.log_action(
        agent="demand_planning_agent",
        card_id="batch",
        action="published_insights",
        details={"count": count},
    )
    return state

def build_graph():
    graph = StateGraph(DemandPlanningState)
    graph.add_node("load_cards", load_cards)
    graph.add_node("publish_to_queue", publish_to_queue)
    graph.set_entry_point("load_cards")
    graph.add_edge("load_cards", "publish_to_queue")
    graph.add_edge("publish_to_queue", END)
    return graph.compile()

def run() -> int:
    queue.init_db()
    app = build_graph()
    result = app.invoke({"cards": [], "published_count": 0})
    print(f"Demand Planning Agent: published {result['published_count']} stockout-risk insights to queue")
    return result["published_count"]
    
if __name__ == "__main__":
    run()