from __future__ import annotations

import re
from typing import Any

import numpy as np

from hornet.session import Session, ToolResult

# Shared helpers — imported by planner and sql_agent
PREDICTION_WORDS = (
    "predict",
    "forecast",
    "project",
    "projection",
    "next season",
    "will score",
    "will average",
    "likely to",
    "expect to",
    "trend",
    "projected",
)


def is_prediction_question(question: str) -> bool:
    q = question.lower()
    return any(w in q for w in PREDICTION_WORDS)


def extract_player_name(question: str) -> str | None:
    if m := re.search(r"['\"]([^'\"]+)['\"]", question):
        return m.group(1).strip()

    if m := re.search(
        r"(?:predict|forecast|project)\s+(.+?)'s\s+",
        question,
        re.IGNORECASE,
    ):
        return m.group(1).strip()

    if m := re.search(
        r"\b([A-Z][\w\.\-']*(?:\s+[A-Z][\w\.\-']*){0,2})'s\s+",
        question,
    ):
        return m.group(1).strip()

    if m := re.search(
        r"\b(?:predict|forecast|project)\s+(.+?)"
        r"(?:\s+(?:points?|scoring|passing|rushing|receiving|ppg|yards?|in\s+20\d{2}|for\s+20\d{2}))\b",
        question,
        re.IGNORECASE,
    ):
        name = m.group(1).strip()
        name = re.sub(r"\b(nba|nfl|nhl|basketball|football|hockey)\b", "", name, flags=re.I).strip()
        return name if name else None

    if m := re.search(r"\bfor\s+(.+?)\s+in\s+20\d{2}\b", question, re.IGNORECASE):
        name = re.sub(r"\b(nba|nfl|nhl)\b", "", m.group(1), flags=re.I).strip()
        return name if name else None

    return None


def extract_target_year(question: str, history_years: list[int] | None = None) -> int:
    if m := re.search(r"\b(?:in|for)\s+(20\d{2})\b", question, re.IGNORECASE):
        return int(m.group(1))
    if m := re.search(r"\b(20\d{2})\b", question):
        year = int(m.group(1))
        if is_prediction_question(question):
            return year
    if history_years:
        return max(history_years) + 1
    return 2025


def sanitize_sql_like(value: str) -> str:
    return value.replace("'", "''")


def prediction_history_question(sport: str, question: str) -> str:
    """Build a sub-question that fetches multi-season history for projection."""
    player = extract_player_name(question)
    q = question.lower()

    if sport == "nba":
        if player:
            return f"All seasons for {player}: year, pts, g — order by year"
        return "Top 10 scorers by year for recent seasons with year and pts"

    if sport == "nhl":
        if player:
            return f"All seasons for {player}: year, player_pts, player_gp, g, a — order by year"
        return "Top 10 point scorers by year with year and player_pts"

    if sport == "nfl":
        if re.search(r"rush", q):
            stat = "rushing yards"
            if player:
                return f"All seasons rushing yards for {player}: year, rushing_yds — order by year"
        elif re.search(r"receiv", q):
            stat = "receiving yards"
            if player:
                return f"All seasons receiving yards for {player}: year, receiving_yds — order by year"
        else:
            stat = "passing yards"
            if player:
                return f"All seasons passing yards for {player}: year, yds — order by year"
        return f"Top 10 players by {stat} per year with year and yards"

    return question


METRIC_CANDIDATES: dict[str, list[tuple[str, str]]] = {
    "nba": [("pts", "points per game")],
    "nhl": [("player_pts", "season points (goals + assists)")],
    "nfl": [
        ("yds", "passing yards"),
        ("rushing_yds", "rushing yards"),
        ("receiving_yds", "receiving yards"),
    ],
}


