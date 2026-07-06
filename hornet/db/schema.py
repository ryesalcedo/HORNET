from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from hornet.config import Settings


def introspect_database(db_path: Path) -> dict[str, Any]:
    if not db_path.exists():
        return {"sport_db": str(db_path), "tables": {}, "exists": False}

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        tables: dict[str, Any] = {}
        table_rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        for row in table_rows:
            name = row["name"]
            cols = conn.execute(f"PRAGMA table_info({name})").fetchall()
            sample = conn.execute(f"SELECT * FROM {name} LIMIT 3").fetchall()
            tables[name] = {
                "columns": [
                    {
                        "name": c["name"],
                        "type": c["type"],
                        "notnull": bool(c["notnull"]),
                        "pk": bool(c["pk"]),
                    }
                    for c in cols
                ],
                "sample_rows": [dict(r) for r in sample],
                "row_count": conn.execute(f"SELECT COUNT(*) AS n FROM {name}").fetchone()["n"],
            }
        return {"sport_db": str(db_path), "tables": tables, "exists": True}
    finally:
        conn.close()


def load_schema_cache(cache_path: Path) -> dict[str, Any] | None:
    if not cache_path.exists():
        return None
    with open(cache_path) as f:
        return json.load(f)


def save_schema_cache(cache_path: Path, schema: dict[str, Any]) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_path, "w") as f:
        json.dump(schema, f, indent=2, default=str)


def build_all_schema_caches(settings: Settings) -> dict[str, dict[str, Any]]:
    settings.schema_cache_dir.mkdir(parents=True, exist_ok=True)
    out: dict[str, dict[str, Any]] = {}
    for sport in settings.sports:
        schema = introspect_database(sport.database)
        schema["sport_id"] = sport.id
        schema["sport_label"] = sport.label
        cache_path = settings.schema_cache_dir / f"{sport.id}.json"
        save_schema_cache(cache_path, schema)
        out[sport.id] = schema
    return out


def schema_text(schema: dict[str, Any], *, max_tables: int = 40) -> str:
    if not schema.get("exists"):
        return f"Database not found: {schema.get('sport_db')}"

    lines = [f"-- {schema.get('sport_label', schema.get('sport_id', 'sport'))} schema"]
    tables = schema.get("tables", {})
    for i, (table, meta) in enumerate(tables.items()):
        if i >= max_tables:
            lines.append(f"-- ... {len(tables) - max_tables} more tables")
            break
        col_defs = ", ".join(f"{c['name']} {c['type']}" for c in meta["columns"])
        lines.append(f"CREATE TABLE {table} ({col_defs});  -- rows: {meta['row_count']}")
    return "\n".join(lines)
