"""SQLite schema introspection, cache, and prompt formatting."""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any

from hornet.config import Settings


def _quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


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
            qname = _quote_ident(name)
            cols = conn.execute(f"PRAGMA table_info({qname})").fetchall()
            sample = conn.execute(f"SELECT * FROM {qname} LIMIT 3").fetchall()
            row_count = conn.execute(f"SELECT COUNT(*) AS n FROM {qname}").fetchone()["n"]

            col_meta: list[dict[str, Any]] = []
            for c in cols:
                col_name = c["name"]
                qcol = _quote_ident(col_name)
                samples: list[Any] = []
                try:
                    sample_rows = conn.execute(
                        f"SELECT DISTINCT {qcol} AS v FROM {qname} "
                        f"WHERE {qcol} IS NOT NULL LIMIT 5"
                    ).fetchall()
                    samples = [r["v"] for r in sample_rows]
                except sqlite3.Error:
                    samples = []

                entry: dict[str, Any] = {
                    "name": col_name,
                    "type": c["type"] or "",
                    "notnull": bool(c["notnull"]),
                    "pk": bool(c["pk"]),
                    "samples": samples,
                }
                if col_name.lower() == "year":
                    try:
                        yr = conn.execute(
                            f"SELECT MIN({qcol}) AS lo, MAX({qcol}) AS hi FROM {qname}"
                        ).fetchone()
                        entry["min"] = yr["lo"]
                        entry["max"] = yr["hi"]
                    except sqlite3.Error:
                        pass
                col_meta.append(entry)

            tables[name] = {
                "columns": col_meta,
                "sample_rows": [dict(r) for r in sample],
                "row_count": row_count,
            }

        return {
            "sport_db": str(db_path),
            "tables": tables,
            "exists": True,
            "table_names": list(tables.keys()),
            "column_index": {
                t: [c["name"] for c in meta["columns"]] for t, meta in tables.items()
            },
        }
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
        col_defs = ", ".join(f"{c['name']} {c['type'] or 'ANY'}" for c in meta["columns"])
        lines.append(f"CREATE TABLE {table} ({col_defs});  -- rows: {meta['row_count']}")
    return "\n".join(lines)


def schema_text_detailed(schema: dict[str, Any], *, max_tables: int | None = None) -> str:
    """Human-readable full catalog: every table, column, type, samples, year range."""
    if not schema.get("exists"):
        return f"Database not found: {schema.get('sport_db')}"

    lines = [
        f"{schema.get('sport_label', schema.get('sport_id', 'sport'))} — {schema.get('sport_db')}",
        f"Tables: {', '.join(schema.get('table_names') or list(schema.get('tables', {})))}",
        "",
    ]
    tables = schema.get("tables", {})
    for i, (table, meta) in enumerate(tables.items()):
        if max_tables is not None and i >= max_tables:
            lines.append(f"... {len(tables) - max_tables} more tables")
            break
        lines.append(f"[{table}]  rows={meta['row_count']}")
        for c in meta["columns"]:
            bits = [c["name"], c.get("type") or "ANY"]
            if c.get("pk"):
                bits.append("PK")
            if "min" in c and "max" in c:
                bits.append(f"range={c['min']}..{c['max']}")
            samples = c.get("samples") or []
            if samples:
                shown = ", ".join(repr(s) for s in samples[:3])
                bits.append(f"e.g. {shown}")
            lines.append("  - " + " | ".join(bits))
        lines.append("")
    return "\n".join(lines).rstrip()


def schema_text_sql(
    schema: dict[str, Any],
    *,
    max_tables: int | None = None,
    tables: list[str] | None = None,
) -> str:
    """Full schema for SQLCoder: types + sample values. Prefer completeness over brevity."""
    if not schema.get("exists"):
        return f"-- missing: {schema.get('sport_db')}"

    all_tables = schema.get("tables", {})
    if tables:
        ordered = [(t, all_tables[t]) for t in tables if t in all_tables]
        # Always note other tables exist so the model knows the DB is larger
        other = [t for t in all_tables if t not in {x[0] for x in ordered}]
    else:
        ordered = list(all_tables.items())
        other = []

    lines: list[str] = [
        f"-- sport={schema.get('sport_id')} tables={len(all_tables)}",
        f"-- ALL TABLES: {', '.join(all_tables.keys())}",
    ]
    if other:
        lines.append(f"-- (focused subset below; also available: {', '.join(other)})")

    for i, (table, meta) in enumerate(ordered):
        if max_tables is not None and i >= max_tables:
            lines.append(f"-- ... truncated {len(ordered) - max_tables} tables")
            break
        lines.append(f"TABLE {table} -- {meta['row_count']} rows")
        for c in meta["columns"]:
            extra = ""
            if "min" in c and "max" in c:
                extra = f"  -- year range {c['min']}..{c['max']}"
            elif c.get("samples"):
                samples = ", ".join(repr(s) for s in c["samples"][:3])
                extra = f"  -- e.g. {samples}"
            lines.append(f"  {c['name']} {c.get('type') or 'ANY'}{extra}")
    return "\n".join(lines)


