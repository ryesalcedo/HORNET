"""Extra correctness checks on committed fixture DBs (1977–2026)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from hornet.db.connection import execute_query
from hornet.db.schema import explain_select, introspect_database
from tests.fixtures.build_sports_dbs import (
    NBA_2024_SCORING_LEADER,
    NFL_2023_RUSHING_LEADER,
    NHL_2023_POINTS_LEADER,
    YEAR_END,
    YEAR_START,
)

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "databases"


@pytest.fixture(scope="module")
def committed_dbs() -> dict[str, Path]:
    paths = {s: FIXTURE_DIR / f"{s}.db" for s in ("nba", "nfl", "nhl")}
    missing = [s for s, p in paths.items() if not p.exists()]
    if missing:
        pytest.skip(f"fixture DBs missing ({missing}); run: python tests/fixtures/build_sports_dbs.py")
    return paths


def test_committed_dbs_year_bounds(committed_dbs):
    for sport, path in committed_dbs.items():
        schema = introspect_database(path)
        assert schema["exists"]
        for table, meta in schema["tables"].items():
            if meta["row_count"] == 0:
                continue
            colnames = {c["name"] for c in meta["columns"]}
            if "year" not in colnames:
                continue
            conn = sqlite3.connect(path)
            lo, hi = conn.execute(f"SELECT MIN(year), MAX(year) FROM {table}").fetchone()
            conn.close()
            assert lo == YEAR_START, f"{sport}.{table}"
            assert hi == YEAR_END, f"{sport}.{table}"


def test_committed_edge_years_have_rows(committed_dbs):
    checks = [
        ("nba", "player_mvp_stats"),
        ("nfl", "passing"),
        ("nfl", "rushing_and_receiving"),
        ("nhl", "player_team_stats"),
    ]
    for sport, table in checks:
        path = committed_dbs[sport]
        conn = sqlite3.connect(path)
        for year in (YEAR_START, YEAR_END):
            n = conn.execute(f"SELECT COUNT(*) FROM {table} WHERE year = ?", (year,)).fetchone()[0]
            assert n > 0, f"{sport}.{table} empty for {year}"
        conn.close()


def test_committed_known_leaders(committed_dbs):
    nba = execute_query(
        committed_dbs["nba"],
        "SELECT player, pts FROM player_mvp_stats WHERE year = 2024 ORDER BY pts DESC LIMIT 1",
    )
    assert nba["rows"][0]["player"] == NBA_2024_SCORING_LEADER[0]

    nfl = execute_query(
        committed_dbs["nfl"],
        "SELECT player, rushing_yds FROM rushing_and_receiving "
        "WHERE year = 2023 ORDER BY rushing_yds DESC LIMIT 1",
    )
    assert nfl["rows"][0]["player"] == NFL_2023_RUSHING_LEADER[0]

    nhl = execute_query(
        committed_dbs["nhl"],
        "SELECT player, player_pts FROM player_team_stats "
        "WHERE year = 2023 ORDER BY player_pts DESC LIMIT 1",
    )
    assert nhl["rows"][0]["player"] == NHL_2023_POINTS_LEADER[0]


def test_explain_rejects_bad_column(committed_dbs):
    err = explain_select(
        committed_dbs["nba"],
        "SELECT player, threes_made FROM player_mvp_stats WHERE year = 2016",
    )
    assert err is not None


def test_only_select_allowed(committed_dbs):
    with pytest.raises(ValueError, match="SELECT"):
        execute_query(committed_dbs["nba"], "DELETE FROM player_mvp_stats")
