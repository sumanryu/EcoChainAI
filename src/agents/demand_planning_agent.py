"""
Day 3 — Demand Planning Agent (Phase 9: topic-aware).

Reads insight cards and routes them by SIGNAL TYPE to two different topics:
  - stockout_risk cards -> Inventory Agent
  - negative-anomaly cards (demand dropped unexpectedly) -> Marketing Agent
    (a sales drop is what marketing might want to react to with a promo;
    a positive anomaly, demand spiking, is not something marketing needs
    to act on the same way, so only negative anomalies are routed there)

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
    stockout_published: int
    anomaly_published: int


def load_cards(state: DemandPlanningState) -> DemandPlanningState:
    with open(config.INSIGHTS_JSON) as f:
        cards = json.load(f)
    state["cards"] = cards
    return state


def publish_to_queue(state: DemandPlanningState) -> DemandPlanningState:
    stockout_count = 0
    anomaly_count = 0

    for card in state["cards"]:
        if card.get("stockout_risk_flag") == 1:
            queue.push_to_topic("stockout_risk", card["id"], card)
            stockout_count += 1

        # only route NEGATIVE anomalies (demand dropped) to marketing —
        # normalized_residual < 0 means actual sales were lower than expected
        if card.get("anomaly_flag") == 1 and card.get("normalized_residual", 0) < 0:
            queue.push_to_topic("anomaly_drop", card["id"], card)
            anomaly_count += 1

    state["stockout_published"] = stockout_count
    state["anomaly_published"] = anomaly_count

    queue.log_action(
        agent="demand_planning_agent",
        card_id="batch",
        action="published_insights",
        details={"stockout_risk": stockout_count, "anomaly_drop": anomaly_count},
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


def run() -> dict:
    queue.init_db()
    app = build_graph()
    result = app.invoke({"cards": [], "stockout_published": 0, "anomaly_published": 0})
    print(f"Demand Planning Agent: published {result['stockout_published']} stockout-risk "
          f"+ {result['anomaly_published']} anomaly-drop insights to queue")
    return result


if __name__ == "__main__":
    run()