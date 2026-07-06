from __future__ import annotations

import json
import logging
from typing import Any

from hornet.agents.sql_agent import SQLAgent
from hornet.agents.stats_agent import StatsAgent
from hornet.config import Settings
from hornet.llm import OllamaClient
from hornet.session import Session, ToolResult
from hornet.tools import TOOL_DEFINITIONS, build_tool_registry, run_tool

logger = logging.getLogger(__name__)

ORCHESTRATOR_SYSTEM = """You are HORNET, a local sports analytics orchestrator for NBA, NFL, and NHL data.

You coordinate tools to answer multi-step questions. You do NOT guess stats — call tools.

Available capabilities:
- schema_lookup: inspect table/column layout per sport
- sql_query: run SELECT queries (prefer after schema_lookup when unsure)
- search: ripgrep raw CSV files under data/raw
- compute_stats: deterministic math on numeric arrays (describe, compare_means, per_game, correlation)

Workflow tips:
1. For database questions → schema_lookup then sql_query (or ask SQL agent via natural question in sql)
2. For cross-sport comparisons → query each sport, then compute_stats
3. For narrative stats interpretation → set needs_stats_narrative=true in your final JSON

When you have enough information, respond with JSON only:
{
  "final_answer": "markdown answer for the user",
  "needs_stats_narrative": false,
  "stats_context": {}
}

If you need a tool, respond with JSON only:
{
  "tool": "tool_name",
  "arguments": { ... }
}
"""


class Orchestrator:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = OllamaClient(settings)
        self.registry = build_tool_registry(settings)
        self.sql_agent = SQLAgent(settings, self.client)
        self.stats_agent = StatsAgent(settings, self.client)

    def _call_orchestrator(self, session: Session) -> dict[str, Any]:
        messages: list[dict[str, str]] = [
            {"role": "system", "content": ORCHESTRATOR_SYSTEM},
            *session.messages,
        ]
        if session.tool_results:
            messages.append(
                {
                    "role": "user",
                    "content": session.summary_for_prompt(),
                }
            )

        raw = self.client.chat(
            self.settings.orchestrator,
            messages,
            format_json=True,
        )
        content = raw.get("message", {}).get("content", "{}")
        try:
            return self.client.parse_json_content(content)
        except json.JSONDecodeError:
            return {"final_answer": content, "needs_stats_narrative": False}

    def _maybe_narrate(self, question: str, decision: dict[str, Any], session: Session) -> str:
        if not decision.get("needs_stats_narrative"):
            return str(decision.get("final_answer", ""))

        stats_context = decision.get("stats_context") or {
            "tool_results": session.last_results(10),
        }
        narrative = self.stats_agent.explain(question, stats_context, session)
        self.stats_agent.unload()
        return narrative

    def _handle_nl_sql(self, tool: str, args: dict[str, Any], session: Session) -> ToolResult:
        """Allow orchestrator to pass a natural-language question instead of raw SQL."""
        if tool == "sql_query" and "question" in args and "sql" not in args:
            sport = args["sport"]
            question = args["question"]
            output = self.sql_agent.run(sport, question, session)
            return ToolResult(tool="sql_query", input=args, output=output)

        output = run_tool(tool, args, session, self.registry)
        return ToolResult(tool=tool, input=args, output=output)

    def run(self, question: str, session: Session | None = None) -> str:
        session = session or Session()
        session.add_user(question)

        for round_idx in range(self.settings.max_tool_rounds):
            decision = self._call_orchestrator(session)
            logger.info("orchestrator round %s: %s", round_idx, list(decision.keys()))

            if "tool" in decision:
                tool = decision["tool"]
                args = decision.get("arguments", {})
                result = self._handle_nl_sql(tool, args, session)
                session.record_tool(result)
                if result.error:
                    session.messages.append(
                        {
                            "role": "user",
                            "content": f"Tool {tool} error: {result.error}",
                        }
                    )
                continue

            if "final_answer" in decision:
                answer = self._maybe_narrate(question, decision, session)
                session.add_assistant(answer)
                return answer

            # Fallback: treat unknown shape as final text
            text = json.dumps(decision, indent=2)
            session.add_assistant(text)
            return text

        return "Reached max tool rounds without a final answer. Check logs or rephrase."
