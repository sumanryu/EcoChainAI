"""Central config. Adjust RAW_DATA_DIR to wherever you extracted the M5 csvs."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

RAW_DATA_DIR = ROOT / "data" / "raw"          # put m5 csvs here
WAREHOUSE_DB = ROOT / "data" / "warehouse.duckdb"
FEATURES_PARQUET = ROOT / "data" / "features.parquet"
FORECASTS_PARQUET = ROOT / "data" / "forecasts.parquet"
INSIGHTS_JSON = ROOT / "data" / "insight_cards.json"

MLFLOW_TRACKING_URI = f"sqlite:///{ROOT / 'mlruns.db'}"
MLFLOW_EXPERIMENT = "demand-intel-mesh"

# Day 2: RAG
QDRANT_HOST = "localhost"
QDRANT_PORT = 6333
QDRANT_COLLECTION = "insight_cards"
EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"  # sentence-transformers, 384-dim
EMBEDDING_DIM = 384
OLLAMA_MODEL = "llama3"
OLLAMA_HOST = "http://localhost:11434"
RAG_TOP_K = 5

# Day 3: agents
AGENT_QUEUE_DB = ROOT / "data" / "agent_queue.db"
REORDER_LEAD_TIME_DAYS = 7   # assumed supplier lead time for reorder qty calc
REORDER_SAFETY_FACTOR = 1.2  # buffer on top of P90 demand during lead time

# M5 raw filenames — rename if yours differ
SALES_FILE = "sales_train_validation.csv"
CALENDAR_FILE = "calendar.csv"
PRICES_FILE = "sell_prices.csv"

# validation/holdout split: last N days used as validation window
VALIDATION_DAYS = 28

# quantile used for stockout risk (P90 demand)
RISK_QUANTILE = 0.9

# lag/rolling windows for feature engineering
LAG_DAYS = [7, 14, 28]
ROLL_WINDOWS = [7, 28]
