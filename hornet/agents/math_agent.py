from __future__ import annotations

from typing import Any

from hornet.session import Session, ToolResult


def _first_sql_row(result: ToolResult) -> dict[str, Any] | None:
    out = result.output
    if not isinstance(out, dict):
        return None
    rows = out.get("rows", [])
    return rows[0] if rows else None


def _numeric_series(result: ToolResult, column: str) -> list[float]:
    out = result.output
    if not isinstance(out, dict):
        return []
    values: list[float] = []
    for row in out.get("rows", []):
        v = row.get(column)
        if v is not None:
            try:
                values.append(float(v))
            except (TypeError, ValueError):
                pass
    return values


def _is_compare_question(question: str) -> bool:
    q = question.lower()
    return any(w in q for w in ("compare", "versus", " vs ", "better", "difference", "how do"))


def _sports_from_results(results: list[ToolResult]) -> dict[str, ToolResult]:
    out: dict[str, ToolResult] = {}
    for r in results:
        if r.tool != "sql_query":
            continue
        sport = r.input.get("sport", "").lower()
        if sport:
            out[sport] = r
    return out


class MathAgent:
    """Deterministic math — no LLM. All numbers for synthesis come from here."""

    name = "math_agent"

    def analyze(self, question: str, session: Session) -> dict[str, Any]:
        sql_results = [r for r in session.tool_results if r.tool == "sql_query"]
        if not sql_results:
            return {"status": "no_data"}

        if _is_compare_question(question) and len(sql_results) >= 2:
            return self._cross_sport_or_multi(question, session, sql_results)

        if _is_compare_question(question) and len(sql_results) == 1:
            return self._intra_result_compare(sql_results[0])

        return self._summarize(sql_results)

    def _summarize(self, results: list[ToolResult]) -> dict[str, Any]:
        summaries = []
        for r in results:
            row = _first_sql_row(r)
            if row:
                summaries.append({"sport": r.input.get("sport"), "leader": row})
        return {"status": "summary", "leaders": summaries}

    def _intra_result_compare(self, result: ToolResult) -> dict[str, Any]:
        """Compare values within one SQL result (e.g. top 3 rushers)."""
        sport = result.input.get("sport", "")
        for col in ("rushing_yds", "yds", "pts", "player_pts", "receiving_yds"):
            series = _numeric_series(result, col)
            if len(series) >= 2:
                return {
                    "status": "intra_compare",
                    "sport": sport,
                    "metric": col,
                    "values": series,
                    "max": max(series),
                    "min": min(series),
                    "mean": round(sum(series) / len(series), 3),
                    "spread": round(max(series) - min(series), 3),
                    "leader_advantage": round(max(series) - series[1], 3) if len(series) > 1 else 0,
                }
        return {"status": "intra_compare", "sport": sport, "note": "no numeric series found"}

    def _cross_sport_or_multi(
        self, question: str, session: Session, results: list[ToolResult]
    ) -> dict[str, Any]:
        by_sport = _sports_from_results(results)
        profiles: list[dict[str, Any]] = []

        for sport, result in by_sport.items():
            row = _first_sql_row(result)
            if not row:
                continue
            profiles.append(self._profile_row(sport, row))

        if len(profiles) < 2:
            return {"status": "cross_compare", "profiles": profiles, "note": "insufficient data"}

        # Cross-sport scoring: present facts, flag non-comparability
        if len({p["sport"] for p in profiles}) >= 2 and self._is_scoring_question(question):
            return {
                "status": "cross_sport_scoring",
                "comparable": False,
                "reason": (
                    "NBA pts is points per game; NHL player_pts is season total (goals+assists). "
                    "Different scoring systems — do not declare a single winner."
                ),
                "profiles": profiles,
            }

        # Same metric across sports (rare) — could compare if units match
        metrics = {p.get("primary_metric") for p in profiles}
        if len(metrics) == 1 and None not in metrics:
            values = [p["primary_value"] for p in profiles]
            return {
                "status": "cross_compare",
                "comparable": True,
                "metric": profiles[0]["primary_metric"],
                "profiles": profiles,
                "max": max(values),
                "min": min(values),
                "spread": round(max(values) - min(values), 3),
            }

        return {
            "status": "cross_compare",
            "comparable": False,
            "reason": "Metrics differ across sports or rows.",
            "profiles": profiles,
        }

    @staticmethod
    def _is_scoring_question(question: str) -> bool:
        q = question.lower()
        return any(w in q for w in ("scor", "point", "ppg"))

    @staticmethod
    def _profile_row(sport: str, row: dict[str, Any]) -> dict[str, Any]:
        sport = sport.lower()
        if sport == "nba":
            ppg = float(row.get("pts", 0))
            games = float(row.get("g", 0))
            est_total = round(ppg * games, 1) if games else None
            return {
                "sport": "nba",
                "player": row.get("player"),
                "primary_metric": "pts (per game)",
                "primary_value": ppg,
                "games": int(games) if games else None,
                "estimated_season_points": est_total,
                "note": "pts is per-game scoring average",
            }
        if sport == "nhl":
            total = float(row.get("player_pts", 0))
            gp = float(row.get("player_gp", 0))
            goals = row.get("g")
            assists = row.get("a")
            per_game = round(total / gp, 3) if gp else None
            return {
                "sport": "nhl",
                "player": row.get("player"),
                "team": row.get("team_full"),
                "primary_metric": "player_pts (season total)",
                "primary_value": total,
                "games": int(gp) if gp else None,
                "goals": goals,
                "assists": assists,
                "points_per_game": per_game,
                "note": "player_pts = goals + assists for the season",
            }
        if sport == "nfl":
            for col, label in (
                ("yds", "passing yards (season)"),
                ("rushing_yds", "rushing yards (season)"),
                ("receiving_yds", "receiving yards (season)"),
            ):
                if col in row and row[col] is not None:
                    return {
                        "sport": "nfl",
                        "player": row.get("player"),
                        "team": row.get("team"),
                        "primary_metric": label,
                        "primary_value": float(row[col]),
                    }
        return {"sport": sport, "player": row.get("player"), "raw": row}
