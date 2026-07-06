from __future__ import annotations

import json
import logging
from typing import Any

from hornet.config import Settings
from hornet.db import load_schema_cache, schema_text
from hornet.db.connection import execute_query
from hornet.llm import OllamaClient
from hornet.session import Session

logger = logging.getLogger(__name__)

SQL_SYSTEM = """You are SQLCoder, a SQLite expert for sports analytics.
Rules:
- Output ONLY a single SELECT statement. No markdown, no explanation.
- Use valid SQLite syntax.
- Only read data; never INSERT/UPDATE/DELETE.
- Prefer explicit column names over SELECT *.
- Use LIMIT when returning large sets.
"""


class SQLAgent:
    def __init__(self, settings: Settings, client: OllamaClient) -> None:
        self.settings = settings
        self.client = client

    def generate_sql(self, sport: str, question: str, session: Session) -> str:
        cache = load_schema_cache(self.settings.schema_cache_dir / f"{sport.lower()}.json")
        if cache is None:
            raise RuntimeError(f"Schema cache missing for {sport}. Run build_schema_cache.py")

        schema_block = schema_text(cache)
        context = session.summary_for_prompt()
        prompt = f"""Schema:
{schema_block}

Question: {question}

{f"Prior context:{chr(10)}{context}" if context else ""}

Write the SQL query:"""

        sql = self.client.generate(self.settings.sql, prompt, system=SQL_SYSTEM)
        return sql.strip().strip("`").removeprefix("sql").strip()

    def run(self, sport: str, question: str, session: Session) -> dict[str, Any]:
        sql = self.generate_sql(sport, question, session)
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
