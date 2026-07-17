from __future__ import annotations

import logging
import re
from typing import Any

from hornet.config import Settings
from hornet.db.column_hints import dynamic_hints
from hornet.db import load_schema_cache
from hornet.db.connection import execute_query
from hornet.db.schema import (
    all_columns,
    explain_select,
    nfl_tables_for_question,
    schema_text_sql,
    validate_sql_against_schema,
)
from hornet.llm.model_manager import ModelManager
from hornet.llm.ollama_client import OllamaClient
from hornet.session import Session

logger = logging.getLogger(__name__)

SQL_PREFIX = """You are SQLCoder. Output ONE SQLite SELECT statement.
The LIVE SCHEMA block lists every real table and column — use ONLY those names.
Never invent columns. Never substitute a different metric for a missing one.
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
    def _asks_threes_made(question: str) -> bool:
        q = question.lower()
        if not re.search(r"\b(three|threes|3[- ]?pt|3pm|3p)\b", q):
            return False
        if re.search(r"\b(pct|percent|percentage|%)\b", q):
            return False
        return True

    @staticmethod
    def _threes_made_column(columns: set[str]) -> str | None:
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
        for name in sorted(columns):
            if re.search(r"(^|_)(3p|fg3|three)", name) and "pct" not in name and "attempt" not in name:
                return name
        return None

    @classmethod
    def _unsupported_reason(cls, sport: str, question: str, cache: dict[str, Any]) -> str | None:
        cols = all_columns(cache)
        if sport == "nba" and cls._asks_threes_made(question) and not cls._threes_made_column(cols):
            return (
                "This NBA database has no three-pointers-made / 3PM column in the live schema. "
                "Cannot answer 'most threes made' from available columns."
            )
        return None

    def _ensure_valid(self, sport: str, sql: str, cache: dict[str, Any]) -> str:
        """Validate against cached schema + SQLite EXPLAIN; raise on failure."""
        bad = validate_sql_against_schema(sql, cache)
        if bad:
            raise RuntimeError(bad)
        if re.search(r"count\s*\(\s*\*\s*\).*three|three.*count\s*\(\s*\*\s*\)", sql, re.I | re.S):
            raise RuntimeError("Rejected SQL: COUNT(*) is not three-pointers made.")
        if re.search(r"pts\s*>=\s*3", sql, re.I) and re.search(r"three", sql, re.I):
            raise RuntimeError("Rejected SQL: pts >= 3 is not three-pointers made.")

        db_path = self.settings.db_path(sport)
        explain_err = explain_select(db_path, sql)
        if explain_err:
            raise RuntimeError(f"SQLite rejected SQL: {explain_err}")
        return sql

    @staticmethod
    def _fallback_sql(sport: str, question: str, cache: dict[str, Any]) -> str | None:
        """Deterministic SQL for common patterns — only if columns exist in live schema."""
        q = question.lower()
        year_match = re.search(r"\b(20\d{2})\b", q)
        year = year_match.group(1) if year_match else None
        limit = SQLAgent._limit(question)
        cols = all_columns(cache)

        if sport == "nba" and SQLAgent._asks_threes_made(question):
            return None

        def has(*names: str) -> bool:
            return all(n in cols for n in names)

        if sport == "nba" and year and re.search(r"point|scor|ppg", q) and has("player", "pts", "year"):
            select_cols = "player, pts, g" if limit == 1 and "g" in cols else "player, pts"
            return (
                f"SELECT {select_cols} FROM player_mvp_stats "
                f"WHERE year = {year} ORDER BY pts DESC LIMIT {limit}"
            )

        if sport == "nfl" and year:
            if re.search(r"pass", q) and re.search(r"yard|yds", q) and has("player", "yds", "year"):
                team = ", team" if "team" in cols else ""
                return (
                    f"SELECT player{team}, yds FROM passing "
                    f"WHERE year = {year} ORDER BY yds DESC LIMIT {limit}"
                )
            if re.search(r"pass", q) and re.search(r"td|touchdown", q) and has("player", "td", "year"):
                team = ", team" if "team" in cols else ""
                return (
                    f"SELECT player{team}, td FROM passing "
                    f"WHERE year = {year} ORDER BY td DESC LIMIT {limit}"
                )
            if (
                re.search(r"rush", q)
                and re.search(r"yard|yds", q)
                and has("player", "rushing_yds", "year")
            ):
                team = ", team" if "team" in cols else ""
                return (
                    f"SELECT player{team}, rushing_yds FROM rushing_and_receiving "
                    f"WHERE year = {year} ORDER BY rushing_yds DESC LIMIT {limit}"
                )
            if (
                re.search(r"receiv", q)
                and re.search(r"yard|yds", q)
                and has("player", "receiving_yds", "year")
            ):
                team = ", team" if "team" in cols else ""
                return (
                    f"SELECT player{team}, receiving_yds FROM rushing_and_receiving "
                    f"WHERE year = {year} ORDER BY receiving_yds DESC LIMIT {limit}"
                )

        if (
            sport == "nhl"
            and year
            and re.search(r"point|scor", q)
            and has("player", "player_pts", "year")
        ):
            extra = []
            for c in ("team_full", "player_gp", "g", "a"):
                if c in cols:
                    extra.append(c)
            select_cols = ", ".join(["player", *extra, "player_pts"])
            return (
                f"SELECT {select_cols} FROM player_team_stats "
                f"WHERE year = {year} ORDER BY player_pts DESC LIMIT {limit}"
            )

        return None

    def _schema_block(self, cache: dict, sport: str, question: str) -> str:
        tables = nfl_tables_for_question(question) if sport == "nfl" else None
        # No table cap — SQLCoder must see the full focused set
        return schema_text_sql(cache, tables=tables, max_tables=None)

    def _generate(self, sport: str, question: str) -> str:
        sport = sport.lower()
        cache = load_schema_cache(self.settings.schema_cache_dir / f"{sport}.json")
        if cache is None:
            raise RuntimeError(f"No schema cache for {sport} — run: python scripts/build_schema_cache.py")
        if not cache.get("exists"):
            raise RuntimeError(f"Database missing for {sport}: {cache.get('sport_db')}")

        unsupported = self._unsupported_reason(sport, question, cache)
        if unsupported:
            raise RuntimeError(unsupported)

        prompt = (
            f"Schema:\n{self._schema_block(cache, sport, question)}\n\n"
            f"Hints:\n{dynamic_hints(sport, cache)}\n\n"
            f"Question: {question}\n\nSQL:"
        )

        fallback = self._fallback_sql(sport, question, cache)
        if fallback:
            logger.info("sql_agent: using pattern fallback")
            return self._ensure_valid(sport, fallback, cache)

        with self.models.use(self.settings.sql) as model_cfg:
            raw = self.client.generate_completion(model_cfg, prompt, prefix=SQL_PREFIX)

        sql = self._clean_sql(raw)
        if sql == "UNSUPPORTED":
            raise RuntimeError(
                f"Schema for {sport} cannot answer this question with available columns. "
                f"Known tables: {cache.get('table_names', [])}"
            )
        if sql.upper().startswith("SELECT"):
            try:
                return self._ensure_valid(sport, sql, cache)
            except RuntimeError as exc:
                logger.warning("sql_agent: rejected generated SQL (%s)", exc)
                fallback = self._fallback_sql(sport, question, cache)
                if fallback:
                    return self._ensure_valid(sport, fallback, cache)
                raise

        logger.warning("sql_agent: SQLCoder failed (%r)", raw[:80])
        fallback = self._fallback_sql(sport, question, cache)
        if fallback:
            return self._ensure_valid(sport, fallback, cache)
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
