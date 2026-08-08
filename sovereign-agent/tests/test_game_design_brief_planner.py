"""Tests for GameDesignBriefPlanner — mirrors tests/test_planners.py
conventions for marketing_brief-shaped planners."""
from __future__ import annotations

import pytest

from sovereign_agent.game_design_doctrine import notes_for
from sovereign_agent.game_projects import GameProject, save
from sovereign_agent.planners.base import PlannerError
from sovereign_agent.planners.game_design_brief import SECTIONS, GameDesignBriefPlanner


def test_registered_in_planner_registry():
    from sovereign_agent.planners import REGISTRY, get_planner
    assert "game-design-brief" in REGISTRY
    assert isinstance(get_planner("game-design-brief"), GameDesignBriefPlanner)


def test_required_args():
    planner = GameDesignBriefPlanner()
    assert planner.required_args() == ("project_slug", "output")


def test_missing_project_slug_raises(tmp_path):
    planner = GameDesignBriefPlanner()
    with pytest.raises(PlannerError):
        planner.plan(output=str(tmp_path / "brief.md"), data_dir=tmp_path)


def test_missing_output_raises(tmp_path):
    save(GameProject(project_name="Test Game"), tmp_path)
    planner = GameDesignBriefPlanner()
    with pytest.raises(PlannerError):
        planner.plan(project_slug="test-game", data_dir=tmp_path)


def test_unknown_project_raises(tmp_path):
    planner = GameDesignBriefPlanner()
    with pytest.raises(PlannerError):
        planner.plan(project_slug="ghost", output=str(tmp_path / "brief.md"),
                     data_dir=tmp_path)


def test_plan_emits_sections_in_order(tmp_path):
    save(GameProject(project_name="Flat Runner", genre="platformer", dimension="2d"), tmp_path)
    planner = GameDesignBriefPlanner()
    result = planner.plan(project_slug="flat-runner", output=str(tmp_path / "brief.md"),
                          data_dir=tmp_path)
    expected = [name for name, _ in SECTIONS]
    got = [step.args["section"] for step in result.steps]
    assert got == expected
    assert all(step.kind == "compose_game_design_section" for step in result.steps)


def test_skip_excludes_sections(tmp_path):
    save(GameProject(project_name="Flat Runner", dimension="2d"), tmp_path)
    planner = GameDesignBriefPlanner()
    result = planner.plan(project_slug="flat-runner", output=str(tmp_path / "brief.md"),
                          data_dir=tmp_path, skip=["level-plan"])
    got = [step.args["section"] for step in result.steps]
    assert "level-plan" not in got
    assert len(got) == len(SECTIONS) - 1


def test_render_step_threads_doctrine_notes(tmp_path):
    project = GameProject(project_name="Cube World", genre="puzzle", dimension="3d")
    save(project, tmp_path)
    planner = GameDesignBriefPlanner()
    result = planner.plan(project_slug="cube-world", output=str(tmp_path / "brief.md"),
                          data_dir=tmp_path)
    rendered = planner.render_step(result.steps[0], {})
    assert "Cube World" in rendered
    assert "world-class expert game designer" in rendered
    assert notes_for(project) in rendered
