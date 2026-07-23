"""Broad regression suite (~100 cases) for planner + SQL routing fixes."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from hornet.agents.planner import build_data_plan, infer_sport, infer_sports, sport_sub_question
from hornet.agents.sql_agent import SQLAgent
from hornet.db.column_hints import dynamic_hints
from hornet.db.connection import execute_query
from hornet.db import load_schema_cache
from tests.fixtures.build_sports_dbs import NBA_2006_MVP, NBA_2024_SCORING_LEADER


@pytest.fixture
def sql_agent(settings) -> SQLAgent:
    models = MagicMock()
    models.use.side_effect = AssertionError("SQLCoder should not be called for this test")
    return SQLAgent(settings, MagicMock(), models)


# ---------------------------------------------------------------------------
# Planner — preserve single-sport intent
# ---------------------------------------------------------------------------

PLAYER_QUESTIONS = [
    "How did Steve Nash do in the NBA in 2006?",
    "Steve Nash NBA stats 2006",
    "Tell me about Steve Nash in the NBA in 2006",
    "NBA info on Steve Nash 2006",
    "What were Steve Nash's numbers in the NBA in 2006?",
    "Show Steve Nash basketball stats for 2006",
    "Nikola Jokic NBA 2024",
    "Stephen Curry NBA threes 2016",
    "LeBron James NBA 2012",
    "Christian McCaffrey NFL rushing 2023",
    "Connor McDavid NHL 2023",
    "Tua Tagovailoa NFL passing yards 2023",
]

AWARD_QUESTIONS = [
    "Who won MVP in the NBA in 2006?",
    "NBA MVP 2006",
    "NBA award winners 2006",
    "Who won the NBA MVP in 2024?",
    "NBA awards 2016",
    "MVP winners NBA 2005",
    "NBA DPOY 2006",
    "NBA ROY 2006",
]

LEADER_QUESTIONS = [
    ("nba", "Most points per game in the NBA in 2024"),
    ("nba", "NBA scoring leaders 2024"),
    ("nba", "Top 10 NBA scorers 2024"),
    ("nba", "Who led the NBA in scoring in 2024?"),
    ("nba", "Most threes made in the NBA in 2016"),
    ("nfl", "Most rushing yards in the NFL in 2023"),
    ("nfl", "NFL passing yards leaders 2023"),
    ("nfl", "Most receiving yards NFL 2023"),
    ("nfl", "Most sacks in the NFL in 2023"),
    ("nhl", "NHL scoring leader most points in 2023"),
    ("nhl", "Top NHL points 2024"),
]


@pytest.mark.parametrize("question", PLAYER_QUESTIONS)
def test_planner_preserves_player_questions(question: str):
    plan = build_data_plan(question)
    assert plan is not None
    assert plan.mode == "data"
    assert len(plan.steps) == 1
    assert plan.steps[0].arguments["question"] == question
    assert "Top 5 players by points" not in plan.steps[0].arguments["question"]


@pytest.mark.parametrize("question", AWARD_QUESTIONS)
def test_planner_preserves_award_questions(question: str):
    plan = build_data_plan(question)
    assert plan is not None
    assert plan.steps[0].arguments["question"] == question
    assert not plan.steps[0].arguments["question"].startswith("Top ")


@pytest.mark.parametrize("sport,question", LEADER_QUESTIONS)
def test_planner_preserves_leader_questions(sport: str, question: str):
    plan = build_data_plan(question)
    assert plan is not None
    assert plan.steps[0].arguments["sport"] == sport
    assert plan.steps[0].arguments["question"] == question


def test_planner_cross_sport_rewrites():
    plan = build_data_plan("Compare NBA and NHL scoring in 2024")
    assert plan is not None
    assert len(plan.steps) == 2
    for step in plan.steps:
        assert step.arguments["question"].startswith("Top")


@pytest.mark.parametrize(
    "text,expected",
    [
        ("nba scoring", ["nba"]),
        ("NFL rushing", ["nfl"]),
        ("nhl points", ["nhl"]),
        ("basketball and hockey", ["nba", "nhl"]),
        ("football vs basketball", ["nba", "nfl"]),
        ("hello", []),
    ],
)
def test_infer_sports(text: str, expected: list[str]):
    assert infer_sports(text) == expected


@pytest.mark.parametrize(
    "text,expected",
    [
        ("nba only", "nba"),
        ("nfl only", "nfl"),
        ("nhl only", "nhl"),
        ("nba and nhl", None),
    ],
)
def test_infer_sport(text: str, expected: str | None):
    assert infer_sport(text) == expected


@pytest.mark.parametrize(
    "sport,question,needle",
    [
        ("nba", "x 2024", "points per game"),
        ("nhl", "x 2024", "total points"),
        ("nfl", "rushing 2024", "rushing yards"),
        ("nfl", "receiving 2024", "receiving yards"),
        ("nfl", "passing 2024", "passing yards"),
    ],
)
def test_sport_sub_question_metrics(sport: str, question: str, needle: str):
    out = sport_sub_question(sport, question)
    assert needle in out.lower()
    assert "2024" in out


# ---------------------------------------------------------------------------
# SQL agent — named players, awards, leaders
# ---------------------------------------------------------------------------

NAME_CASES = [
    ("Steve Nash 2006", "Steve Nash"),
    ("How did Steve Nash do in 2006?", "Steve Nash"),
    ("Nikola Jokic stats 2024", "Nikola Jokic"),
    ("Stephen Curry in 2016", "Stephen Curry"),
    ("Christian McCaffrey 2023", "Christian McCaffrey"),
    ("Connor McDavid 2023", "Connor McDavid"),
    ("LeBron James 2012 season", "LeBron James"),
    ("Dirk Nowitzki 2007", "Dirk Nowitzki"),
]


@pytest.mark.parametrize("question,expected", NAME_CASES)
def test_extract_named_player(question: str, expected: str):
    assert SQLAgent._extract_named_player(question) == expected


@pytest.mark.parametrize(
    "question",
    [
        "Most points in 2024",
        "Who led scoring in 2024",
        "Top 5 scorers 2024",
        "NBA MVP 2006",
        "award winners 2006",
    ],
)
def test_extract_named_player_none(question: str):
    assert SQLAgent._extract_named_player(question) is None


@pytest.mark.parametrize(
    "question,year",
    [
        ("How did Steve Nash do in the NBA in 2006?", 2006),
        ("Steve Nash NBA 2005", 2005),
        ("Steve Nash NBA 2007", 2007),
        ("Nikola Jokic NBA 2024", 2024),
        ("Stephen Curry NBA 2016", 2016),
    ],
)
def test_named_player_sql_and_rows(sql_agent: SQLAgent, settings, question: str, year: int):
    sql = sql_agent._generate("nba", question)
    assert "like '%" in sql.lower()
    assert f"year = {year}" in sql
    result = execute_query(settings.db_path("nba"), sql)
    assert result["rows"], f"no rows for {question}"


def test_steve_nash_2006_exact(sql_agent: SQLAgent, settings):
    result = sql_agent.run("nba", "How did Steve Nash do in the NBA in 2006?", MagicMock())
    assert "error" not in result
    row = result["rows"][0]
    assert row["player"] == NBA_2006_MVP[0]
    assert float(row["pts"]) == pytest.approx(NBA_2006_MVP[1])
    assert "MVP-1" in str(row.get("awards", ""))


def test_mvp_winner_2006(sql_agent: SQLAgent, settings):
    result = sql_agent.run("nba", "Who won MVP in the NBA in 2006?", MagicMock())
    assert "error" not in result
    assert result["rows"]
    assert result["rows"][0]["player"] == NBA_2006_MVP[0]
    assert "MVP-1" in result["generated_sql"] or "mvp-1" in result["generated_sql"].lower()


def test_mvp_winner_2024(sql_agent: SQLAgent, settings):
    result = sql_agent.run("nba", "Who won MVP in the NBA in 2024?", MagicMock())
    assert "error" not in result
    assert result["rows"][0]["player"] == NBA_2024_SCORING_LEADER[0]


@pytest.mark.parametrize(
    "question",
    [
        "NBA award winners 2006",
        "NBA awards in 2024",
        "NBA award winners 2016",
    ],
)
def test_award_winners_return_rows(sql_agent: SQLAgent, settings, question: str):
    result = sql_agent.run("nba", question, MagicMock())
    assert "error" not in result
    assert result["rows"]
    assert "awards" in result["generated_sql"].lower()


@pytest.mark.parametrize(
    "sport,question,needle",
    [
        ("nba", "Most points per game leaders in 2024 NBA", "order by pts desc"),
        ("nba", "Top 3 NBA scorers 2024", "limit 3"),
        ("nba", "Most threes made in 2016", "order by c_3p desc"),
        ("nfl", "Most rushing yards in 2023", "rushing_yds"),
        ("nfl", "Most passing yards in 2023", "from passing"),
        ("nfl", "Most receiving yards in 2023", "receiving_yds"),
        ("nfl", "Most sacks in 2023", "order by"),
        ("nhl", "NHL scoring leader most points in 2023", "player_pts"),
        ("nhl", "Top 5 NHL points 2023", "limit 5"),
    ],
)
def test_leaderboard_sql_needles(sql_agent: SQLAgent, sport: str, question: str, needle: str):
    sql = sql_agent._generate(sport, question)
    assert needle in sql.lower()


@pytest.mark.parametrize(
    "question,expected",
    [
        ("top 3 scorers 2024", 3),
        ("top 10 leaders 2024", 10),
        ("scoring leader 2024", 5),
        ("most points 2024", 5),
        ("top player 2024", 1),
        ("who led scoring 2024", 5),
    ],
)
def test_limit_parsing(question: str, expected: int):
    assert SQLAgent._limit(question) == expected


@pytest.mark.parametrize(
    "question,ambiguous",
    [
        ("Compare points vs assists 2024", True),
        ("Most points 2024", False),
        ("Rushing and receiving leaders 2023", True),
        ("Most rushing yards 2023", False),
        ("2023 vs 2024 scoring", True),
    ],
)
def test_ambiguous_detection(question: str, ambiguous: bool):
    assert SQLAgent._is_ambiguous(question) is ambiguous


@pytest.mark.parametrize(
    "question,yes",
    [
        ("most threes made 2016", True),
        ("3PM leaders 2016", True),
        ("best three point percentage 2016", False),
        ("most points 2016", False),
    ],
)
def test_asks_threes_made(question: str, yes: bool):
    assert SQLAgent._asks_threes_made(question) is yes


# ---------------------------------------------------------------------------
# Hints / schema expectations for awards
# ---------------------------------------------------------------------------


def test_nba_hints_mention_awards(settings):
    cache = load_schema_cache(settings.schema_cache_dir / "nba.json")
    hints = dynamic_hints("nba", cache)
    assert "awards" in hints.lower()
    assert "like '%name%'" in hints.lower() or "named player" in hints.lower()


def test_fixture_has_awards_and_nash(settings):
    rows = execute_query(
        settings.db_path("nba"),
        "SELECT player, awards, pts FROM player_mvp_stats "
        "WHERE player LIKE '%Steve Nash%' AND year = 2006",
    )
    assert rows["rows"]
    assert "MVP-1" in str(rows["rows"][0]["awards"])


@pytest.mark.parametrize("year", [2005, 2006, 2007, 2016, 2024])
def test_nba_year_has_players(settings, year: int):
    rows = execute_query(
        settings.db_path("nba"),
        f"SELECT COUNT(*) AS n FROM player_mvp_stats WHERE year = {year}",
    )
    assert int(rows["rows"][0]["n"]) >= 1


@pytest.mark.parametrize("year", [2020, 2021, 2022, 2023, 2024])
def test_nfl_year_has_passers(settings, year: int):
    rows = execute_query(
        settings.db_path("nfl"),
        f"SELECT COUNT(*) AS n FROM passing WHERE year = {year}",
    )
    assert int(rows["rows"][0]["n"]) >= 1


@pytest.mark.parametrize("year", [2020, 2021, 2022, 2023, 2024])
def test_nhl_year_has_skaters(settings, year: int):
    rows = execute_query(
        settings.db_path("nhl"),
        f"SELECT COUNT(*) AS n FROM player_team_stats WHERE year = {year}",
    )
    assert int(rows["rows"][0]["n"]) >= 1


# Production CSV-backed DBs (optional — skip if not imported locally)
PROD_ROOT = None


def _prod_nba():
    from pathlib import Path
    from hornet.config import ROOT

    path = ROOT / "data" / "databases" / "nba.db"
    if not path.exists():
        return None
    # fixture session uses tmp DBs; check the repo copy separately
    repo = Path(__file__).resolve().parents[1] / "data" / "databases" / "nba.db"
    return repo if repo.exists() else None


def test_production_nash_if_present():
    path = _prod_nba()
    if path is None:
        pytest.skip("production nba.db not present")
    rows = execute_query(
        path,
        "SELECT player, year, awards, pts, share FROM player_mvp_stats "
        "WHERE player LIKE '%Steve Nash%' AND year = 2006",
    )
    assert rows["rows"]
    assert rows["rows"][0]["player"] == "Steve Nash"
    assert "MVP" in str(rows["rows"][0].get("awards") or "")
