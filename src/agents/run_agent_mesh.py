"""
Phase 9 — Full agent mesh orchestration.

Runs all 5 agents in DEPENDENCY ORDER — this matters, since each agent
downstream needs its upstream topic populated first:

  Demand Planning  (produces: stockout_risk, anomaly_drop)
      -> Inventory       (consumes: stockout_risk;  produces: reorder_request)
      -> Procurement     (consumes: reorder_request; produces: procurement_confirmed)
      -> Finance         (consumes: procurement_confirmed)
      -> Marketing       (consumes: anomaly_drop)

Run:
    python -m src.agents.run_agent_mesh
"""

from src.agents import (
    queue,
    demand_planning_agent,
    inventory_agent,
    procurement_agent,
    finance_agent,
    marketing_agent,
)


def run() -> None:
    steps = [
        ("Demand Planning Agent", demand_planning_agent.run),
        ("Inventory Agent", inventory_agent.run),
        ("Procurement Agent", procurement_agent.run),
        ("Finance Agent", finance_agent.run),
        ("Marketing Agent", marketing_agent.run),
    ]

    for name, fn in steps:
        print("=" * 60)
        print(name)
        print("=" * 60)
        fn()
        print()

    print("=" * 60)
    print("Queue depths (pending items per topic — should be ~0 if the chain kept up)")
    print("=" * 60)
    for topic, depth in queue.get_queue_depths().items():
        print(f"  {topic}: {depth} pending")

    print("\n" + "=" * 60)
    print("Recent actions across the full mesh")
    print("=" * 60)
    for action in queue.get_recent_actions(limit=15):
        print(f"[{action['created_at']}] {action['agent']} -> {action['action']} (card: {action['card_id']})")


if __name__ == "__main__":
    run()