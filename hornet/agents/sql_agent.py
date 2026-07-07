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
Use only columns listed in the schema. No markdown."""


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
    def _fallback_sql(sport: str, question: str) -> str | None:
        """Deterministic SQL for common patterns when SQLCoder fails."""
        q = question.lower()
        year_match = re.search(r"\b(20\d{2})\b", q)
        year = year_match.group(1) if year_match else None
        limit = SQLAgent._limit(question)

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
        if sql.upper().startswith("SELECT"):
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