class PredictionAgent:
    """Deterministic trend projection from historical SQL rows — no LLM."""

    name = "prediction_agent"

    def predict(self, question: str, session: Session) -> dict[str, Any]:
        sql_result = self._latest_sql(session)
        if sql_result is None:
            return {"status": "no_data", "reason": "No SQL results to project from"}

        rows = self._rows(sql_result)
        if not rows:
            return {"status": "no_data", "reason": "SQL returned no rows"}

        sport = str(sql_result.input.get("sport", "")).lower()
        metric_col, metric_label = self._pick_metric(sport, rows, question)
        if not metric_col:
            return {"status": "no_metric", "reason": "Could not identify a numeric stat column"}

        series = self._time_series(rows, metric_col)
        if len(series) < 2:
            return {
                "status": "insufficient_data",
                "reason": f"Need at least 2 seasons; found {len(series)}",
                "metric": metric_label,
                "historical": series,
            }

        years = [p["year"] for p in series]
        values = [p["value"] for p in series]
        target = extract_target_year(question, years)
        linear = self._linear_project(years, values, target)
        ewma = self._ewma_project(values, alpha=0.6)

        player = rows[0].get("player") or extract_player_name(question)
        return {
            "status": "projected",
            "sport": sport,
            "player": player,
            "metric": metric_col,
            "metric_label": metric_label,
            "target_year": target,
            "method": "linear_regression",
            "historical": series,
            "projected_value": linear["value"],
            "ewma_baseline": round(ewma, 3),
            "slope_per_year": linear["slope"],
            "r_squared": linear["r_squared"],
            "confidence_note": (
                f"Linear fit on {len(series)} seasons (R²={linear['r_squared']:.2f}). "
                "Projections assume recent trend continues — not a guarantee."
            ),
        }

    @staticmethod
    def _latest_sql(session: Session) -> ToolResult | None:
        for result in reversed(session.tool_results):
            if result.tool == "sql_query" and not result.error:
                return result
        return None

    @staticmethod
    def _rows(result: ToolResult) -> list[dict[str, Any]]:
        out = result.output
        if isinstance(out, dict):
            return list(out.get("rows", []))
        return []

    @staticmethod
    def _pick_metric(
        sport: str, rows: list[dict[str, Any]], question: str
    ) -> tuple[str | None, str | None]:
        q = question.lower()
        candidates = METRIC_CANDIDATES.get(sport, [])
        if sport == "nfl":
            if "rush" in q:
                candidates = [("rushing_yds", "rushing yards")]
            elif "receiv" in q:
                candidates = [("receiving_yds", "receiving yards")]
            else:
                candidates = [("yds", "passing yards")]

        for col, label in candidates:
            if col in rows[0] and rows[0][col] is not None:
                return col, label
        return None, None

    @staticmethod
    def _time_series(rows: list[dict[str, Any]], metric_col: str) -> list[dict[str, Any]]:
        series: list[dict[str, Any]] = []
        for row in rows:
            year = row.get("year")
            val = row.get(metric_col)
            if year is None or val is None:
                continue
            try:
                series.append({"year": int(year), "value": round(float(val), 3)})
            except (TypeError, ValueError):
                continue
        series.sort(key=lambda p: p["year"])
        return series

    @staticmethod
    def _linear_project(
        years: list[int], values: list[float], target_year: int
    ) -> dict[str, float]:
        x = np.array(years, dtype=float)
        y = np.array(values, dtype=float)
        slope, intercept = np.polyfit(x, y, 1)
        predicted = float(slope * target_year + intercept)

        if len(y) > 1:
            corr = np.corrcoef(x, y)[0, 1]
            r_sq = float(corr ** 2) if not np.isnan(corr) else 0.0
        else:
            r_sq = 0.0

        return {
            "value": round(predicted, 3),
            "slope": round(float(slope), 4),
            "r_squared": round(r_sq, 3),
        }

    @staticmethod
    def _ewma_project(values: list[float], alpha: float = 0.6) -> float:
        ewma = values[0]
        for v in values[1:]:
            ewma = alpha * v + (1 - alpha) * ewma
        return float(ewma)
