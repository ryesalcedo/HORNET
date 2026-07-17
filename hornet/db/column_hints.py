"""Human-readable schema hints injected into the SQL agent."""

from __future__ import annotations

from typing import Any

SPORT_HINTS: dict[str, str] = {
    "nba": """\
NBA (player_mvp_stats) — MVP ballot + per-game box stats for nominees, NOT the full league:
- pts = points PER GAME (scoring leaders)
- pts_max / pts_won = MVP VOTING points (NOT scoring)
- Percent columns (*_pct) are percentages — NOT makes
- For threes MADE / 3PM: use the live threes-made column from the schema below if present
  (often c_3p, fg3, x3p, etc.). Never invent COUNT(*) or pts>=3 as a substitute.
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

    from hornet.db.shooting_cols import threes_made_column, threes_pct_column

    all_cols = {c["name"].lower() for meta in tables.values() for c in meta["columns"]}
    if "pts" in all_cols and ("pts_won" in all_cols or "pts_max" in all_cols):
        lines.append("WARNING: pts = player scoring; pts_won/pts_max = MVP votes — do not confuse.")
    made = threes_made_column(all_cols)
    pct = threes_pct_column(all_cols)
    if made:
        lines.append(f"THREE-POINT MAKES column: {made} — use this for 'threes made' / 3PM leaders.")
    if pct:
        lines.append(f"THREE-POINT PCT column: {pct} — percentage only, not makes.")
    if sport == "nba" and pct and not made:
        lines.append("WARNING: 3P% exists but no threes-made column was detected.")

    lines.append("If the question needs a column not listed above, output UNSUPPORTED.")
    return "\n".join(lines)
