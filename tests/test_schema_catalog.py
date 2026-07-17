"""Schema catalog tests against synthetic 1977–2026 DBs."""

from __future__ import annotations

import sqlite3

from hornet.db.schema import (
    all_columns,
    introspect_database,
    load_schema_cache,
    schema_text_sql,
    validate_sql_against_schema,
)


REQUIRED = {
    "nba": {
        "player_mvp_stats": {
            "player",
            "year",
            "pts",
            "pts_won",
            "pts_max",
            "g",
            "c_3p_pct",
        }
    },
    "nfl": {
        "passing": {"player", "team", "year", "yds", "td", "cmp", "att", "rate"},
        "rushing_and_receiving": {
            "player",
            "team",
            "year",
            "rushing_yds",
            "receiving_yds",
            "rushing_td",
            "receiving_rec",
        },
        "defense": {"player", "team", "year", "tackles", "sacks", "interceptions"},
        "kicking": {"player", "year", "fgm", "fga"},
        "games": {"year", "week", "team"},
        "team_stats": {"year", "team", "wins", "losses"},
    },
    "nhl": {
        "player_team_stats": {
            "player",
            "year",
            "team",
            "team_full",
            "g",
            "a",
            "player_gp",
            "player_pts",
        }
    },
}


def test_fixture_year_span(settings, year_span):
    lo, hi = year_span
    for sport in settings.sports:
        conn = sqlite3.connect(sport.database)
        tables = [
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        ]
        assert tables, f"{sport.id} has no tables"
        for table in tables:
            cols = {c[1] for c in conn.execute(f"PRAGMA table_info({table})")}
            if "year" not in cols:
                continue
            # skip empty postseason stub tables
            n = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            if n == 0:
                continue
            ymin, ymax = conn.execute(f"SELECT MIN(year), MAX(year) FROM {table}").fetchone()
            assert ymin == lo, f"{sport.id}.{table} min year {ymin} != {lo}"
            assert ymax == hi, f"{sport.id}.{table} max year {ymax} != {hi}"
        conn.close()


def test_required_tables_and_columns(settings):
    for sport in settings.sports:
        schema = introspect_database(sport.database)
        assert schema["exists"]
        for table, needed in REQUIRED[sport.id].items():
            assert table in schema["tables"], f"{sport.id} missing table {table}"
            have = {c["name"] for c in schema["tables"][table]["columns"]}
            missing = needed - have
            assert not missing, f"{sport.id}.{table} missing columns {missing}"


def test_schema_cache_written(settings):
    for sport in settings.sports:
        cache = load_schema_cache(settings.schema_cache_dir / f"{sport.id}.json")
        assert cache is not None
        assert cache["exists"]
        assert cache.get("column_index")
        text = schema_text_sql(cache)
        assert "ALL TABLES:" in text
        assert "TABLE " in text


def test_validate_rejects_unknown_metric(settings):
    cache = load_schema_cache(settings.schema_cache_dir / "nba.json")
    err = validate_sql_against_schema(
        "SELECT player, three_count FROM player_mvp_stats WHERE year = 2016",
        cache,
    )
    assert err is not None
    assert "three" in err.lower() or "unknown" in err.lower()


def test_validate_accepts_real_scoring_sql(settings):
    cache = load_schema_cache(settings.schema_cache_dir / "nba.json")
    err = validate_sql_against_schema(
        "SELECT player, pts FROM player_mvp_stats WHERE year = 2024 ORDER BY pts DESC LIMIT 5",
        cache,
    )
    assert err is None


def test_nba_has_pct_not_threes_made(settings):
    cols = all_columns(load_schema_cache(settings.schema_cache_dir / "nba.json"))
    assert "c_3p_pct" in cols
    assert "fg3" not in cols
    assert "threes_made" not in cols
