# Demand Intelligence Mesh

A retail demand forecasting system where classical ML predictions become
structured insights, get ingested into a RAG store served by a local SLM,
and are acted on by a small mesh of cross-department agents — proving one
end-to-end pattern: **data -> ML -> insight -> shared knowledge base ->
autonomous agent action**, entirely local for v1, cloud deployment planned
for v2.

## Architecture

```
Raw data (M5, Kaggle)
  -> DuckDB warehouse -> feature pipeline
  -> LightGBM point forecast + LightGBM P90 quantile risk + Isolation Forest anomaly detection
  -> insight cards (structured JSON + text summary)
  -> embedded (bge-small) -> Qdrant vector store
  -> RAG query loop (Qdrant + Ollama/llama3)
  -> Demand Planning Agent (LangGraph) -> shared queue (SQLite)
  -> Inventory Agent (LangGraph) -> reorder decisions, RAG-grounded rationale
  -> Streamlit dashboard (KPIs, insight feed, agent log, RAG chat)
```

## Stack

| Layer | Tool |
|---|---|
| Data | M5 Forecasting dataset (Kaggle) |
| Storage | DuckDB, Parquet |
| ML | LightGBM (point + quantile), scikit-learn (Isolation Forest), MLflow |
| Vector store | Qdrant (local Docker) |
| Embeddings | bge-small-en-v1.5 (sentence-transformers) |
| SLM | Ollama, llama3:8b |
| Agents | LangGraph |
| Dashboard | Streamlit |

## Setup

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Qdrant
docker run -p 6333:6333 -v $(pwd)/qdrant_storage:/qdrant/storage qdrant/qdrant

# Ollama
ollama serve &
ollama pull llama3
```

Download M5 from Kaggle, place the 3 CSVs in `data/raw/`. See individual
`DAY1_README.md` .. `DAY4_README.md` for phase-by-phase detail.

## Run everything

```bash
python -m src.pipeline.run_day1          # ingest -> features -> 3 models -> forecasts.parquet
python -m src.insights.generate_cards     # forecasts.parquet -> insight_cards.json
python -m src.rag.load_qdrant             # embed + load into Qdrant
python -m src.agents.run_day3             # Demand Planning -> Inventory handoff
streamlit run src/dashboard/app.py        # dashboard
```

For a live demo feel:
```bash
python -m src.pipeline.replay --batch-days 1 --sleep 3 --max-batches 20
```
(run this in a separate terminal while the dashboard is open — watch the
Agent Action Log tab update as it replays)

## Verified results (v1, run against full M5 dataset)

- Point forecast: RMSE 1.91, MAE 0.96
- P90 risk model: empirical coverage 0.903 (target 0.90 — well calibrated)
- Anomaly detection: 3.0% flagged (matches configured contamination)
- 853,720 series-days scored (28-day validation window x 30,490 series)
- 104,139 stockout-risk insight cards generated, agent handoff verified end to end

## Known modeling assumptions

- On-hand inventory is **synthetic** — M5 has no real inventory feed. See `src/models/train_quantile.py::simulate_inventory`.
- One **global** LightGBM model across all series (categorical item/store), not per-series models.
- Reorder quantity is a **safety-stock heuristic**, not full inventory optimization.
- Agent queue is **SQLite**, a stand-in for a real event bus (Kafka) — same push/pop interface, swappable later.

## What's next (v2+, not built yet)

- Kafka event bus in place of the SQLite queue
- Marketing, Procurement, Finance agents (same pattern, more nodes)
- AWS deployment: S3, SageMaker, OpenSearch, ECS, Step Functions, Terraform
- Hierarchical forecast reconciliation across item/store/state levels
- Drift monitoring (Evidently AI)


