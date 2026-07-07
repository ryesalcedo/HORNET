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


def schema_text_sql(
    schema: dict[str, Any],
    *,
    max_tables: int = 25,
    tables: list[str] | None = None,
) -> str:
    """Compact schema for SQLCoder — column names only, keeps prompts small."""
    if not schema.get("exists"):
        return f"-- missing: {schema.get('sport_db')}"

    all_tables = schema.get("tables", {})
    if tables:
        ordered = [(t, all_tables[t]) for t in tables if t in all_tables]
    else:
        ordered = list(all_tables.items())

    lines: list[str] = []
    for i, (table, meta) in enumerate(ordered):
        if i >= max_tables:
            break
        cols = ", ".join(c["name"] for c in meta["columns"])
        lines.append(f"-- {table} ({meta['row_count']} rows): {cols}")
    return "\n".join(lines)


def nfl_tables_for_question(question: str) -> list[str] | None:
    """Narrow 19 NFL tables to the relevant ones for the question."""
    q = question.lower()
    if any(w in q for w in ("pass", "quarterback", "qb ")):
        return ["passing", "passing_post"]
    if any(w in q for w in ("rush", "rushing")):
        return ["rushing_and_receiving", "rushing_and_receiving_post"]
    if any(w in q for w in ("receiv", "catch", "rec ")):
        return ["rushing_and_receiving", "rushing_and_receiving_post"]
    if any(w in q for w in ("defense", "tackle", "sack", "interception")):
        return ["defense", "defense_post"]
    if any(w in q for w in ("kick", "field goal", "fg ")):
        return ["kicking", "kicking_post", "scoring"]
    if any(w in q for w in ("game", "score", "week")):
        return ["games", "team_stats"]
    return None
