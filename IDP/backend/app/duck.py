"""DuckDB connection helpers sized from PC RAM/CPU (or env overrides)."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

import duckdb

from .config import duckdb_memory_gb, duckdb_threads, temp_dir


def quote_ident(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def quote_path(path: object) -> str:
    text = str(path).replace("'", "''")
    return f"'{text}'"


@contextmanager
def duck_connection() -> Iterator[duckdb.DuckDBPyConnection]:
    con = duckdb.connect(database=":memory:")
    try:
        mem = duckdb_memory_gb()
        threads = duckdb_threads()
        tmp = temp_dir()
        con.execute(f"SET memory_limit='{mem}GB'")
        con.execute(f"SET threads={int(threads)}")
        con.execute(f"SET temp_directory={quote_path(tmp)}")
        yield con
    finally:
        con.close()
