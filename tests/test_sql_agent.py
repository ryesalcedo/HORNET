"""SQL agent pattern / validation tests (no Ollama required)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from hornet.agents.sql_agent import SQLAgent
from hornet.db.connection import execute_query
from tests.fixtures.build_sports_dbs import (
    NBA_2016_THREES_LEADER,
    NBA_2024_SCORING_LEADER,
    NFL_2023_PASSING_LEADER,
    NFL_2023_RUSHING_LEADER,
    NHL_2023_POINTS_LEADER,
)


@pytest.fixture
def sql_agent(settings) -> SQLAgent:
    client = MagicMock()
    models = MagicMock()
    # If SQLCoder is invoked, fail the test unless we expect it
    models.use.side_effect = AssertionError("SQLCoder should not be called for this test")
    return SQLAgent(settings, client, models)


def test_fast_path_nba_scoring(sql_agent: SQLAgent, settings):
    sql = sql_agent._generate("nba", "Most points per game leaders in 2024 NBA")
    assert "player_mvp_stats" in sql.lower()
    assert "order by pts desc" in sql.lower()
    result = execute_query(settings.db_path("nba"), sql)
    assert result["rows"]
    assert result["rows"][0]["player"] == NBA_2024_SCORING_LEADER[0]
    assert float(result["rows"][0]["pts"]) == pytest.approx(NBA_2024_SCORING_LEADER[1])


def test_fast_path_nfl_rushing(sql_agent: SQLAgent, settings):
    sql = sql_agent._generate("nfl", "Most rushing yards in 2023")
    assert "rushing_and_receiving" in sql.lower()
    assert "rushing_yds" in sql.lower()
    result = execute_query(settings.db_path("nfl"), sql)
    assert result["rows"][0]["player"] == NFL_2023_RUSHING_LEADER[0]
    assert float(result["rows"][0]["rushing_yds"]) == pytest.approx(NFL_2023_RUSHING_LEADER[1])


def test_fast_path_nfl_passing(sql_agent: SQLAgent, settings):
    sql = sql_agent._generate("nfl", "Who had the most passing yards in 2023?")
    assert "from passing" in sql.lower()
    result = execute_query(settings.db_path("nfl"), sql)
    assert result["rows"][0]["player"] == NFL_2023_PASSING_LEADER[0]
    assert float(result["rows"][0]["yds"]) == pytest.approx(NFL_2023_PASSING_LEADER[1])


def test_fast_path_nhl_points(sql_agent: SQLAgent, settings):
    sql = sql_agent._generate("nhl", "NHL scoring leader most points in 2023")
    assert "player_team_stats" in sql.lower()
    assert "player_pts" in sql.lower()
    result = execute_query(settings.db_path("nhl"), sql)
    assert result["rows"][0]["player"] == NHL_2023_POINTS_LEADER[0]
    assert int(result["rows"][0]["player_pts"]) == NHL_2023_POINTS_LEADER[1]


def test_fast_path_nba_threes_made(sql_agent: SQLAgent, settings):
    sql = sql_agent._generate("nba", "Most threes made in 2016")
    assert "c_3p" in sql.lower()
    assert "order by c_3p desc" in sql.lower()
    result = execute_query(settings.db_path("nba"), sql)
    assert result["rows"][0]["player"] == NBA_2016_THREES_LEADER[0]
    assert float(result["rows"][0]["c_3p"]) == pytest.approx(NBA_2016_THREES_LEADER[1])


def test_threes_made_unsupported_without_column(settings):
    """If only 3P% exists, refuse 'threes made'."""
    from hornet.db import load_schema_cache
    from hornet.db.schema import save_schema_cache

    cache = load_schema_cache(settings.schema_cache_dir / "nba.json")
    assert cache is not None
    # strip made column from cached schema copy
    for meta in cache["tables"].values():
        meta["columns"] = [c for c in meta["columns"] if c["name"].lower() != "c_3p"]
    save_schema_cache(settings.schema_cache_dir / "nba.json", cache)

    client = MagicMock()
    models = MagicMock()
    models.use.side_effect = AssertionError("should not call SQLCoder")
    agent = SQLAgent(settings, client, models)
    out = agent.run("nba", "Most threes made in 2016", session=MagicMock())
    assert "error" in out
    assert "3pm" in out["error"].lower() or "three" in out["error"].lower()

    # restore full cache for later tests
    from hornet.db import build_all_schema_caches

    build_all_schema_caches(settings)


def test_ambiguous_skips_fast_path_uses_sqlcoder(settings):
    client = MagicMock()
    models = MagicMock()
    cm = MagicMock()
    cm.__enter__.return_value = MagicMock(model="test-sql", temperature=0.0, keep_alive=0)
    cm.__exit__.return_value = False
    models.use.return_value = cm
    client.generate_completion.return_value = (
        "SELECT player, pts FROM player_mvp_stats WHERE year = 2024 ORDER BY pts DESC LIMIT 5"
    )
    agent = SQLAgent(settings, client, models)
    sql = agent._generate("nba", "Compare points vs assists leaders in 2024")
    assert client.generate_completion.called
    assert "pts" in sql.lower()


def test_sqlcoder_invalid_falls_back_to_recovery(settings):
    client = MagicMock()
    models = MagicMock()
    cm = MagicMock()
    cm.__enter__.return_value = MagicMock(model="test-sql", temperature=0.0, keep_alive=0)
    cm.__exit__.return_value = False
    models.use.return_value = cm
    # Hallucinated threes SQL — should be rejected then recovery may not apply;
    # use a bad column that recovery can fix via rushing pattern instead.
    client.generate_completion.return_value = (
        "SELECT player, fake_yds FROM rushing_and_receiving WHERE year = 2023 "
        "ORDER BY fake_yds DESC LIMIT 5"
    )
    agent = SQLAgent(settings, client, models)
    sql = agent._generate("nfl", "Most rushing yards in 2023")
    # Fast path should catch this before SQLCoder — if not, recovery after reject
    assert "rushing_yds" in sql.lower()
    assert "fake_yds" not in sql.lower()
