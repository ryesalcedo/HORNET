from __future__ import annotations

import logging
import re
from typing import Any

from hornet.config import Settings
from hornet.db.column_hints import dynamic_hints
from hornet.db import load_schema_cache
from hornet.db.connection import execute_query
from hornet.db.shooting_cols import threes_made_column, threes_pct_column
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
Prefer simple SELECT … WHERE year = … ORDER BY <metric> DESC LIMIT N for leader questions.
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
        if re.search(r"\b(leader|leading|most|highest|best)\b", question.lower()):
            return 5
        if "top player" in question.lower():
            return 1
        return 5

    @staticmethod
    def _is_ambiguous(question: str) -> bool:
        """Skip deterministic fast-path when the ask needs judgment / multi-metric SQL."""
        q = question.lower()
        if re.search(
            r"\b(vs\.?|versus|compare|comparison|correlat|difference|ratio|"
            r"both|either|average of|per game vs|and also)\b",
            q,
        ):
            return True
        if len(re.findall(r"\b(20\d{2})\b", q)) > 1:
            return True
        # two distinct leaderboard metrics in one question
        metrics = 0
        for pat in (
            r"\brush",
            r"\bpass",
            r"\breceiv",
            r"\bpoint",
            r"\bgoal",
            r"\bassists?\b",
            r"\bthree",
            r"\bsack",
        ):
            if re.search(pat, q):
                metrics += 1
        return metrics >= 2

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
        return threes_made_column(columns)

    @classmethod
    def _unsupported_reason(cls, sport: str, question: str, cache: dict[str, Any]) -> str | None:
        cols = all_columns(cache)
        if sport != "nba" or not cls._asks_threes_made(question):
            return None
        made = cls._threes_made_column(cols)
        if made:
            return None
        pct = threes_pct_column(cols)
        if pct:
            return (
                f"Live schema has three-point percentage ({pct}) but no threes-made / 3PM column. "
                "Ask for 3P% leaders, or confirm the makes column name via /schema nba."
            )
        return (
            "Live schema has no three-pointers-made / 3PM column. "
            "Cannot answer 'most threes made'. Run /schema nba to inspect columns."
        )

    def _ensure_valid(self, sport: str, sql: str, cache: dict[str, Any]) -> str:
        bad = validate_sql_against_schema(sql, cache)
        if bad:
            raise RuntimeError(bad)
        if re.search(r"count\s*\(\s*\*\s*\).*three|three.*count\s*\(\s*\*\s*\)", sql, re.I | re.S):
            raise RuntimeError("Rejected SQL: COUNT(*) is not three-pointers made.")
        if re.search(r"pts\s*>=\s*3", sql, re.I) and re.search(r"three", sql, re.I):
            raise RuntimeError("Rejected SQL: pts >= 3 is not three-pointers made.")

        explain_err = explain_select(self.settings.db_path(sport), sql)
        if explain_err:
            raise RuntimeError(f"SQLite rejected SQL: {explain_err}")
        return sql

    @staticmethod
    def _pattern_sql(
        sport: str,
        question: str,
        cache: dict[str, Any],
        *,
        strict: bool,
    ) -> str | None:
        """Deterministic leaderboard SQL when the ask is clear and columns exist.

        strict=True  → fast path (efficiency): only unambiguous leaderboard asks
        strict=False → recovery path after SQLCoder fails validation
        """
        q = question.lower()
        year_match = re.search(r"\b(20\d{2})\b", q)
        year = year_match.group(1) if year_match else None
        if not year:
            return None

        limit = SQLAgent._limit(question)
        cols = all_columns(cache)

        def has(*names: str) -> bool:
            return all(n in cols for n in names)

        leaderish = bool(
            re.search(r"\b(most|highest|leading|leader|top|best|who led|who had)\b", q)
        )
        if strict and not leaderish:
            return None

        if sport == "nba" and SQLAgent._asks_threes_made(question):
            made_col = SQLAgent._threes_made_column(cols)
            if not made_col:
                return None
            table = None
            tables = cache.get("tables") or {}
            if "player_mvp_stats" in tables:
                table = "player_mvp_stats"
            else:
                for tname, meta in tables.items():
                    names = {c["name"].lower() for c in meta["columns"]}
                    if made_col in names:
                        table = tname
                        break
            if not table:
                return None
            pieces = ["player"]
            if "team" in cols:
                pieces.append("team")
            pieces.append(made_col)
            if "g" in cols:
                pieces.append("g")
            select_cols = ", ".join(pieces)
            return (
                f"SELECT {select_cols} FROM {table} "
                f"WHERE year = {year} ORDER BY {made_col} DESC LIMIT {limit}"
            )

        if sport == "nba" and has("player", "pts", "year"):
            scoring = bool(
                re.search(r"\b(ppg|points?\s+per\s+game|scoring)\b", q)
                or re.search(r"\b(most|highest|leading|top)\b.{0,40}\bpoints?\b", q)
                or re.search(r"\bpoints?\b.{0,40}\b(leader|most|highest)\b", q)
            )
            if scoring and not re.search(r"\b(mvp vote|pts_won|pts_max)\b", q):
                select_cols = "player, pts, g" if "g" in cols else "player, pts"
                return (
                    f"SELECT {select_cols} FROM player_mvp_stats "
                    f"WHERE year = {year} ORDER BY pts DESC LIMIT {limit}"
                )

        if sport == "nfl":
            if (
                re.search(r"\b(sack|sacks)\b", q)
                and has("player", "year")
                and ("sk" in cols or "sacks" in cols)
            ):
                sack_col = "sk" if "sk" in cols else "sacks"
                team = ", team" if "team" in cols else ""
                return (
                    f"SELECT player{team}, {sack_col} FROM defense "
                    f"WHERE year = {year} ORDER BY {sack_col} DESC LIMIT {limit}"
                )
            if (
                re.search(r"\b(pass(ing)?|quarterback|\bqb\b)\b", q)
                and re.search(r"\b(yard|yards|yds)\b", q)
                and has("player", "yds", "year")
            ):
                team = ", team" if "team" in cols else ""
                return (
                    f"SELECT player{team}, yds FROM passing "
                    f"WHERE year = {year} ORDER BY yds DESC LIMIT {limit}"
                )
            if (
                re.search(r"\b(pass(ing)?|quarterback|\bqb\b)\b", q)
                and re.search(r"\b(td|tds|touchdown)\b", q)
                and has("player", "td", "year")
            ):
                team = ", team" if "team" in cols else ""
                return (
                    f"SELECT player{team}, td FROM passing "
                    f"WHERE year = {year} ORDER BY td DESC LIMIT {limit}"
                )
            if (
                re.search(r"\b(rush|rushing)\b", q)
                and re.search(r"\b(yard|yards|yds)\b", q)
                and has("player", "rushing_yds", "year")
            ):
                team = ", team" if "team" in cols else ""
                return (
                    f"SELECT player{team}, rushing_yds FROM rushing_and_receiving "
                    f"WHERE year = {year} ORDER BY rushing_yds DESC LIMIT {limit}"
                )
            if (
                re.search(r"\b(receiv|receiving|reception)\b", q)
                and re.search(r"\b(yard|yards|yds)\b", q)
                and has("player", "receiving_yds", "year")
            ):
                team = ", team" if "team" in cols else ""
                return (
                    f"SELECT player{team}, receiving_yds FROM rushing_and_receiving "
                    f"WHERE year = {year} ORDER BY receiving_yds DESC LIMIT {limit}"
                )

        if sport == "nhl" and has("player", "player_pts", "year"):
            points = bool(
                re.search(r"\b(player[_\s]?pts|scoring leader|point leaders?)\b", q)
                or re.search(r"\b(most|highest|leading|top)\b.{0,40}\bpoints?\b", q)
            )
            if points or (not strict and re.search(r"\bpoints?\b", q)):
                extra = [c for c in ("team_full", "player_gp", "g", "a") if c in cols]
                select_cols = ", ".join(["player", *extra, "player_pts"])
                return (
                    f"SELECT {select_cols} FROM player_team_stats "
                    f"WHERE year = {year} ORDER BY player_pts DESC LIMIT {limit}"
                )

        return None

    def _schema_block(self, cache: dict, sport: str, question: str) -> str:
        tables = nfl_tables_for_question(question) if sport == "nfl" else None
        return schema_text_sql(cache, tables=tables, max_tables=None)

    def _sqlcoder(self, sport: str, question: str, cache: dict[str, Any]) -> str:
        prompt = (
            f"Schema:\n{self._schema_block(cache, sport, question)}\n\n"
            f"Hints:\n{dynamic_hints(sport, cache)}\n\n"
            f"Question: {question}\n\nSQL:"
        )
        with self.models.use(self.settings.sql) as model_cfg:
            raw = self.client.generate_completion(model_cfg, prompt, prefix=SQL_PREFIX)
        return self._clean_sql(raw)

    def _generate(self, sport: str, question: str) -> str:
        sport = sport.lower()
        cache = load_schema_cache(self.settings.schema_cache_dir / f"{sport}.json")
        if cache is None:
            raise RuntimeError(
                f"No schema cache for {sport} — run: python scripts/build_schema_cache.py"
            )
        if not cache.get("exists"):
            raise RuntimeError(f"Database missing for {sport}: {cache.get('sport_db')}")

        unsupported = self._unsupported_reason(sport, question, cache)
        if unsupported:
            raise RuntimeError(unsupported)

        # 1) Fast path — high-confidence leaderboard patterns (no LLM round-trip)
        if not self._is_ambiguous(question):
            fast = self._pattern_sql(sport, question, cache, strict=True)
            if fast:
                try:
                    sql = self._ensure_valid(sport, fast, cache)
                    logger.info("sql_agent: fast-path pattern")
                    return sql
                except RuntimeError as exc:
                    logger.warning("sql_agent: fast-path rejected (%s)", exc)

        # 2) SQLCoder with full live schema
        raw_sql = self._sqlcoder(sport, question, cache)
        if raw_sql == "UNSUPPORTED":
            raise RuntimeError(
                f"Schema for {sport} cannot answer this question with available columns. "
                f"Known tables: {cache.get('table_names', [])}"
            )
        if raw_sql.upper().startswith("SELECT"):
            try:
                sql = self._ensure_valid(sport, raw_sql, cache)
                logger.info("sql_agent: SQLCoder")
                return sql
            except RuntimeError as exc:
                logger.warning("sql_agent: SQLCoder rejected (%s)", exc)
        else:
            logger.warning("sql_agent: SQLCoder non-SELECT (%r)", raw_sql[:80])

        # 3) Recovery — looser patterns after LLM failure
        recovery = self._pattern_sql(sport, question, cache, strict=False)
        if recovery:
            sql = self._ensure_valid(sport, recovery, cache)
            logger.info("sql_agent: recovery pattern")
            return sql

        raise RuntimeError(
            f"Could not produce valid SQL for {sport!r}. "
            f"Last model output: {raw_sql[:160]!r}"
        )

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
