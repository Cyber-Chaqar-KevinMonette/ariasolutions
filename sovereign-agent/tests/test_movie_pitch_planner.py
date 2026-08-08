"""Tests for movie-studio-d — the Dream Pitch Generator (MoviePitchPlanner).

Mirrors test_drafts_marketing.py's marketing-brief planner test shape.
"""
from __future__ import annotations

import pytest

from sovereign_agent.planners import REGISTRY, get_planner, planner_names
from sovereign_agent.planners.base import PlannerError
from sovereign_agent.planners.movie_pitch import DEFAULT_PITCH_COUNT, DEFAULT_THEME


def test_movie_pitch_in_registry():
    assert "movie-pitch" in REGISTRY
    assert "movie-pitch" in planner_names()


def test_movie_pitch_plan_requires_output():
    p = get_planner("movie-pitch")
    with pytest.raises(PlannerError, match="output"):
        p.plan()


def test_movie_pitch_plan_defaults_theme_when_none_given():
    p = get_planner("movie-pitch")
    plan = p.plan(output="/tmp/pitches.md")
    assert plan.notes == f"theme: {DEFAULT_THEME}"
    assert len(plan.steps) == DEFAULT_PITCH_COUNT
    for step in plan.steps:
        assert step.args["theme"] == DEFAULT_THEME


def test_movie_pitch_plan_honors_explicit_theme():
    p = get_planner("movie-pitch")
    plan = p.plan(theme="a quiet story about a small town", output="/tmp/pitches.md")
    assert "a quiet story about a small town" in plan.notes
    assert all(s.args["theme"] == "a quiet story about a small town" for s in plan.steps)


def test_movie_pitch_plan_honors_count():
    p = get_planner("movie-pitch")
    plan = p.plan(output="/tmp/pitches.md", count=5)
    assert len(plan.steps) == 5
    indices = [s.args["pitch_index"] for s in plan.steps]
    assert indices == [1, 2, 3, 4, 5]
    assert all(s.args["pitch_count"] == 5 for s in plan.steps)


def test_movie_pitch_plan_rejects_zero_count():
    p = get_planner("movie-pitch")
    with pytest.raises(PlannerError, match="count"):
        p.plan(output="/tmp/pitches.md", count=0)


def test_movie_pitch_render_step_includes_context_and_distinctness_instruction():
    p = get_planner("movie-pitch")
    plan = p.plan(theme="hopeful AI futures", output="/tmp/pitches.md", count=2)
    rendered = p.render_step(plan.steps[0], {})
    assert "hopeful AI futures" in rendered
    assert "#1 of 2" in rendered or "1 of 2" in rendered
    assert "distinct" in rendered.lower()
    assert "markdown" in rendered.lower()
    assert "Pitch 1" in rendered
