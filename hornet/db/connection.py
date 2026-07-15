from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from hornet.config import Settings


@contextmanager
def connect(db_path: Path) -> Iterator[sqlite3.Connection]:
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def execute_query(db_path: Path, sql: str, *, max_rows: int = 5000) -> dict[str, Any]:
    sql_stripped = sql.strip().rstrip(";")
    if not sql_stripped.lower().startswith("select"):
        raise ValueError("Only SELECT queries are allowed")

    with connect(db_path) as conn:
        cur = conn.execute(sql_stripped)
        rows = cur.fetchmany(max_rows + 1)
        truncated = len(rows) > max_rows
        if truncated:
            rows = rows[:max_rows]
        columns = [d[0] for d in cur.description] if cur.description else []
        return {
            "columns": columns,
            "rows": [dict(r) for r in rows],
            "row_count": len(rows),
            "truncated": truncated,
            "sql": sql_stripped,
        }


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
