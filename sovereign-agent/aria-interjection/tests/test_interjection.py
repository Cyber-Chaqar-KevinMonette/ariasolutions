"""
test_interjection.py — Tests for M37 (Objective Map + interjection tools).
"""
from __future__ import annotations

import json
import pytest
from unittest.mock import patch, MagicMock


# ── ObjectiveMap unit tests ───────────────────────────────────────────────────


def test_objective_map_add_returns_objective():
    from sovereign_agent.objective_map import ObjectiveMap, _objectives
    _objectives.clear()
    obj_map = ObjectiveMap()
    obj = obj_map.add("run the full test suite", priority="secondary", scope="this_session")
    assert obj.id
    assert obj.text == "run the full test suite"
    assert obj.priority == "secondary"
    assert obj.scope == "this_session"
    assert obj.status == "active"
    _objectives.clear()


def test_objective_map_list_active():
    from sovereign_agent.objective_map import ObjectiveMap, _objectives
    _objectives.clear()
    obj_map = ObjectiveMap()
    obj_map.add("task 1", priority="primary")
    obj_map.add("task 2", priority="background")
    active = obj_map.list_active()
    assert len(active) == 2
    _objectives.clear()


def test_objective_map_complete():
    from sovereign_agent.objective_map import ObjectiveMap, _objectives
    _objectives.clear()
    obj_map = ObjectiveMap()
    obj = obj_map.add("complete me")
    result = obj_map.complete(obj.id)
    assert result is not None
    assert result.status == "complete"
    assert result.completed_at is not None
    # Completed not in active list
    active = obj_map.list_active()
    assert all(o.id != obj.id for o in active)
    _objectives.clear()


def test_objective_map_by_priority_order():
    from sovereign_agent.objective_map import ObjectiveMap, _objectives
    _objectives.clear()
    obj_map = ObjectiveMap()
    obj_map.add("background task", priority="background")
    obj_map.add("secondary task", priority="secondary")
    obj_map.add("primary task", priority="primary")
    sorted_objectives = obj_map.by_priority()
    assert sorted_objectives[0].priority == "primary"
    assert sorted_objectives[1].priority == "secondary"
    assert sorted_objectives[2].priority == "background"
    _objectives.clear()


def test_objective_map_add_btw():
    from sovereign_agent.objective_map import ObjectiveMap, _objectives
    _objectives.clear()
    obj_map = ObjectiveMap()
    obj = obj_map.add_btw("by the way, check the logs")
    assert obj.note == "btw"
    assert obj.priority == "background"
    assert obj.status == "active"
    _objectives.clear()


def test_objective_map_get_returns_none_unknown():
    from sovereign_agent.objective_map import ObjectiveMap, _objectives
    _objectives.clear()
    obj_map = ObjectiveMap()
    assert obj_map.get("does-not-exist") is None
    _objectives.clear()


# ── Tool registration tests ───────────────────────────────────────────────────


def test_interjection_tools_registered():
    import sovereign_agent.tools  # noqa: F401
    from sovereign_agent.authority import _TIER_REGISTRY
    assert "add_objective" in _TIER_REGISTRY
    assert "btw_note" in _TIER_REGISTRY
    assert "list_objectives" in _TIER_REGISTRY
    assert "complete_objective" in _TIER_REGISTRY
    assert _TIER_REGISTRY["add_objective"].tier == 1
    assert _TIER_REGISTRY["btw_note"].tier == 1
    assert _TIER_REGISTRY["list_objectives"].tier == 0
    assert _TIER_REGISTRY["complete_objective"].tier == 1


def test_interjection_tools_have_failure_modes():
    from sovereign_agent.tools.interjection_tools import (
        AddObjectiveTool, BtwNoteTool, ListObjectivesTool, CompleteObjectiveTool,
    )
    for cls in (AddObjectiveTool, BtwNoteTool, ListObjectivesTool, CompleteObjectiveTool):
        assert cls.failure_modes, f"{cls.name} missing failure_modes"


