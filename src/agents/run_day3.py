"""
Day 3 — Orchestration.

Runs Demand Planning Agent then Inventory Agent in sequence, and prints
recent actions_log entries so you can SEE one agent's output triggering
the other's action — no human in the loop. This is the Day 3 "done when."

Run:
    python -m src.agents.run_day3
"""

from src.agents import queue, demand_planning_agent, inventory_agent


def run() -> None:
    print("=" * 60)
    print("Demand Planning Agent")
    print("=" * 60)
    demand_planning_agent.run()

    print("\n" + "=" * 60)
    print("Inventory Agent")
    print("=" * 60)
    inventory_agent.run()

    print("\n" + "=" * 60)
    print("Recent actions (proof of agent handoff)")
    print("=" * 60)
    for action in queue.get_recent_actions(limit=10):
        print(f"[{action['created_at']}] {action['agent']} -> {action['action']} "
              f"(card: {action['card_id']})")
        if action["action"] == "reorder_recommended":
            d = action["details"]
            print(f"    item={d['item_id']} store={d['store_id']} reorder_qty={d['reorder_qty']}")


if __name__ == "__main__":
    run()
