"""Tests for game-studio-capabilities-d — define_game_project: closes
the gap where only the cockpit form (Kevin-only) could define a project."""
from __future__ import annotations

import pytest

from sovereign_agent.game_projects import list_all
from sovereign_agent.tools.define_game_project import DefineGameProjectTool


def test_tool_registered_at_tier_1():
    import sovereign_agent.tools  # noqa: F401
    from sovereign_agent.authority import _TIER_REGISTRY
    assert "define_game_project" in _TIER_REGISTRY
    assert _TIER_REGISTRY["define_game_project"].tier == 1


def test_reachable_under_busy_mode_ceiling():
    from sovereign_agent.authority import tools_available_in_mode
    from sovereign_agent.modes import Mode
    import sovereign_agent.tools  # noqa: F401
    names = {m.name for m in tools_available_in_mode(Mode.BUSY)}
    assert "define_game_project" in names


@pytest.mark.asyncio
async def test_invalid_project_refused(tmp_path):
    tool = DefineGameProjectTool(data_dir=tmp_path)
    result = await tool.execute(
        tool.Args(project_name="", genre="idle-incremental"), trace_id="t1"
    )
    assert not result.ok
    assert "invalid_project" in result.error


@pytest.mark.asyncio
async def test_other_genre_without_genre_other_refused(tmp_path):
    tool = DefineGameProjectTool(data_dir=tmp_path)
    result = await tool.execute(
        tool.Args(project_name="Rhythm Thing", genre="other", genre_other=""),
        trace_id="t1",
    )
    assert not result.ok
    assert "invalid_project" in result.error


@pytest.mark.asyncio
async def test_successful_definition_does_not_set_focus(tmp_path):
    from sovereign_agent.game_projects import get_focus

    tool = DefineGameProjectTool(data_dir=tmp_path)
    result = await tool.execute(
        tool.Args(project_name="Prestige Clicker", genre="idle-incremental",
                 concept="one loop, replayed", monetization_note="itch.io PWYW"),
        trace_id="t1",
    )
    assert result.ok
    assert result.output["slug"] == "prestige-clicker"
    projects = list_all(tmp_path)
    assert len(projects) == 1
    assert projects[0].concept == "one loop, replayed"
    assert get_focus(tmp_path).slug is None  # defining is not focusing
