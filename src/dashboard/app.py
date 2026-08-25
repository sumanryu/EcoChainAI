"""
Day 4 — Dashboard.

Single Streamlit app: KPI summary, insight feed, agent action log, and a
RAG chat box. Reads directly from the same files/DBs the pipeline writes
to (forecasts.parquet, insight_cards.json, agent_queue.db) — no separate
API layer for v1.

Run:
    streamlit run src/dashboard/app.py
"""

import json

import pandas as pd
import streamlit as st

from src import config
from src.agents import queue
from src.rag.query import answer as rag_answer

st.set_page_config(page_title="Demand Intelligence Mesh", layout="wide")
st.title("Demand Intelligence Mesh")
st.caption("Forecasts -> Insights -> RAG -> Agent Mesh -> Action, end to end.")


@st.cache_data(ttl=30)
def load_forecasts() -> pd.DataFrame:
    return pd.read_parquet(config.FORECASTS_PARQUET)


@st.cache_data(ttl=30)
def load_cards() -> list[dict]:
    with open(config.INSIGHTS_JSON) as f:
        return json.load(f)


def load_actions(limit: int = 50) -> list[dict]:
    return queue.get_recent_actions(limit=limit)


tab_overview, tab_insights, tab_agents, tab_chat = st.tabs(
    ["Overview", "Insight Feed", "Agent Action Log", "Ask the RAG"]
)

with tab_overview:
    df = load_forecasts()
    cards = load_cards()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Series-days scored", f"{len(df):,}")
    c2.metric("Stockout risk flagged", f"{df['stockout_risk_flag'].mean():.1%}")
    c3.metric("Anomalies flagged", f"{df['anomaly_flag'].mean():.1%}")
    c4.metric("Active insight cards", f"{len(cards):,}")

    st.subheader("Forecast vs actual, P90 risk band")
    all_series = df[["item_id", "store_id"]].drop_duplicates().sort_values(["item_id", "store_id"])
    # default to a series that actually has stockout risk flagged, more interesting than a random pick
    risky_series = df[df["stockout_risk_flag"] == 1][["item_id", "store_id"]].drop_duplicates()
    default_idx = 0
    options = list(zip(all_series["item_id"], all_series["store_id"]))
    if len(risky_series) > 0:
        default_pair = (risky_series.iloc[0]["item_id"], risky_series.iloc[0]["store_id"])
        if default_pair in options:
            default_idx = options.index(default_pair)

    picked = st.selectbox(
        "Pick a series",
        options=options,
        index=default_idx,
        format_func=lambda p: f"{p[0]} @ {p[1]}",
    )
    sample = df[(df["item_id"] == picked[0]) & (df["store_id"] == picked[1])].sort_values("date")
    st.line_chart(sample.set_index("date")[["actual_sales", "forecast", "p90_forecast"]])
    st.caption(
        "This is the validation window only (last 28 days), where we know the real "
        "outcome — actual vs point forecast vs P90 risk ceiling. It's a calibration "
        "check: forecast should track actual reasonably closely, and actual should "
        "rarely exceed the P90 line (that's what 'P90 coverage ~0.90' means)."
    )

with tab_insights:
    st.subheader("Active insight cards")
    cards = load_cards()
    filter_store = st.multiselect("Filter by store", sorted({c["store_id"] for c in cards}))
    filtered = [c for c in cards if not filter_store or c["store_id"] in filter_store]
    st.write(f"{len(filtered):,} cards")
    st.dataframe(
        pd.DataFrame(filtered)[
            ["id", "item_id", "store_id", "date", "forecast", "actual_sales",
             "stockout_risk_flag", "anomaly_flag", "summary"]
        ],
        use_container_width=True,
        height=500,
    )

with tab_agents:
    st.subheader("Agent action log")
    st.caption("Demand Planning Agent publishes risk -> Inventory Agent reads it, decides, and logs the action below.")
    actions = load_actions(limit=50)
    if not actions:
        st.info("No actions logged yet — run `python -m src.agents.run_day3` first.")
    else:
        rows = []
        for a in actions:
            row = {"time": a["created_at"], "agent": a["agent"], "action": a["action"], "card_id": a["card_id"]}
            if a["action"] == "reorder_recommended":
                row["item_id"] = a["details"].get("item_id")
                row["store_id"] = a["details"].get("store_id")
                row["reorder_qty"] = a["details"].get("reorder_qty")
            rows.append(row)
        st.dataframe(pd.DataFrame(rows), use_container_width=True, height=400)

        st.subheader("Rationale for a specific action")
        reorder_actions = [a for a in actions if a["action"] == "reorder_recommended"]
        if reorder_actions:
            selected = st.selectbox(
                "Pick an action",
                options=range(len(reorder_actions)),
                format_func=lambda i: f"{reorder_actions[i]['details']['item_id']} @ {reorder_actions[i]['details']['store_id']}",
            )
            st.write(reorder_actions[selected]["details"].get("rationale", "No rationale logged."))

with tab_chat:
    st.subheader("Ask a question grounded in the insight store")
    question = st.text_input("Question", placeholder="Which items are at risk of stockout?")
    if st.button("Ask") and question:
        with st.spinner("Retrieving context and generating answer..."):
            response = rag_answer(question)
        st.write(response)