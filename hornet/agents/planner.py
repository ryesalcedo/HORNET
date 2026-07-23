from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

PLANNER_SYSTEM = """You are the HORNET planner. Output JSON only.

Decide how to answer the user's sports analytics question about NBA, NFL, or NHL data.

Modes:
- "direct": greetings, help, capability questions — no database needed
- "data": needs database facts — provide a steps list

For "data" mode, build steps using ONLY these tools:
- sql_query: {"sport":"nba"|"nfl"|"nhl", "question":"plain English data request"}
  NEVER write SQL. SQLCoder handles SQL generation.
- schema_lookup: {"sport":"nba"|"nfl"|"nhl"} — only if table layout is unclear
- search: {"query":"text", "sport":"nba"|"nfl"|"nhl" (optional)} — raw CSV search only
- compute_stats: {"operation":"describe"|"compare_means"|"per_game"|"correlation", ...}

Rules:
- Most stat questions need only ONE sql_query step
- Use schema_lookup only when the question is ambiguous about tables
- Cross-sport comparisons: one sql_query per sport, then compute_stats if comparing numbers
- Set needs_stats_narrative true only for deep statistical interpretation

Output schema:
{
  "mode": "direct" | "data",
  "direct_answer": "string if mode=direct else omit",
  "steps": [{"tool": "...", "arguments": {...}}],
  "needs_stats_narrative": false
}
"""


@dataclass
class PlanStep:
    tool: str
    arguments: dict[str, Any]


@dataclass
class Plan:
    mode: str = "data"
    direct_answer: str | None = None
    steps: list[PlanStep] = field(default_factory=list)
    needs_stats_narrative: bool = False


def infer_sports(text: str) -> list[str]:
    lower = text.lower()
    found: list[str] = []
    if any(k in lower for k in ("nba", "basketball")):
        found.append("nba")
    if any(k in lower for k in ("nfl", "football")):
        found.append("nfl")
    if any(k in lower for k in ("nhl", "hockey")):
        found.append("nhl")
    return found


def infer_sport(text: str) -> str | None:
    sports = infer_sports(text)
    return sports[0] if len(sports) == 1 else None


def _is_meta_question(text: str) -> bool:
    lower = text.strip().lower()
    if lower in {"hi", "hello", "help", "/help", "?"}:
        return True
    return bool(
        re.search(r"\b(what can you do|how do you work|who are you|help me)\b", lower)
    )


def _extract_year(question: str, default: str = "2024") -> str:
    if m := re.search(r"\b((?:19|20)\d{2})\b", question):
        return m.group(1)
    return default


def _extract_limit(question: str, default: int = 5) -> int:
    if m := re.search(r"top\s+(\d+)", question.lower()):
        return int(m.group(1))
    if re.search(r"\bleader\b", question.lower()) and "top" not in question.lower():
        return 1
    return default


def sport_sub_question(sport: str, question: str) -> str:
    """Focused leaderboard sub-question for cross-sport compare plans only.

    Do not use this for single-sport asks — it would discard player names,
    awards, and other non-scoring intent.
    """
    q = question.lower()
    year = _extract_year(question)
    n = _extract_limit(question)

    if sport == "nba":
        if n == 1:
            return f"Top player by points per game in {year} with games played (columns: player, pts, g)"
        return f"Top {n} players by points per game in {year}"
    if sport == "nhl":
        if n == 1:
            return f"Top player by total points in {year} — include player_pts, player_gp, goals (g), assists (a)"
        return f"Top {n} players by total points in {year}"
    if sport == "nfl":
        if re.search(r"rush", q):
            return f"Top {n} players by rushing yards in {year}"
        if re.search(r"receiv", q):
            return f"Top {n} players by receiving yards in {year}"
        return f"Top {n} players by passing yards in {year}"
    return question


def build_data_plan(question: str) -> Plan | None:
    """Deterministic plan for single- and multi-sport data questions."""
    if _is_meta_question(question):
        return fallback_plan(question)

    sports = infer_sports(question)
    if not sports:
        return None

    q = question.lower()
    deep_stats = any(w in q for w in ("correlation", "regression", "statistical analysis", "explain why"))

    # Cross-sport: rewrite each leg to a comparable leaderboard metric.
    # Single-sport: keep the user's question intact (player/awards/etc.).
    if len(sports) >= 2:
        steps = [
            PlanStep("sql_query", {"sport": sport, "question": sport_sub_question(sport, question)})
            for sport in sports
        ]
        return Plan(mode="data", steps=steps, needs_stats_narrative=deep_stats)

    sport = sports[0]
    steps = [PlanStep("sql_query", {"sport": sport, "question": question})]
    return Plan(mode="data", steps=steps, needs_stats_narrative=deep_stats)


def needs_llm_planner(question: str) -> bool:
    """Only use LLM planner when deterministic routing can't handle it."""
    if build_data_plan(question) is not None:
        return False
    lower = question.lower()
    return any(w in lower for w in ("search csv", "raw file", "grep", "correlation", "schema"))


def fallback_plan(question: str) -> Plan:
    """Fast deterministic plan when LLM planner is unnecessary."""
    if _is_meta_question(question):
        return Plan(
            mode="direct",
            direct_answer=(
                "I'm HORNET — local NBA/NFL/NHL analytics. "
                "Ask me questions about players, teams, and stats from your databases. "
                "Example: *Who led the NBA in scoring in 2024?*"
            ),
        )

    sports = infer_sports(question)
    if not sports:
        return Plan(
            mode="direct",
            direct_answer="Which sport — NBA, NFL, or NHL? I need that to query the right database.",
        )

    steps = [
        PlanStep("sql_query", {"sport": sport, "question": question})
        for sport in sports
    ]
    return Plan(mode="data", steps=steps)


def parse_plan(raw: dict[str, Any], question: str) -> Plan:
    mode = raw.get("mode", "data")
    if mode == "direct":
        return Plan(
            mode="direct",
            direct_answer=raw.get("direct_answer", "How can I help?"),
        )

    steps: list[PlanStep] = []
    for item in raw.get("steps", []):
        if not isinstance(item, dict):
            continue
        tool = item.get("tool")
        args = item.get("arguments", {})
        if tool and isinstance(args, dict):
            steps.append(PlanStep(tool=str(tool), arguments=args))

    if not steps:
        return fallback_plan(question)

    sport = infer_sport(question)
    normalized: list[PlanStep] = []
    for step in steps:
        args = dict(step.arguments)
        if step.tool in {"sql_query", "schema_lookup"} and sport and not args.get("sport"):
            args["sport"] = sport
        if step.tool == "sql_query":
            if not args.get("question"):
                for key in ("query", "sql", "request"):
                    if args.get(key):
                        args["question"] = args[key]
            args.pop("sql", None)
            args.pop("query", None)
            if not args.get("question"):
                args["question"] = question
        normalized.append(PlanStep(step.tool, args))

    return Plan(
        mode="data",
        steps=normalized,
        needs_stats_narrative=bool(raw.get("needs_stats_narrative")),
    )
