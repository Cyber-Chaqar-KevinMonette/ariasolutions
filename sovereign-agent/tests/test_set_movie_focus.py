"""Tests for movie-studio-d — set_movie_focus."""
from __future__ import annotations

import pytest

from sovereign_agent.movie_projects import MovieProject, get_focus, save
from sovereign_agent.tools.set_movie_focus import SetMovieFocusTool


def test_tool_registered_at_tier_1():
    import sovereign_agent.tools  # noqa: F401
    from sovereign_agent.authority import _TIER_REGISTRY
    assert "set_movie_focus" in _TIER_REGISTRY
    assert _TIER_REGISTRY["set_movie_focus"].tier == 1


def test_reachable_under_busy_mode_ceiling():
    from sovereign_agent.authority import tools_available_in_mode
    from sovereign_agent.modes import Mode
    import sovereign_agent.tools  # noqa: F401
    names = {m.name for m in tools_available_in_mode(Mode.BUSY)}
    assert "set_movie_focus" in names


@pytest.mark.asyncio
async def test_unknown_project_refused(tmp_path):
    tool = SetMovieFocusTool(data_dir=tmp_path)
    result = await tool.execute(
        tool.Args(project_slug="ghost", reason="testing"), trace_id="t1"
    )
    assert not result.ok
    assert "unknown_project" in result.error


@pytest.mark.asyncio
async def test_empty_reason_refused(tmp_path):
    save(MovieProject(title="Alpha"), tmp_path)
    tool = SetMovieFocusTool(data_dir=tmp_path)
    result = await tool.execute(
        tool.Args(project_slug="alpha", reason=""), trace_id="t1"
    )
    assert not result.ok
    assert "empty_reason" in result.error
    assert get_focus(tmp_path).slug is None


@pytest.mark.asyncio
async def test_successful_switch_is_logged(tmp_path):
    save(MovieProject(title="Alpha"), tmp_path)
    tool = SetMovieFocusTool(data_dir=tmp_path)
    result = await tool.execute(
        tool.Args(project_slug="alpha",
                 reason="Kevin asked to switch to Alpha", vital=False),
        trace_id="t1",
    )
    assert result.ok
    focus = get_focus(tmp_path)
    assert focus.slug == "alpha"
    assert focus.history[-1]["reason"] == "Kevin asked to switch to Alpha"
    assert focus.history[-1]["vital"] is False


@pytest.mark.asyncio
async def test_vital_switch_is_flagged(tmp_path):
    save(MovieProject(title="Alpha"), tmp_path)
    save(MovieProject(title="Beta"), tmp_path)
    tool = SetMovieFocusTool(data_dir=tmp_path)
    await tool.execute(tool.Args(project_slug="alpha", reason="start here"), trace_id="t1")
    result = await tool.execute(
        tool.Args(project_slug="beta", reason="vital: alpha blocked on missing asset",
                 vital=True),
        trace_id="t1",
    )
    assert result.ok
    focus = get_focus(tmp_path)
    assert focus.slug == "beta"
    assert focus.history[-1]["vital"] is True