# ── Tool execute tests ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_add_objective_executes():
    from sovereign_agent.tools.interjection_tools import AddObjectiveTool
    from sovereign_agent.objective_map import _objectives
    _objectives.clear()
    tool = AddObjectiveTool()
    with patch("sovereign_agent.tools.interjection_tools._write_objective_atom", return_value="atom-1"):
        result = await tool.execute(
            tool.Args(text="check test coverage", priority="secondary", scope="this_session"),
            trace_id="t1",
        )
    assert result.ok
    assert "objective_id" in result.output
    assert result.output["priority"] == "secondary"
    _objectives.clear()


@pytest.mark.asyncio
async def test_add_objective_rejects_invalid_priority():
    from sovereign_agent.tools.interjection_tools import AddObjectiveTool
    from sovereign_agent.objective_map import _objectives
    _objectives.clear()
    tool = AddObjectiveTool()
    with patch("sovereign_agent.tools.interjection_tools._write_objective_atom", return_value="atom-1"):
        result = await tool.execute(
            tool.Args(text="test", priority="ultra", scope="this_session"),
            trace_id="t1",
        )
    assert not result.ok
    assert "invalid priority" in result.error
    _objectives.clear()


@pytest.mark.asyncio
async def test_btw_note_executes():
    from sovereign_agent.tools.interjection_tools import BtwNoteTool
    from sovereign_agent.objective_map import _objectives
    _objectives.clear()
    tool = BtwNoteTool()
    with patch("sovereign_agent.tools.interjection_tools._write_objective_atom", return_value="atom-2"):
        result = await tool.execute(
            tool.Args(text="by the way, the DB has stale indexes"),
            trace_id="t1",
        )
    assert result.ok
    assert "note_id" in result.output
    _objectives.clear()


@pytest.mark.asyncio
async def test_list_objectives_splits_btw_notes():
    from sovereign_agent.tools.interjection_tools import ListObjectivesTool, AddObjectiveTool, BtwNoteTool
    from sovereign_agent.objective_map import _objectives
    _objectives.clear()
    with patch("sovereign_agent.tools.interjection_tools._write_objective_atom", return_value="x"):
        tool = AddObjectiveTool()
        await tool.execute(tool.Args(text="real objective"), trace_id="t1")
        tool2 = BtwNoteTool()
        await tool2.execute(tool2.Args(text="btw note"), trace_id="t1")
    list_tool = ListObjectivesTool()
    result = await list_tool.execute(list_tool.Args(), trace_id="t1")
    assert result.ok
    assert len(result.output["objectives"]) == 1
    assert len(result.output["btw_notes"]) == 1
    _objectives.clear()


@pytest.mark.asyncio
async def test_complete_objective_marks_done():
    from sovereign_agent.tools.interjection_tools import AddObjectiveTool, CompleteObjectiveTool
    from sovereign_agent.objective_map import _objectives
    _objectives.clear()
    with patch("sovereign_agent.tools.interjection_tools._write_objective_atom", return_value="x"):
        add_tool = AddObjectiveTool()
        result = await add_tool.execute(add_tool.Args(text="task to complete"), trace_id="t1")
        obj_id = result.output["objective_id"]
        comp_tool = CompleteObjectiveTool()
        comp_result = await comp_tool.execute(
            comp_tool.Args(objective_id=obj_id, outcome_note="done via pytest"),
            trace_id="t1",
        )
    assert comp_result.ok
    assert comp_result.output["status"] == "complete"
    _objectives.clear()


@pytest.mark.asyncio
async def test_complete_objective_unknown_id():
    from sovereign_agent.tools.interjection_tools import CompleteObjectiveTool
    from sovereign_agent.objective_map import _objectives
    _objectives.clear()
    tool = CompleteObjectiveTool()
    result = await tool.execute(tool.Args(objective_id="no-such-id"), trace_id="t1")
    assert not result.ok
    assert "not found" in result.error
    _objectives.clear()


# ── loop.py marker test ───────────────────────────────────────────────────────


def test_loop_has_objective_map_marker():
    import pathlib
    p = pathlib.Path(__file__).resolve()
    for _ in range(8):
        c = p.parent / "src" / "sovereign_agent" / "loop.py"
        if c.exists():
            src = c.read_text()
            assert "objective-map-d" in src, "objective-map-d missing from loop.py"
            return
        p = p.parent
    pytest.skip("loop.py not found")
