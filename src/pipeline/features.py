"""
Phase 2 — Feature engineering.

Builds lag features, rolling mean/std, and calendar/price-derived features
directly in DuckDB (window functions), then writes the result to Parquet
for the modeling phase.

Run:
    python -m src.pipeline.features
"""

import duckdb

from src import config


def build_lag_and_rolling_sql() -> str:
    """Generate SQL fragments for configured lag/rolling windows.

    All windows are computed over sales values SHIFTED by 1 day first
    (i.e. as of "yesterday") so no feature ever leaks same-day sales.
    """
    lag_exprs = [
        f"LAG(sales, {lag}) OVER w AS lag_{lag}"
        for lag in config.LAG_DAYS
    ]
    roll_exprs = []
    for window in config.ROLL_WINDOWS:
        roll_exprs.append(
            f"AVG(sales) OVER (PARTITION BY item_id, store_id ORDER BY date "
            f"ROWS BETWEEN {window} PRECEDING AND 1 PRECEDING) AS roll_mean_{window}"
        )
        roll_exprs.append(
            f"STDDEV(sales) OVER (PARTITION BY item_id, store_id ORDER BY date "
            f"ROWS BETWEEN {window} PRECEDING AND 1 PRECEDING) AS roll_std_{window}"
        )
    return ",\n            ".join(lag_exprs + roll_exprs)


def run() -> None:
    con = duckdb.connect(str(config.WAREHOUSE_DB))

    lag_roll_sql = build_lag_and_rolling_sql()

    query = f"""
        CREATE OR REPLACE TABLE features AS
        SELECT
            item_id,
            dept_id,
            cat_id,
            store_id,
            state_id,
            date,
            sales,
            sell_price,
            -- price change vs previous week's price for the same item-store
            sell_price - LAG(sell_price, 7) OVER w AS price_change_7d,
            -- calendar features
            wday,
            month,
            year,
            CASE WHEN wday IN (1, 7) THEN 1 ELSE 0 END AS is_weekend,
            CASE WHEN event_name_1 IS NOT NULL THEN 1 ELSE 0 END AS has_event,
            COALESCE(snap_ca, 0) + COALESCE(snap_tx, 0) + COALESCE(snap_wi, 0) AS snap_active,
            {lag_roll_sql}
        FROM fact_sales
        WINDOW w AS (PARTITION BY item_id, store_id ORDER BY date)
        ORDER BY item_id, store_id, date
    """
    print("Computing lag/rolling/calendar features...")
    con.execute(query)

    # Drop the earliest rows where lag/rolling features are still NULL
    # (not enough history yet for that series).
    con.execute(f"""
        CREATE OR REPLACE TABLE features AS
        SELECT * FROM features
        WHERE lag_{max(config.LAG_DAYS)} IS NOT NULL
    """)

    n_rows = con.execute("SELECT COUNT(*) FROM features").fetchone()[0]
    print(f"features table built: {n_rows:,} rows")

    con.execute(f"""
        COPY features TO '{config.FEATURES_PARQUET.as_posix()}' (FORMAT PARQUET)
    """)
    print(f"Written to {config.FEATURES_PARQUET}")
    con.close()


if __name__ == "__main__":
    run()
