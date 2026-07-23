"""Human-readable schema hints injected into the SQL agent.

Hints below match the production HORNET DBs (player box + MVP fields on NBA,
Pro-Football-Reference style NFL splits, hockey-reference NHL).
"""

from __future__ import annotations

from typing import Any

SPORT_HINTS: dict[str, str] = {
    "nba": """\
NBA table player_mvp_stats (per-player season rows; includes MVP vote fields):
- Scoring: pts = points PER GAME (not season totals)
- Shooting makes/attempts: fg/fga, c_2p/c_2pa, c_3p/c_3pa, ft/fta
- THREE-POINTERS MADE = c_3p ; attempts = c_3pa ; pct = c_3p_pct
  For "most threes made" / 3PM leaders: ORDER BY c_3p DESC — never COUNT(*) or pts>=3
- Other box: trb, orb, drb, ast, stl, blk, tov, mp, g, gs, efg_pct
- awards = award abbreviations for that season (MVP, DPOY, ROY, AS, etc.)
  For award winners: WHERE awards IS NOT NULL AND awards != '' ; filter with LIKE '%MVP%'
- MVP voting: pts_won, pts_max, share (NOT scoring) — ORDER BY share DESC for MVP race
- Named player lookup: WHERE player LIKE '%Name%' AND year = …
- Team fields: tm and/or team; year = season end year (2024 = 2023-24)
- Use ONLY columns listed in the live schema""",
    "nfl": """\
NFL — use the table that matches the ask (regular season unless question says playoffs/*_post):
- passing: yds=passing yards, td=passing TDs, cmp, att, rate, int
- rushing_and_receiving: rushing_yds, rushing_td, rushing_att, receiving_yds, receiving_rec, receiving_td
- defense: sk=sacks, tackles_comb/tackles_solo/tackles_ast, def_interceptions_int (NOT a column named sacks/tackles/interceptions)
- kicking: scoring_fgm/scoring_fga, scoring_xpm/scoring_xpa
- scoring: pts, touchdowns_*; games / team_stats for team-level
- year, team, player on player tables
- awards column on many player tables when present
- Named player lookup: WHERE player LIKE '%Name%' AND year = …
- Use ONLY columns listed in the live schema""",
    "nhl": """\
NHL table player_team_stats:
- g = GOALS (not games); a = assists; player_pts = points; player_gp = games played
- awards = award abbreviations when present; Named player: WHERE player LIKE '%Name%'
- team = abbrev; team_full = full name; year = season end year
- Use ONLY columns listed in the live schema""",
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
        lines.append(f"THREE-POINT MAKES column: {made} — use for 'threes made' / 3PM leaders.")
    if "c_3pa" in all_cols:
        lines.append("THREE-POINT ATTEMPTS column: c_3pa")
    if pct:
        lines.append(f"THREE-POINT PCT column: {pct} — percentage only, not makes.")
    if sport == "nba" and pct and not made:
        lines.append("WARNING: 3P% exists but no threes-made column was detected.")
    if sport == "nfl":
        if "sk" in all_cols:
            lines.append("NFL sacks column: sk (not 'sacks').")
        if "tackles_comb" in all_cols:
            lines.append("NFL tackles: tackles_comb / tackles_solo / tackles_ast.")
        if "def_interceptions_int" in all_cols:
            lines.append("NFL interceptions: def_interceptions_int.")

    lines.append("If the question needs a column not listed above, output UNSUPPORTED.")
    return "\n".join(lines)