def nfl_tables_for_question(question: str) -> list[str] | None:
    """Narrow NFL tables to the relevant ones for the question."""
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


def table_columns(schema: dict[str, Any], table: str) -> set[str]:
    meta = schema.get("tables", {}).get(table) or schema.get("tables", {}).get(table.lower())
    if not meta:
        return set()
    return {c["name"].lower() for c in meta["columns"]}


def all_columns(schema: dict[str, Any]) -> set[str]:
    cols: set[str] = set()
    for meta in schema.get("tables", {}).values():
        for c in meta.get("columns", []):
            cols.add(str(c["name"]).lower())
    return cols


def extract_from_tables(sql: str) -> list[str]:
    """Best-effort FROM/JOIN table names from a SELECT."""
    found: list[str] = []
    for m in re.finditer(
        r"\b(?:FROM|JOIN)\s+([A-Za-z_][A-Za-z0-9_]*)",
        sql,
        flags=re.IGNORECASE,
    ):
        found.append(m.group(1))
    return found


def validate_sql_against_schema(sql: str, schema: dict[str, Any]) -> str | None:
    """Return error string if SQL references unknown tables/columns; else None."""
    if not schema.get("exists"):
        return "Database schema missing"
    tables = {t.lower(): t for t in schema.get("tables", {})}
    sql_l = sql.lower()

    used_tables = extract_from_tables(sql)
    if not used_tables:
        return "SQL has no FROM table"
    for t in used_tables:
        if t.lower() not in tables:
            return f"Unknown table {t!r}. Known: {sorted(tables)}"

    # Collect identifiers that look like column refs (skip aliases after AS)
    # Remove string literals first
    scrubbed = re.sub(r"'([^']|'')*'", "''", sql)
    scrubbed = re.sub(r"\bas\s+[A-Za-z_][A-Za-z0-9_]*", " ", scrubbed, flags=re.I)

    keywords = {
        "select",
        "from",
        "where",
        "and",
        "or",
        "group",
        "by",
        "order",
        "desc",
        "asc",
        "limit",
        "as",
        "count",
        "sum",
        "avg",
        "min",
        "max",
        "distinct",
        "join",
        "on",
        "left",
        "right",
        "inner",
        "outer",
        "having",
        "case",
        "when",
        "then",
        "else",
        "end",
        "null",
        "not",
        "in",
        "is",
        "between",
        "like",
        "cast",
        "coalesce",
        "union",
        "all",
        "with",
        "over",
        "partition",
        "row_number",
        "rank",
        "dense_rank",
    }

    # Columns allowed = union of columns from referenced tables
    allowed: set[str] = set()
    for t in used_tables:
        allowed |= table_columns(schema, tables[t.lower()])

    tokens = re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\b", scrubbed)
    unknown: list[str] = []
    for tok in tokens:
        low = tok.lower()
        if low in keywords or low in tables or low in allowed:
            continue
        if low.isdigit():
            continue
        # skip obvious function-ish / alias noise; only flag sport-stat-looking names
        if re.search(
            r"(yds|yard|pts|point|td|touch|three|fg|ast|reb|rush|receiv|goal|sack|int|gp|g|mp|pct|rate|att|cmp)",
            low,
        ):
            unknown.append(tok)
    if unknown:
        return (
            f"Unknown column(s) {sorted(set(unknown))} for tables {used_tables}. "
            f"Allowed columns: {sorted(allowed)}"
        )
    return None


def explain_select(db_path: Path, sql: str) -> str | None:
    """Run EXPLAIN on SELECT; return error message on failure."""
    sql_stripped = sql.strip().rstrip(";")
    if not sql_stripped.lower().startswith("select"):
        return "Only SELECT allowed"
    if not db_path.exists():
        return f"Database not found: {db_path}"
    try:
        with sqlite3.connect(db_path) as conn:
            conn.execute(f"EXPLAIN {sql_stripped}")
        return None
    except sqlite3.Error as exc:
        return str(exc)
