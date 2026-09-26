"""
Phase 8 — Rate limiting for the RAG endpoint.

Protects against runaway Bedrock cost from either abuse or an accidental
loop (e.g. someone spamming the Ask button, or a bug that retries in a
tight loop). Two tiers, both checked before any Bedrock call is made:

  1. BURST limit: max N queries per short window (e.g. 5 per 60 seconds) —
     stops rapid-fire hammering.
  2. DAILY cap: max N queries per rolling 24h (e.g. 100/day) — stops
     sustained cost accumulation even from "reasonable-looking" traffic.

Backed by SQLite (same file as the agent queue, different table) so it
persists across container restarts and works correctly even with multiple
browser tabs/sessions hitting the same deployed app — a per-session,
in-memory counter would reset on every page reload and wouldn't actually
protect anything.

This deliberately limits by GLOBAL usage, not per-user/per-IP — Streamlit
doesn't give reliable client IPs, and for a low-traffic demo (interviewers
only), a global cap is simpler and still achieves the actual goal: cap
total spend, regardless of who's asking.
"""

import sqlite3
from datetime import datetime, timedelta, timezone

from src import config

BURST_MAX_QUERIES = 5
BURST_WINDOW_SECONDS = 60

DAILY_MAX_QUERIES = 100


def _get_connection() -> sqlite3.Connection:
    config.AGENT_QUEUE_DB.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(str(config.AGENT_QUEUE_DB))


def _init_table(con: sqlite3.Connection) -> None:
    con.execute("""
        CREATE TABLE IF NOT EXISTS rag_query_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            queried_at TEXT NOT NULL
        )
    """)
    con.commit()


def check_and_record(
    burst_max: int = BURST_MAX_QUERIES,
    burst_window_seconds: int = BURST_WINDOW_SECONDS,
    daily_max: int = DAILY_MAX_QUERIES,
) -> tuple[bool, str]:
    """Call this BEFORE making a Bedrock call. Returns (allowed, message).

    If allowed is True, the query is also RECORDED as having happened —
    so this function is check-and-increment in one step, avoiding a
    race where two calls both check before either records (this matters
    less with SQLite's default locking, but keeping check+record atomic
    per call is the correct pattern regardless).
    """
    con = _get_connection()
    _init_table(con)

    now = datetime.now(timezone.utc)
    burst_cutoff = (now - timedelta(seconds=burst_window_seconds)).isoformat()
    daily_cutoff = (now - timedelta(days=1)).isoformat()

    burst_count = con.execute(
        "SELECT COUNT(*) FROM rag_query_log WHERE queried_at > ?", (burst_cutoff,)
    ).fetchone()[0]

    if burst_count >= burst_max:
        con.close()
        return False, (
            f"Rate limit: max {burst_max} questions per {burst_window_seconds}s. "
            f"Please wait a moment before asking again."
        )

    daily_count = con.execute(
        "SELECT COUNT(*) FROM rag_query_log WHERE queried_at > ?", (daily_cutoff,)
    ).fetchone()[0]

    if daily_count >= daily_max:
        con.close()
        return False, (
            f"Daily limit reached ({daily_max} questions/24h) — this protects "
            f"the demo's cloud budget. Please try again tomorrow."
        )

    # allowed — record this query before returning
    con.execute("INSERT INTO rag_query_log (queried_at) VALUES (?)", (now.isoformat(),))
    con.commit()
    con.close()
    return True, ""


def usage_snapshot() -> dict:
    """For displaying current usage in the dashboard (transparency, not
    just a silent block) — e.g. 'you can ask 3 more questions this minute'."""
    con = _get_connection()
    _init_table(con)
    now = datetime.now(timezone.utc)
    burst_cutoff = (now - timedelta(seconds=BURST_WINDOW_SECONDS)).isoformat()
    daily_cutoff = (now - timedelta(days=1)).isoformat()

    burst_used = con.execute(
        "SELECT COUNT(*) FROM rag_query_log WHERE queried_at > ?", (burst_cutoff,)
    ).fetchone()[0]
    daily_used = con.execute(
        "SELECT COUNT(*) FROM rag_query_log WHERE queried_at > ?", (daily_cutoff,)
    ).fetchone()[0]
    con.close()

    return {
        "burst_used": burst_used,
        "burst_max": BURST_MAX_QUERIES,
        "daily_used": daily_used,
        "daily_max": DAILY_MAX_QUERIES,
    }