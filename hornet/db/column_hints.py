"""Human-readable schema hints injected into the SQL agent."""

from __future__ import annotations

from typing import Any

SPORT_HINTS: dict[str, str] = {
    "nba": """\
NBA (player_mvp_stats) — MVP ballot + per-game box stats for nominees, NOT the full league:
- pts = points PER GAME (scoring leaders)
- pts_max / pts_won = MVP VOTING points (NOT scoring)
- Percent columns (*_pct, c_3p_pct, etc.) are percentages — NOT makes/attempts totals
- No season-total 3PM/"threes made" unless such a column appears in the schema below
- Never invent columns or substitute COUNT(*) / pts>=3 for missing stats
- year = season end year (2024 = 2023-24)""",
    "nfl": """\
NFL — pick the table that matches the stat:
- passing: yds=passing yards, td=passing TDs, cmp, att, rate
- rushing_and_receiving: rushing_yds, receiving_yds, rushing_td, receiving_rec
- defense: tackles/sacks/interceptions columns as listed in schema
- Use ONLY column names from the schema block
- year = season year""",
    "nhl": """\
NHL (player_team_stats):
- g = GOALS (not games); player_gp = games played; player_pts = points
- a = assists; team / team_full as listed
- year = season end year
- Use ONLY column names from the schema block""",
}


def dynamic_hints(sport: str, schema: dict[str, Any]) -> str:
    """Append facts derived from the live schema cache so the model sees real columns."""
    if not schema.get("exists"):
        return f"{sport}: DATABASE MISSING — cannot query."

    lines = [SPORT_HINTS.get(sport, ""), "", "LIVE SCHEMA FACTS (authoritative — override guesses):"]
    tables = schema.get("tables", {})
    lines.append(f"Tables ({len(tables)}): {', '.join(tables.keys())}")

    for table, meta in tables.items():
        colnames = [c["name"] for c in meta["columns"]]
        lines.append(f"- {table} ({meta['row_count']} rows): {', '.join(colnames)}")
        for c in meta["columns"]:
            if c["name"].lower() == "year" and "min" in c and "max" in c:
                lines.append(f"  year range on {table}: {c['min']} .. {c['max']}")

    # Ambiguity warnings from actual names
    all_cols = {c["name"].lower() for meta in tables.values() for c in meta["columns"]}
    if "pts" in all_cols and ("pts_won" in all_cols or "pts_max" in all_cols):
        lines.append("WARNING: pts = player scoring; pts_won/pts_max = MVP votes — do not confuse.")
    if any("pct" in c for c in all_cols) and not any(
        re_name for re_name in all_cols if re_name in {"fg3", "c_3p", "x3p", "threes", "tpm"}
    ):
        if sport == "nba":
            lines.append(
                "WARNING: shooting % columns exist but no threes-made total column was found."
            )

    lines.append("If the question needs a column not listed above, output UNSUPPORTED.")
    return "\n".join(lines)
