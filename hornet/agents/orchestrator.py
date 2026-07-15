from __future__ import annotations

import json
import logging
from typing import Any

from hornet.agents.executor import Executor
from hornet.agents.math_agent import MathAgent
from hornet.agents.planner import PLANNER_SYSTEM, Plan, build_data_plan, fallback_plan, parse_plan
from hornet.agents.sql_agent import SQLAgent
from hornet.agents.stats_agent import StatsAgent
from hornet.config import Settings
from hornet.llm import OllamaClient
from hornet.llm.model_manager import ModelManager
from hornet.session import Session

logger = logging.getLogger(__name__)

SYNTHESIZER_SYSTEM = """You are HORNET. Write a clear answer using tool results and math_analysis.

Rules:
- Use math_analysis for ALL comparisons and calculated numbers — never do math yourself
- If math_analysis.comparable is false, explain why metrics differ; do NOT pick a winner
- Present each profile/leaders table from the data
- Plain markdown only — no LaTeX
- Be concise"""


class Orchestrator:
    """
    3-phase agent flow:
      1. PLAN    — router (code) or orchestrator (complex)
      2. EXECUTE — sql_agent + tools
      2b. MATH   — math_agent (deterministic, no LLM)
      3. ANSWER  — orchestrator synthesizes from math + data
      Optional: stats_agent (Mathstral narrative)
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = OllamaClient(settings)
        self.models = ModelManager(settings, self.client)
        self.sql_agent = SQLAgent(settings, self.client, self.models)
        self.math_agent = MathAgent()
        self.stats_agent = StatsAgent(settings, self.client, self.models)
        self.executor = Executor(settings, self.sql_agent)

    def _plan(self, question: str, session: Session) -> Plan:
        plan = build_data_plan(question)
        if plan is not None:
            if plan.mode == "direct":
                session.add_trace("plan", "router", "direct answer (no LLM)")
            else:
                parts = [f"{s.tool}({s.arguments.get('sport', '?')})" for s in plan.steps]
                session.add_trace("plan", "router", f"{' → '.join(parts)}")
            return plan

        session.add_trace("plan", "orchestrator", "LLM execution plan", self.settings.orchestrator.model)

        with self.models.use(self.settings.orchestrator) as model_cfg:
            raw = self.client.chat(
                model_cfg,
                [
                    {"role": "system", "content": PLANNER_SYSTEM},
                    {"role": "user", "content": question},
                ],
                format_json=True,
            )

        try:
            decision = self.client.parse_json_content(raw.get("message", {}).get("content", "{}"))
            plan = parse_plan(decision, question)
        except (json.JSONDecodeError, TypeError, ValueError):
            logger.warning("planner JSON failed, using fallback")
            plan = fallback_plan(question)

        if plan.mode == "data":
            step_desc = ", ".join(s.tool for s in plan.steps) or "none"
            session.add_trace("plan", "orchestrator", f"steps: {step_desc}", self.settings.orchestrator.model)
        return plan

    def _synthesize(self, question: str, session: Session, plan: Plan) -> str:
        session.add_trace("synthesize", "orchestrator", "answer from tool results", self.settings.orchestrator.model)

        payload = json.dumps(session.last_results(12), indent=2, default=str)[:10000]
        math_block = json.dumps(session.scratch.get("math_analysis", {}), indent=2, default=str)
        with self.models.use(self.settings.orchestrator) as model_cfg:
            raw = self.client.chat(
                model_cfg,
                [
                    {"role": "system", "content": SYNTHESIZER_SYSTEM},
                    {
                        "role": "user",
                        "content": (
                            f"Question: {question}\n\n"
                            f"math_analysis (use for all math):\n{math_block}\n\n"
                            f"Tool results:\n{payload}"
                        ),
                    },
                ],
            )
        return raw.get("message", {}).get("content", "No answer generated.")

    def _maybe_narrate(self, question: str, answer: str, session: Session) -> str:
        session.add_trace("narrate", "stats_agent", "statistical narrative", self.settings.stats.model)
        context = {"draft_answer": answer, "tool_results": session.last_results(10)}
        with self.models.use(self.settings.stats):
            narrative = self.stats_agent.explain(question, context, session)
        return narrative

    def run(self, question: str, session: Session | None = None) -> str:
        session = session or Session()
        session.clear_trace()
        session.add_user(question)

        # Phase 1 — PLAN
        plan = self._plan(question, session)
        if plan.mode == "direct":
            answer = plan.direct_answer or "How can I help?"
            session.add_assistant(answer)
            return answer

        # Phase 2 — EXECUTE (sql_agent + code tools)
        self.executor.run(plan, session)

        # Phase 2b — MATH (deterministic)
        analysis = self.math_agent.analyze(question, session)
        session.scratch["math_analysis"] = analysis
        session.add_trace(
            "math",
            "math_agent",
            f"{analysis.get('status')} comparable={analysis.get('comparable', 'n/a')}",
        )

        # Phase 3 — SYNTHESIZE
        answer = self._synthesize(question, session, plan)

        if plan.needs_stats_narrative:
            answer = self._maybe_narrate(question, answer, session)

        session.add_assistant(answer)
        return answer
