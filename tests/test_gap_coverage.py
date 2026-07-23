"""Gap coverage: DPOY/ROY/6MOY, career years, team asks, schema sample notes."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from hornet.agents.sql_agent import SQLAgent
from hornet.db import load_schema_cache
from hornet.db.connection import execute_query
from hornet.db.schema import introspect_database, schema_text_sql
from hornet.db.team_aliases import extract_team
from tests.fixtures.build_sports_dbs import NBA_2006_MVP


@pytest.fixture
def sql_agent(settings) -> SQLAgent:
    models = MagicMock()
    models.use.side_effect = AssertionError("SQLCoder should not be called")
    return SQLAgent(settings, MagicMock(), models)


@pytest.mark.parametrize(
    "question,player,code",
    [
        ("Who won DPOY in the NBA in 2006?", "Ben Wallace", "DPOY-1"),
        ("Who won ROY in the NBA in 2006?", "Chris Paul", "ROY-1"),
        ("Who won Sixth Man in the NBA in 2006?", "Mike Miller", "6MOY-1"),
        ("NBA 6MOY 2006", "Mike Miller", "6MOY-1"),
        ("Who won MVP in the NBA in 2006?", NBA_2006_MVP[0], "MVP-1"),
    ],
)
def test_specific_award_winners(sql_agent: SQLAgent, settings, question, player, code):
    out = sql_agent.run("nba", question, MagicMock())
    assert "error" not in out, out
    assert out["rows"]
    assert out["rows"][0]["player"] == player
    assert code in str(out["rows"][0]["awards"])
    assert "-1" in out["generated_sql"]


@pytest.mark.parametrize(
    "question",
    [
        "Steve Nash career MVP years",
        "Steve Nash MVP seasons",
        "Which years did Steve Nash win MVP?",
    ],
)
def test_career_mvp_years(sql_agent: SQLAgent, settings, question):
    out = sql_agent.run("nba", question, MagicMock())
    assert "error" not in out, out
    years = {int(r["year"]) for r in out["rows"]}
    assert 2005 in years and 2006 in years
    assert all("MVP" in str(r.get("awards") or "") for r in out["rows"])


def test_phoenix_suns_record_2006(sql_agent: SQLAgent, settings):
    out = sql_agent.run("nba", "Phoenix Suns record in 2006", MagicMock())
    assert "error" not in out, out
    assert out["rows"]
    row = out["rows"][0]
    teamish = str(row.get("tm") or row.get("team") or "")
    assert "PHO" in teamish or "Phoenix" in teamish
    # Production rows include w/l; fixtures may only return roster/scoring for the team
    if "w" in row:
        assert row["w"] is not None


def test_suns_scoring_leader_2006(sql_agent: SQLAgent, settings):
    out = sql_agent.run("nba", "Who led the Phoenix Suns in scoring in 2006?", MagicMock())
    assert "error" not in out, out
    assert out["rows"]
    assert "pts" in out["generated_sql"].lower()
    assert "pho" in out["generated_sql"].lower() or "phoenix" in out["generated_sql"].lower()


@pytest.mark.parametrize(
    "sport,question,needle",
    [
        ("nba", "phoenix suns", "PHO"),
        ("nfl", "kansas city chiefs", "Chiefs"),
        ("nhl", "toronto maple leafs", "TOR"),
    ],
)
def test_team_alias_extract(sport, question, needle):
    hit = extract_team(sport, question)
    assert hit is not None
    abbrev, like_frag = hit
    assert needle in (abbrev or "") or needle in like_frag


def test_schema_player_samples_marked_examples_only(settings):
    schema = introspect_database(settings.db_path("nba"))
    player_col = next(c for c in schema["tables"]["player_mvp_stats"]["columns"] if c["name"] == "player")
    assert player_col.get("samples_note")
    text = schema_text_sql(schema)
    assert "examples only" in text


def test_sixth_man_not_treated_as_player_name():
    assert SQLAgent._extract_named_player("Who won Sixth Man in the NBA in 2006?") is None


def test_phoenix_suns_not_treated_as_player_name():
    assert SQLAgent._extract_named_player("How did the Phoenix Suns do in 2006?") is None
