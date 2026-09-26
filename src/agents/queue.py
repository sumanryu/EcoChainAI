"""
Day 3 + Phase 9 — Shared queue for agent handoff, now TOPIC-based.

v1 had one hardcoded queue (Demand Planning -> Inventory only). Phase 9
adds 3 more agents with 3 more handoffs, so the queue is generalized with
a `topic` column — the same core idea Kafka uses (producers publish to a
named topic, consumers subscribe to it), just backed by SQLite instead of
a real message broker.

This is a DELIBERATE design choice: when this project eventually swaps to
real Kafka (parked on the v2 backlog), the CALLING CODE (push_to_topic,
pop_pending) barely changes — only queue.py's internals would swap from
SQLite to a Kafka producer/consumer. Agents never talk to each other
directly; they only know about topics, which is what makes that future
swap cheap.

Topics in use:
  stockout_risk         — Demand Planning -> Inventory
  reorder_request        — Inventory -> Procurement
  procurement_confirmed  — Procurement -> Finance
  anomaly_drop           — Demand Planning -> Marketing

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
        CREATE TABLE IF NOT EXISTS topic_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic TEXT NOT NULL,
            card_id TEXT NOT NULL,
            payload TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
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
            details TEXT,
            created_at TEXT NOT NULL
        )
    """)
    con.commit()
    con.close()


def push_to_topic(topic: str, card_id: str, payload: dict) -> None:
    con = get_connection()
    con.execute(
        "INSERT INTO topic_queue (topic, card_id, payload, status, created_at) VALUES (?, ?, ?, 'pending', ?)",
        (topic, card_id, json.dumps(payload), datetime.now(timezone.utc).isoformat()),
    )
    con.commit()
    con.close()


def pop_pending(topic: str, limit: int = 50) -> list[dict]:
    """Fetch pending items for ONE topic and mark them consumed."""
    con = get_connection()
    rows = con.execute(
        "SELECT id, payload FROM topic_queue WHERE topic = ? AND status = 'pending' LIMIT ?",
        (topic, limit),
    ).fetchall()

    ids = [r[0] for r in rows]
    if ids:
        con.executemany(
            "UPDATE topic_queue SET status = 'consumed', consumed_at = ? WHERE id = ?",
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


def get_queue_depths() -> dict:
    """Pending count per topic — a real observability metric worth showing
    on the dashboard (Phase 10): if a topic's depth keeps growing, that
    topic's consumer is falling behind."""
    con = get_connection()
    rows = con.execute(
        "SELECT topic, COUNT(*) FROM topic_queue WHERE status = 'pending' GROUP BY topic"
    ).fetchall()
    con.close()
    return dict(rows)


if __name__ == "__main__":
    init_db()
    print(f"Queue DB initialized at {config.AGENT_QUEUE_DB}")