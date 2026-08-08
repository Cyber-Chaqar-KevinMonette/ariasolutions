"""Tests for aria-xp-live-d — award_aria_xp: the tool Aria calls herself
to record general task-scoring events, mirroring award_game_xp.py's
established precedent for the game-project-scoped ledger."""
from __future__ import annotations

import pytest

from sovereign_agent.tools.award_aria_xp import AwardAriaXPTool


def test_tool_registered_at_tier_1():
    import sovereign_agent.tools  # noqa: F401
    from sovereign_agent.authority import _TIER_REGISTRY
    assert "award_aria_xp" in _TIER_REGISTRY
    assert _TIER_REGISTRY["award_aria_xp"].tier == 1


def test_reachable_under_busy_mode_ceiling():
    from sovereign_agent.authority import tools_available_in_mode
    from sovereign_agent.modes import Mode
    import sovereign_agent.tools  # noqa: F401
    names = {m.name for m in tools_available_in_mode(Mode.BUSY)}
    assert "award_aria_xp" in names


@pytest.mark.asyncio
async def test_empty_note_refused(tmp_path):
    tool = AwardAriaXPTool(data_dir=tmp_path)
    result = await tool.execute(
        tool.Args(event_type="task_success", note=""), trace_id="t1",
    )
    assert not result.ok
    assert "empty_note" in result.error


@pytest.mark.asyncio
async def test_unknown_event_type_refused(tmp_path):
    tool = AwardAriaXPTool(data_dir=tmp_path)
    result = await tool.execute(
        tool.Args(event_type="made_up", note="something"), trace_id="t1",
    )
    assert not result.ok
    assert "unknown_event_type" in result.error


@pytest.mark.asyncio
async def test_task_success_awards_the_named_constant(tmp_path):
    from sovereign_agent.aria_xp import XP_TASK_SUCCESS

    tool = AwardAriaXPTool(data_dir=tmp_path)
    result = await tool.execute(
        tool.Args(event_type="task_success", note="fixed a real bug"), trace_id="t1",
    )
    assert result.ok
    assert result.output["awarded_xp"] == XP_TASK_SUCCESS
    assert "Lv." in result.output["message"]


@pytest.mark.asyncio
async def test_mistake_without_how_to_avoid_is_refused(tmp_path):
    """The whole point: a mistake is never just a bare point deduction."""
    tool = AwardAriaXPTool(data_dir=tmp_path)
    result = await tool.execute(
        tool.Args(event_type="mistake", note="broke something"), trace_id="t1",
    )
    assert not result.ok
    assert "missing_how_to_avoid" in result.error


@pytest.mark.asyncio
async def test_mistake_with_how_to_avoid_opens_a_real_diagnosis_case(tmp_path):
    from sovereign_agent.aria_xp import XP_MISTAKE
    from sovereign_agent.diagnosis import ConflictCatalog

    tool = AwardAriaXPTool(data_dir=tmp_path)
    result = await tool.execute(
        tool.Args(
            event_type="mistake", note="assumed a tool existed that didn't",
            how_to_avoid="verify against the live tool registry first",
        ),
        trace_id="t1",
    )
    assert result.ok
    assert result.output["awarded_xp"] == XP_MISTAKE
    case_id = result.output["case_id"]
    assert case_id

    catalog = ConflictCatalog(tmp_path / "diagnoses")
    assert catalog.get_conflict(case_id) is not None
    assert catalog.get_resolution(case_id) is not None


@pytest.mark.asyncio
async def test_memory_written_event_type_works(tmp_path):
    from sovereign_agent.aria_xp import XP_MEMORY_WRITTEN

    tool = AwardAriaXPTool(data_dir=tmp_path)
    result = await tool.execute(
        tool.Args(event_type="memory_written", note="stored a fact about Kevin"),
        trace_id="t1",
    )
    assert result.ok
    assert result.output["awarded_xp"] == XP_MEMORY_WRITTEN
