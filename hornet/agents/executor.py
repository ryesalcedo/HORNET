from __future__ import annotations

import logging
from typing import Any

from hornet.agents.planner import Plan, PlanStep
from hornet.agents.sql_agent import SQLAgent
from hornet.config import Settings
from hornet.session import Session, ToolResult
from hornet.tools.registry import build_tool_registry, run_tool

logger = logging.getLogger(__name__)


class Executor:
    """Run a plan's tool steps — no LLM except sql_agent for SQL generation."""

    def __init__(self, settings: Settings, sql_agent: SQLAgent) -> None:
        self.settings = settings
        self.sql_agent = sql_agent
        self.registry = build_tool_registry(settings)

    @staticmethod
    def _detail(tool: str, output: Any) -> str:
        if not isinstance(output, dict):
            return tool
        if output.get("error"):
            return f"{tool} ERROR: {output['error']}"
        if tool == "sql_query":
            sql = output.get("generated_sql", "")
            n = output.get("row_count", len(output.get("rows", [])))
            return f"{n} rows | {sql[:140]}"
        if tool == "schema_lookup":
            return f"schema → {output.get('sport')}"
        if tool == "search":
            return f"{len(output.get('matches', []))} matches"
        if tool == "compute_stats":
            return str(output.get("operation", output.get("status", "done")))
        return tool

    def _run_step(self, step: PlanStep, session: Session) -> ToolResult:
        tool, args = step.tool, step.arguments

        if tool == "sql_query":
            sport = args.get("sport")
            question = args.get("question")
            if not sport or not question:
                result = ToolResult(
                    tool=tool,
                    input=args,
                    output={"error": "sql_query requires sport and question"},
                    error="missing sport or question",
                    agent="sql_agent",
                    model=self.settings.sql.model,
                )
            else:
                output = self.sql_agent.run(sport, question, session)
                result = ToolResult(
                    tool=tool,
                    input=args,
                    output=output,
                    error=output.get("error") if isinstance(output, dict) else None,
                    agent="sql_agent",
                    model=self.settings.sql.model,
                )
        elif tool in self.registry:
            output = run_tool(tool, args, session, self.registry)
            agent = "math_agent" if tool == "compute_stats" else "tool"
            result = ToolResult(
                tool=tool,
                input=args,
                output=output,
                error=output.get("error") if isinstance(output, dict) else None,
                agent=agent,
            )
        else:
            result = ToolResult(
                tool=tool,
                input=args,
                output={"error": f"unknown tool: {tool}"},
                error=f"unknown tool: {tool}",
                agent="tool",
            )

        session.add_trace("execute", result.agent, self._detail(tool, result.output), result.model)
        return result

    def run(self, plan: Plan, session: Session) -> list[ToolResult]:
        results: list[ToolResult] = []
        for step in plan.steps:
            result = self._run_step(step, session)
            results.append(result)
            session.record_tool(result)
        return results
