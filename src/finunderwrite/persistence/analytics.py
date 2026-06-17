"""Read-only DuckDB analytics layer over processed files / the app DB.

Local analytics convenience only; never used on the request path. DuckDB opens
data in read-only mode so it cannot mutate the operational store.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from config.settings import Settings, get_settings

if TYPE_CHECKING:
    import pandas as pd


def query_processed_csv(sql: str, settings: Settings | None = None) -> pd.DataFrame:
    """Run a DuckDB SQL query; CSVs under data/processed are queryable by path.

    Example: ``SELECT * FROM read_csv_auto('.../synthetic_gaussian_copula_100.csv')``.
    """
    import duckdb

    settings = settings or get_settings()
    con = duckdb.connect(database=":memory:", read_only=False)
    try:
        con.execute(f"SET home_directory='{settings.data_processed.as_posix()}'")
        return con.execute(sql).fetch_df()
    finally:
        con.close()


def read_csv(path: Path) -> pd.DataFrame:
    """Read a single processed CSV via DuckDB into a DataFrame."""
    import duckdb

    con = duckdb.connect(database=":memory:")
    try:
        return con.execute("SELECT * FROM read_csv_auto(?)", [str(path)]).fetch_df()
    finally:
        con.close()


def summarize(path: Path) -> dict[str, Any]:
    """Return a small numeric summary (row count, column means) for a CSV."""
    df = read_csv(path)
    numeric = df.select_dtypes(include="number")
    return {
        "rows": int(len(df)),
        "columns": list(df.columns),
        "means": {c: float(numeric[c].mean()) for c in numeric.columns},
    }
