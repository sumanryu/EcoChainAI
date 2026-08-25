"""
Phase 1 — Ingestion.

Loads the three M5 CSVs into DuckDB, unpivots the wide sales_train_validation
table (one column per day) into a long fact table, and joins in calendar and
price data.

Run:
    python -m src.pipeline.ingest
"""

import duckdb

from src import config


def get_connection() -> duckdb.DuckDBPyConnection:
    config.WAREHOUSE_DB.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(config.WAREHOUSE_DB))


def load_raw_tables(con: duckdb.DuckDBPyConnection) -> None:
    sales_path = config.RAW_DATA_DIR / config.SALES_FILE
    calendar_path = config.RAW_DATA_DIR / config.CALENDAR_FILE
    prices_path = config.RAW_DATA_DIR / config.PRICES_FILE

    for p in (sales_path, calendar_path, prices_path):
        if not p.exists():
            raise FileNotFoundError(
                f"Expected M5 file at {p}. Download the M5 dataset from Kaggle "
                f"and place the CSVs under {config.RAW_DATA_DIR}"
            )

    con.execute(f"""
        CREATE OR REPLACE TABLE raw_sales AS
        SELECT * FROM read_csv_auto('{sales_path.as_posix()}')
    """)
    con.execute(f"""
        CREATE OR REPLACE TABLE calendar AS
        SELECT * FROM read_csv_auto('{calendar_path.as_posix()}')
    """)
    con.execute(f"""
        CREATE OR REPLACE TABLE prices AS
        SELECT * FROM read_csv_auto('{prices_path.as_posix()}')
    """)


def unpivot_sales(con: duckdb.DuckDBPyConnection) -> None:
    """Wide (id, item_id, ..., d_1, d_2, ... d_1913) -> long (id, ..., d, sales)."""
    day_cols = [
        c[1] for c in con.execute("PRAGMA table_info('raw_sales')").fetchall()
        if c[1].startswith("d_")
    ]
    day_cols_sql = ", ".join(f'"{c}"' for c in day_cols)

    con.execute(f"""
        CREATE OR REPLACE TABLE sales_long AS
        SELECT id, item_id, dept_id, cat_id, store_id, state_id, d, sales
        FROM raw_sales
        UNPIVOT (sales FOR d IN ({day_cols_sql}))
    """)


def build_fact_table(con: duckdb.DuckDBPyConnection) -> None:
    """Join sales_long with calendar (for dates/events) and prices (weekly)."""
    con.execute("""
        CREATE OR REPLACE TABLE fact_sales AS
        SELECT
            s.item_id,
            s.dept_id,
            s.cat_id,
            s.store_id,
            s.state_id,
            c.date::DATE AS date,
            c.wm_yr_wk,
            c.weekday,
            c.wday,
            c.month,
            c.year,
            c.event_name_1,
            c.event_type_1,
            c.snap_ca,
            c.snap_tx,
            c.snap_wi,
            s.sales,
            p.sell_price
        FROM sales_long s
        JOIN calendar c ON s.d = c.d
        LEFT JOIN prices p
            ON s.item_id = p.item_id
            AND s.store_id = p.store_id
            AND c.wm_yr_wk = p.wm_yr_wk
    """)

    n_rows = con.execute("SELECT COUNT(*) FROM fact_sales").fetchone()[0]
    n_series = con.execute(
        "SELECT COUNT(DISTINCT item_id || store_id) FROM fact_sales"
    ).fetchone()[0]
    print(f"fact_sales built: {n_rows:,} rows across {n_series:,} item-store series")


def run() -> None:
    con = get_connection()
    print("Loading raw CSVs into DuckDB...")
    load_raw_tables(con)
    print("Unpivoting wide sales table to long format...")
    unpivot_sales(con)
    print("Building fact_sales (joined with calendar + prices)...")
    build_fact_table(con)
    con.close()
    print(f"Done. Warehouse at {config.WAREHOUSE_DB}")


if __name__ == "__main__":
    run()
