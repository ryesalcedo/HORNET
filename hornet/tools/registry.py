from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Callable

from hornet.config import Settings
from hornet.db import execute_query, load_schema_cache, schema_text
from hornet.session import Session

ToolFn = Callable[[dict[str, Any], Session], Any]


def _require_sport(args: dict[str, Any]) -> str | None:
    sport = args.get("sport")
    return sport.lower() if sport else None


def _schema_lookup(args: dict[str, Any], session: Session, settings: Settings) -> dict[str, Any]:
    sport_id = _require_sport(args)
    if not sport_id:
        return {"error": "Missing required argument: sport (nba, nfl, or nhl)"}
    cache_path = settings.schema_cache_dir / f"{sport_id}.json"
    schema = load_schema_cache(cache_path)
    if schema is None:
        return {"error": f"No schema cache for {sport_id}. Run: python scripts/build_schema_cache.py"}
    detail = args.get("detail", "summary")
    if detail == "full":
        return schema
    return {"sport": sport_id, "schema_ddl": schema_text(schema)}


def _sql_query(args: dict[str, Any], session: Session, settings: Settings) -> dict[str, Any]:
    sport_id = _require_sport(args)
    if not sport_id:
        return {"error": "Missing required argument: sport (nba, nfl, or nhl)"}
    sql = args.get("sql")
    if not sql:
        return {"error": "Missing required argument: sql (or pass question to SQL agent)"}
    db_path = settings.db_path(sport_id)
    try:
        return execute_query(db_path, sql, max_rows=settings.max_sql_rows)
    except Exception as exc:
        return {"error": str(exc), "sql": sql}


def _search(args: dict[str, Any], session: Session, settings: Settings) -> dict[str, Any]:
    query = args["query"]
    sport = args.get("sport")
    root = settings.schema_cache_dir.parent / "raw"
    search_root = root / sport if sport else root
    if not search_root.exists():
        return {"matches": [], "note": f"Path not found: {search_root}"}

    cmd = ["rg", "--json", "-i", "--max-count", "20", query, str(search_root)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except FileNotFoundError:
        return {"error": "ripgrep (rg) not installed", "query": query}

    matches = []
    for line in proc.stdout.splitlines():
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if obj.get("type") == "match":
            data = obj.get("data", {})
            matches.append(
                {
                    "path": data.get("path", {}).get("text"),
                    "line_number": data.get("line_number"),
                    "line": data.get("lines", {}).get("text", "").strip(),
                }
            )
    return {"query": query, "sport": sport, "matches": matches}


def _compute_stats(args: dict[str, Any], session: Session, settings: Settings) -> dict[str, Any]:
    import numpy as np
    import pandas as pd

    operation = args["operation"]
    series_a = args.get("series_a", [])
    series_b = args.get("series_b", [])

    def _series(name: str, values: list[float]) -> pd.Series:
        return pd.Series(values, dtype="float64", name=name)

    if operation == "describe":
        s = _series("values", series_a)
        return {"describe": s.describe().to_dict()}

    if operation == "compare_means":
        a = _series("a", series_a)
        b = _series("b", series_b)
        return {
            "mean_a": float(a.mean()),
            "mean_b": float(b.mean()),
            "diff": float(a.mean() - b.mean()),
            "pct_diff": float((a.mean() - b.mean()) / b.mean() * 100) if b.mean() else None,
        }

    if operation == "per_game":
        totals = np.array(series_a, dtype=float)
        games = float(args.get("games", 1))
        if games <= 0:
            return {"error": "games must be > 0"}
        return {"per_game": (totals / games).tolist()}

    if operation == "correlation":
        a = _series("a", series_a)
        b = _series("b", series_b)
        if len(a) != len(b) or len(a) < 2:
            return {"error": "series_a and series_b must have equal length >= 2"}
        return {"correlation": float(a.corr(b))}

    return {"error": f"Unknown operation: {operation}"}


TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "schema_lookup",
            "description": "Return cached DDL/schema for an NBA, NFL, or NHL database.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sport": {"type": "string", "enum": ["nba", "nfl", "nhl"]},
                    "detail": {"type": "string", "enum": ["summary", "full"], "default": "summary"},
                },
                "required": ["sport"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "sql_query",
            "description": (
                "Fetch data from a sport SQLite database. "
                "Pass a natural-language question — SQLCoder generates the SQL. "
                "Do NOT write SQL yourself."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "sport": {"type": "string", "enum": ["nba", "nfl", "nhl"]},
                    "question": {
                        "type": "string",
                        "description": "What data to fetch, in plain English",
                    },
                },
                "required": ["sport", "question"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search",
            "description": "Search raw CSV/text files under data/raw with ripgrep.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "sport": {"type": "string", "enum": ["nba", "nfl", "nhl"]},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compute_stats",
            "description": "Deterministic math/stats on numeric series (no LLM).",
            "parameters": {
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "enum": ["describe", "compare_means", "per_game", "correlation"],
                    },
                    "series_a": {"type": "array", "items": {"type": "number"}},
                    "series_b": {"type": "array", "items": {"type": "number"}},
                    "games": {"type": "number"},
                },
                "required": ["operation"],
            },
        },
    },
]


def build_tool_registry(settings: Settings) -> dict[str, ToolFn]:
    """Code-only tools. sql_query is routed through sql_agent in the orchestrator."""
    return {
        "schema_lookup": lambda args, session: _schema_lookup(args, session, settings),
        "search": lambda args, session: _search(args, session, settings),
        "compute_stats": lambda args, session: _compute_stats(args, session, settings),
    }


def run_tool(
    name: str,
    args: dict[str, Any],
    session: Session,
    registry: dict[str, ToolFn],
) -> Any:
    if name not in registry:
        return {"error": f"Unknown tool: {name}"}
    return registry[name](args, session)
