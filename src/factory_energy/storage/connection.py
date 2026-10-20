from __future__ import annotations

from pathlib import Path

import duckdb


def open_local(path: str | Path = ":memory:", read_only: bool = False) -> duckdb.DuckDBPyConnection:
    """Open a local DuckDB file (or an in-memory database); connection strings are rejected."""
    value = str(path)
    lowered = value.lower()
    if value != ":memory:" and any(token in lowered for token in ("server=", "driver=", "://")):
        raise ValueError("DuckDB path must be a local file, not a connection string")
    if value != ":memory:":
        Path(value).parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(value, read_only=read_only)
