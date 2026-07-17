"""Human-readable schema hints injected into the SQL agent."""

SPORT_HINTS: dict[str, str] = {
    "nba": """\
NBA database (table: player_mvp_stats) — MVP voting + per-game box stats for nominees:
- pts = points PER GAME — use this for scoring leaders
- pts_max / pts_won = MVP VOTING points (NOT player scoring)
- trb, ast, stl, blk, mp, g = per-game / season counting stats when present
- fg_pct, c_3p_pct / x3p_pct, ft_pct = SHOOTING PERCENTAGES only (0–1 or 0–100)
- There is NO season-total "threes made" / 3PM column. Do NOT invent one.
- Do NOT use COUNT(*), pts >= 3, or any pts filter as a stand-in for threes made.
- If asked for most threes MADE / 3PM / three-pointers made, you cannot answer from this DB.
- year = season end year (2024 = 2023-24 season)
- One row per player per season (MVP ballot rows — not the full league)

Example scoring query:
SELECT player, pts FROM player_mvp_stats WHERE year = 2024 ORDER BY pts DESC LIMIT 3;""",
    "nfl": """\
NFL database — use the correct table for the stat type:
- passing: QB stats — yds = passing yards, td = passing TDs, cmp, att, rate
- rushing_and_receiving: rushing_yds, receiving_yds, rushing_td, receiving_rec
- defense: tackles, sacks, interceptions
- year = season year, player, team on all tables

Example passing yards leaders:
SELECT player, team, yds FROM passing WHERE year = 2024 ORDER BY yds DESC LIMIT 5;""",
    "nhl": """\
NHL database (table: player_team_stats):
- g = GOALS (not games)
- a = assists
- player_gp = games PLAYED by the player
- player_pts = season TOTAL points (goals + assists)
- Never use g as games played — use player_gp
- year = season end year
- team = abbreviation, team_full = full name

Example points leaders:
SELECT player, player_pts, g, a FROM player_team_stats WHERE year = 2023 ORDER BY player_pts DESC LIMIT 5;""",
}
