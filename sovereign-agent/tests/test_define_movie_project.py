"""Tests for movie-studio-d — define_movie_project."""
from __future__ import annotations

import pytest

from sovereign_agent.movie_projects import list_all
from sovereign_agent.tools.define_movie_project import DefineMovieProjectTool


def test_tool_registered_at_tier_1():
    import sovereign_agent.tools  # noqa: F401
    from sovereign_agent.authority import _TIER_REGISTRY
    assert "define_movie_project" in _TIER_REGISTRY
    assert _TIER_REGISTRY["define_movie_project"].tier == 1


def test_reachable_under_busy_mode_ceiling():
    from sovereign_agent.authority import tools_available_in_mode
    from sovereign_agent.modes import Mode
    import sovereign_agent.tools  # noqa: F401
    names = {m.name for m in tools_available_in_mode(Mode.BUSY)}
    assert "define_movie_project" in names


@pytest.mark.asyncio
async def test_invalid_project_refused(tmp_path):
    tool = DefineMovieProjectTool(data_dir=tmp_path)
    result = await tool.execute(
        tool.Args(title="", genre="short-film"), trace_id="t1"
    )
    assert not result.ok
    assert "invalid_project" in result.error


@pytest.mark.asyncio
async def test_other_genre_without_genre_other_refused(tmp_path):
    tool = DefineMovieProjectTool(data_dir=tmp_path)
    result = await tool.execute(
        tool.Args(title="Untitled Thing", genre="other", genre_other=""),
        trace_id="t1",
    )
    assert not result.ok
    assert "invalid_project" in result.error


@pytest.mark.asyncio
async def test_successful_definition_does_not_set_focus(tmp_path):
    from sovereign_agent.movie_projects import get_focus

    tool = DefineMovieProjectTool(data_dir=tmp_path)
    result = await tool.execute(
        tool.Args(title="Test Film", genre="short-film",
                 logline="one clean visual idea", monetization_note="itch.io PWYW"),
        trace_id="t1",
    )
    assert result.ok
    assert result.output["slug"] == "test-film"
    projects = list_all(tmp_path)
    assert len(projects) == 1
    assert projects[0].logline == "one clean visual idea"
    assert get_focus(tmp_path).slug is None  # defining is not focusing
