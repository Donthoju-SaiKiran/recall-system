"""SQLite helpers: create the schema and insert generated rows."""
from __future__ import annotations

import sqlite3
from collections.abc import Iterable

from .ddl import build_ddl
from .schema import TABLE_BY_NAME


def create_db(path: str = ":memory:") -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.executescript(build_ddl())
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def insert_rows(conn: sqlite3.Connection, table: str, rows: Iterable[dict]) -> int:
    """Insert dict rows using the column order from schema.py.

    Missing optional keys become NULL. Unknown keys raise, so typos fail loudly.
    """
    cols = [c.name for c in TABLE_BY_NAME[table].cols]
    allowed = set(cols)
    data = []
    for row in rows:
        extra = set(row) - allowed
        if extra:
            raise KeyError(f"{table}: unknown columns {sorted(extra)}")
        data.append(tuple(row.get(c) for c in cols))
    placeholders = ", ".join("?" for _ in cols)
    conn.executemany(f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({placeholders})", data)
    return len(data)
