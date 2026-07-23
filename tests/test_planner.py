"""Planner routing tests — preserve player/awards intent on single-sport asks."""

from __future__ import annotations

from hornet.agents.planner import build_data_plan, sport_sub_question


def test_single_sport_preserves_player_question():
    q = "How did Steve Nash do in the NBA in 2006?"
    plan = build_data_plan(q)
    assert plan is not None
    assert len(plan.steps) == 1
    assert plan.steps[0].arguments["sport"] == "nba"
    assert plan.steps[0].arguments["question"] == q


def test_single_sport_preserves_mvp_question():
    q = "Who won MVP in the NBA in 2006?"
    plan = build_data_plan(q)
    assert plan is not None
    assert plan.steps[0].arguments["question"] == q
    assert "Top 5" not in plan.steps[0].arguments["question"]


def test_single_sport_preserves_awards_question():
    q = "NBA award winners 2006"
    plan = build_data_plan(q)
    assert plan is not None
    assert plan.steps[0].arguments["question"] == q


def test_cross_sport_still_rewrites_to_leaderboards():
    q = "Compare NBA and NHL scoring in 2024"
    plan = build_data_plan(q)
    assert plan is not None
    assert len(plan.steps) == 2
    questions = {s.arguments["sport"]: s.arguments["question"] for s in plan.steps}
    assert "Top" in questions["nba"]
    assert "points" in questions["nba"].lower()
    assert "Top" in questions["nhl"]


def test_sport_sub_question_still_builds_leaderboards():
    assert sport_sub_question("nba", "compare leagues 2024").startswith("Top")
