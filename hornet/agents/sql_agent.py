from __future__ import annotations

import logging
import re
from typing import Any

from hornet.config import Settings
from hornet.db.column_hints import SPORT_HINTS
from hornet.db import load_schema_cache
from hornet.db.connection import execute_query
from hornet.db.schema import nfl_tables_for_question, schema_text_sql
from hornet.llm.model_manager import ModelManager
from hornet.llm.ollama_client import OllamaClient
from hornet.session import Session

logger = logging.getLogger(__name__)

SQL_PREFIX = """You are SQLCoder. Output ONE SQLite SELECT statement.
Use ONLY column names that appear in the schema list. Never invent columns.
Never substitute a different metric (e.g. do not use pts or COUNT(*) for threes made).
If the schema cannot answer the question, output exactly: UNSUPPORTED
No markdown."""


class SQLAgent:
    def __init__(self, settings: Settings, client: OllamaClient, models: ModelManager) -> None:
        self.settings = settings
        self.client = client
        self.models = models

    @staticmethod
    def _clean_sql(raw: str) -> str:
        sql = raw.strip().strip("`").removeprefix("sql").strip()
        if "```" in sql:
            sql = sql.split("```")[0].strip()
        if re.search(r"\bUNSUPPORTED\b", sql, re.IGNORECASE):
            return "UNSUPPORTED"
        match = re.search(r"(SELECT\b.+)", sql, re.IGNORECASE | re.DOTALL)
        if match:
            sql = match.group(1)
        sql = sql.split(";")[0].strip()
        sql = re.sub(r"\s+NULLS\s+LAST", "", sql, flags=re.IGNORECASE)
        return sql

    @staticmethod
    def _limit(question: str) -> int:
        if m := re.search(r"top\s+(\d+)", question.lower()):
            return int(m.group(1))
        if re.search(r"\bleader\b", question.lower()) or "top player" in question.lower():
            return 1
        return 5

    @staticmethod
    def _schema_columns(cache: dict[str, Any]) -> set[str]:
        cols: set[str] = set()
        for meta in cache.get("tables", {}).values():
            for c in meta.get("columns", []):
                cols.add(str(c["name"]).lower())
        return cols

    @staticmethod
    def _asks_threes_made(question: str) -> bool:
        q = question.lower()
        if not re.search(r"\b(three|threes|3[- ]?pt|3pm|3p)\b", q):
            return False
        # percentage questions are fine if a pct column exists
        if re.search(r"\b(pct|percent|percentage|%)\b", q):
            return False
        return True

    @staticmethod
    def _threes_made_column(columns: set[str]) -> str | None:
        """Return a season/total threes-made column if present (not percentage)."""
        candidates = (
            "fg3",
            "fg3m",
            "x3p",
            "c_3p",
            "three_pm",
            "threes",
            "tpm",
            "made_3",
            "threes_made",
        )
        for name in candidates:
            if name in columns:
                return name
        # prefer non-pct columns that look like 3p made
        for name in sorted(columns):
            if re.search(r"(^|_)(3p|fg3|three)", name) and "pct" not in name and "attempt" not in name:
                return name
        return None

    @classmethod
    def _unsupported_reason(cls, sport: str, question: str, cache: dict[str, Any]) -> str | None:
        cols = cls._schema_columns(cache)
        if sport == "nba" and cls._asks_threes_made(question) and not cls._threes_made_column(cols):
            return (
                "This NBA database (player_mvp_stats) has no three-pointers-made / 3PM column. "
                "It only has MVP voting and per-game box stats (and 3P% if present). "
                "Cannot answer 'most threes made' from this data."
            )
        return None

    @classmethod
    def _validate_sql(cls, sql: str, cache: dict[str, Any]) -> str | None:
        """Return an error message if SQL references unknown identifiers suspiciously."""
        cols = cls._schema_columns(cache)
        tables = {t.lower() for t in cache.get("tables", {})}
        # crude token scan — catch invented aliases used as source columns
        tokens = set(re.findall(r"\b[a-z_][a-z0-9_]*\b", sql.lower()))
        sql_keywords = {
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
        }
        # known bad pattern: counting rows / pts threshold as "threes"
        if re.search(r"count\s*\(\s*\*\s*\).*three|three.*count\s*\(\s*\*\s*\)", sql, re.I | re.S):
            return "Rejected SQL: COUNT(*) is not three-pointers made."
        if re.search(r"pts\s*>=\s*3", sql, re.I) and "three" in sql.lower():
            return "Rejected SQL: pts >= 3 is not three-pointers made."

        # if SELECT aliases invent three_count without a real 3p source column
        if "three_count" in tokens or "threes" in tokens:
            if not cls._threes_made_column(cols):
                return "Rejected SQL: no threes-made column in schema."

        unknown = []
        for tok in tokens:
            if tok in sql_keywords or tok in cols or tok in tables:
                continue
            if tok.isdigit():
                continue
            # allow common aliases
            if tok.endswith("_count") or tok in {"player", "team", "year"}:
                continue
            # flag tokens that look like columns but aren't in schema
            if re.search(r"(yds|pts|td|three|fg|ast|reb|g|mp)", tok) and tok not in cols:
                unknown.append(tok)
        if unknown:
            return f"Rejected SQL: unknown columns {sorted(set(unknown))} not in schema."
        return None

    @staticmethod
    def _fallback_sql(sport: str, question: str) -> str | None:
        """Deterministic SQL for common patterns when SQLCoder fails."""
        q = question.lower()
        year_match = re.search(r"\b(20\d{2})\b", q)
        year = year_match.group(1) if year_match else None
        limit = SQLAgent._limit(question)

        # Never invent threes-made SQL — handled by _unsupported_reason
        if sport == "nba" and SQLAgent._asks_threes_made(question):
            return None

        if sport == "nba" and year and re.search(r"point|scor|ppg", q):
            cols = "player, pts, g" if limit == 1 else "player, pts"
            return (
                f"SELECT {cols} FROM player_mvp_stats "
                f"WHERE year = {year} ORDER BY pts DESC LIMIT {limit}"
            )

        if sport == "nfl" and year:
            if re.search(r"pass", q) and re.search(r"yard|yds", q):
                return (
                    f"SELECT player, team, yds FROM passing "
                    f"WHERE year = {year} ORDER BY yds DESC LIMIT {limit}"
                )
            if re.search(r"pass", q) and re.search(r"td|touchdown", q):
                return (
                    f"SELECT player, team, td FROM passing "
                    f"WHERE year = {year} ORDER BY td DESC LIMIT {limit}"
                )
            if re.search(r"rush", q) and re.search(r"yard|yds", q):
                return (
                    f"SELECT player, team, rushing_yds FROM rushing_and_receiving "
                    f"WHERE year = {year} ORDER BY rushing_yds DESC LIMIT {limit}"
                )
            if re.search(r"receiv", q) and re.search(r"yard|yds", q):
                return (
                    f"SELECT player, team, receiving_yds FROM rushing_and_receiving "
                    f"WHERE year = {year} ORDER BY receiving_yds DESC LIMIT {limit}"
                )

        if sport == "nhl" and year and re.search(r"point|scor", q):
            cols = (
                "player, team_full, player_pts, player_gp, g, a"
                if limit == 1
                else "player, team_full, player_pts, player_gp, g, a"
            )
            return (
                f"SELECT {cols} FROM player_team_stats "
                f"WHERE year = {year} ORDER BY player_pts DESC LIMIT {limit}"
            )

        return None

    def _schema_block(self, cache: dict, sport: str, question: str) -> str:
        tables = nfl_tables_for_question(question) if sport == "nfl" else None
        return schema_text_sql(cache, tables=tables)

    def _generate(self, sport: str, question: str) -> str:
        cache = load_schema_cache(self.settings.schema_cache_dir / f"{sport.lower()}.json")
        if cache is None:
            raise RuntimeError(f"No schema cache for {sport}")

        unsupported = self._unsupported_reason(sport.lower(), question, cache)
        if unsupported:
            raise RuntimeError(unsupported)

        prompt = (
            f"Schema:\n{self._schema_block(cache, sport.lower(), question)}\n\n"
            f"Hints:\n{SPORT_HINTS.get(sport.lower(), '')}\n\n"
            f"Question: {question}\n\nSQL:"
        )

        # Try fallback first for known patterns — faster and more reliable than SQLCoder
        fallback = self._fallback_sql(sport, question)
        if fallback:
            logger.info("sql_agent: using pattern fallback")
            return fallback

        with self.models.use(self.settings.sql) as model_cfg:
            raw = self.client.generate_completion(model_cfg, prompt, prefix=SQL_PREFIX)

        sql = self._clean_sql(raw)
        if sql == "UNSUPPORTED":
            raise RuntimeError(
                f"Schema for {sport} cannot answer this question with available columns."
            )
        if sql.upper().startswith("SELECT"):
            bad = self._validate_sql(sql, cache)
            if bad:
                raise RuntimeError(bad)
            return sql

        logger.warning("sql_agent: SQLCoder failed (%r), using fallback if possible", raw[:80])
        fallback = self._fallback_sql(sport, question)
        if fallback:
            return fallback
        raise RuntimeError(f"SQLCoder returned invalid SQL: {raw[:120]!r}")

    def run(self, sport: str, question: str, session: Session) -> dict[str, Any]:
        try:
            sql = self._generate(sport, question)
        except Exception as exc:
            return {"error": str(exc)}

        logger.info("sql_agent: %s", sql[:180])
        try:
            result = execute_query(
                self.settings.db_path(sport),
                sql,
                max_rows=self.settings.max_sql_rows,
            )
        except Exception as exc:
            result = {"error": str(exc), "sql": sql}
        result["generated_sql"] = sql
        return result
