"""Tests for game-studio-capabilities-d — award_game_xp: closes the gap
where game_dev_xp.award() had no tool wrapper at all."""
from __future__ import annotations

import pytest

from sovereign_agent.game_projects import GameProject, save
from sovereign_agent.tools.award_game_xp import AwardGameXPTool


def test_tool_registered_at_tier_1():
    import sovereign_agent.tools  # noqa: F401
    from sovereign_agent.authority import _TIER_REGISTRY
    assert "award_game_xp" in _TIER_REGISTRY
    assert _TIER_REGISTRY["award_game_xp"].tier == 1


def test_reachable_under_busy_mode_ceiling():
    from sovereign_agent.authority import tools_available_in_mode
    from sovereign_agent.modes import Mode
    import sovereign_agent.tools  # noqa: F401
    names = {m.name for m in tools_available_in_mode(Mode.BUSY)}
    assert "award_game_xp" in names


@pytest.mark.asyncio
async def test_unknown_project_refused(tmp_path):
    tool = AwardGameXPTool(data_dir=tmp_path)
    result = await tool.execute(
        tool.Args(project_slug="ghost", event_type="task_completed", note="x"),
        trace_id="t1",
    )
    assert not result.ok
    assert "unknown_project" in result.error


@pytest.mark.asyncio
async def test_empty_note_refused(tmp_path):
    save(GameProject(project_name="Alpha"), tmp_path)
    tool = AwardGameXPTool(data_dir=tmp_path)
    result = await tool.execute(
        tool.Args(project_slug="alpha", event_type="task_completed", note="  "),
        trace_id="t1",
    )
    assert not result.ok
    assert "empty_note" in result.error


@pytest.mark.asyncio
async def test_unknown_event_type_refused(tmp_path):
    save(GameProject(project_name="Alpha"), tmp_path)
    tool = AwardGameXPTool(data_dir=tmp_path)
    result = await tool.execute(
        tool.Args(project_slug="alpha", event_type="made_up", note="x"),
        trace_id="t1",
    )
    assert not result.ok
    assert "unknown_event_type" in result.error


@pytest.mark.asyncio
async def test_successful_award_uses_named_constant(tmp_path):
    from sovereign_agent.game_dev_xp import XP_MILESTONE

    save(GameProject(project_name="Alpha"), tmp_path)
    tool = AwardGameXPTool(data_dir=tmp_path)
    result = await tool.execute(
        tool.Args(project_slug="alpha", event_type="milestone",
                 note="first playable level, feels good"),
        trace_id="t1",
    )
    assert result.ok
    assert result.output["awarded_xp"] == XP_MILESTONE
    assert result.output["total_xp"] == XP_MILESTONE
    assert result.output["level"] == 1
