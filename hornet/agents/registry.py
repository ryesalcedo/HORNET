"""Agent registry — plug in new agents here."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hornet.agents.math_agent import MathAgent
    from hornet.agents.sql_agent import SQLAgent
    from hornet.agents.stats_agent import StatsAgent

# Agent roles in the HORNET pipeline:
#   router           — code, no LLM (planner.build_data_plan)
#   sql_agent        — SQLCoder + SQLite
#   math_agent       — deterministic Python math
#   prediction_agent — trend projection from history (no LLM)
#   orchestrator     — plan (complex) + synthesize
#   stats_agent      — Mathstral narrative (optional, on demand)

AGENT_ROLES = (
    "router",
    "sql_agent",
    "math_agent",
    "prediction_agent",
    "orchestrator",
    "stats_agent",
    "tool",
)
