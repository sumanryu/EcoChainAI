"""
Day 3 — Shared queue for agent handoff.

v1 stand-in for a real event bus (Kafka in v2+). Two tables:
  - insights_queue: Demand Planning agent writes here, Inventory agent reads
  - actions_log: Inventory agent writes decisions here (the audit trail /
    what the Day 4 dashboard displays as the agent action log)

Run directly to (re)initialize the tables:
    python -m src.agents.queue
"""

import json
import sqlite3
from datetime import datetime, timezone

from src import config

def get_connection() -> sqlite3.Connection:
    config.AGENT_QUEUE_DB.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(str(config.AGENT_QUEUE_DB))

def init_db() -> None:
    con = get_connection()
    con.execute("""
        CREATE TABLE IF NOT EXISTS insights_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            card_id TEXT NOT NULL,
            payload TEXT NOT NULL,       -- json blob of the insight card
            status TEXT NOT NULL DEFAULT 'pending',  -- pending | consumed
            created_at TEXT NOT NULL,
            consumed_at TEXT
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS actions_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent TEXT NOT NULL,
            card_id TEXT,
            action TEXT NOT NULL,
            details TEXT,                -- json blob
            created_at TEXT NOT NULL
        )
    """)
    con.commit()
    con.close()


def push_insight(card: dict) -> None:
    con = get_connection()
    con.execute(
        "INSERT INTO insights_queue (card_id, payload, status, created_at) VALUES (?, ?, 'pending', ?)",
        (card["id"], json.dumps(card), datetime.now(timezone.utc).isoformat()),
    )
    con.commit()
    con.close()

def pop_pending_insights(limit: int = 50) -> list[dict]:
    """Fetch pending insights and mark them consumed in one pass."""
    con = get_connection()
    rows = con.execute(
        "SELECT id, payload FROM insights_queue WHERE status = 'pending' LIMIT ?",
        (limit,),
    ).fetchall()

    ids = [r[0] for r in rows]
    if ids:
        con.executemany(
            "UPDATE insights_queue SET status = 'consumed', consumed_at = ? WHERE id = ?",
            [(datetime.now(timezone.utc).isoformat(), i) for i in ids],
        )
        con.commit()
    con.close()

    return [json.loads(r[1]) for r in rows]

def log_action(agent: str, card_id: str, action: str, details: dict) -> None:
    con = get_connection()
    con.execute(
        "INSERT INTO actions_log (agent, card_id, action, details, created_at) VALUES (?, ?, ?, ?, ?)",
        (agent, card_id, action, json.dumps(details), datetime.now(timezone.utc).isoformat()),
    )
    con.commit()
    con.close()

def get_recent_actions(limit: int = 20) -> list[dict]:
    con = get_connection()
    rows = con.execute(
        "SELECT agent, card_id, action, details, created_at FROM actions_log "
        "ORDER BY created_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    con.close()
    return [
        {"agent": r[0], "card_id": r[1], "action": r[2], "details": json.loads(r[3]), "created_at": r[4]}
        for r in rows
    ]

if __name__ == "__main__":
    init_db()
    print(f"Queue DB initialized at {config.AGENT_QUEUE_DB}")
