"""
test_leverage.py — Tests for M41 (Leverage Oracle tools).
"""
from __future__ import annotations

import pytest
from unittest.mock import patch


# ── Tool registration tests ───────────────────────────────────────────────────


def test_leverage_tools_registered():
    import sovereign_agent.tools  # noqa: F401
    from sovereign_agent.authority import _TIER_REGISTRY
    assert "score_leverage" in _TIER_REGISTRY
    assert "leverage_audit" in _TIER_REGISTRY
    assert "prioritize_objectives" in _TIER_REGISTRY
    for name in ("score_leverage", "leverage_audit", "prioritize_objectives"):
        assert _TIER_REGISTRY[name].tier == 0, f"{name} should be T0"


def test_leverage_tools_have_failure_modes():
    from sovereign_agent.tools.leverage_tools import (
        ScoreLeverageTool, LeverageAuditTool, PrioritizeObjectivesTool,
    )
    for cls in (ScoreLeverageTool, LeverageAuditTool, PrioritizeObjectivesTool):
        assert cls.failure_modes, f"{cls.name} missing failure_modes"


# ── score_leverage unit tests ─────────────────────────────────────────────────


def test_compute_leverage_score_high_blocker():
    from sovereign_agent.tools.leverage_tools import _compute_leverage_score
    result = _compute_leverage_score(
        "Fix blocking dependency that is stuck in the pipeline",
        "downstream tasks depend on this completing first",
        None,
    )
    assert result["leverage_score"] > 0.4
    assert result["recommendation"] in {"do_first", "do_normal", "defer"}


def test_compute_leverage_score_low_polish():
    from sovereign_agent.tools.leverage_tools import _compute_leverage_score
    result = _compute_leverage_score("Add extra whitespace to readme", None, None)
    assert result["leverage_score"] < 0.5
    assert result["recommendation"] in {"defer", "skip"}


def test_compute_leverage_score_deterministic():
    from sovereign_agent.tools.leverage_tools import _compute_leverage_score
    r1 = _compute_leverage_score("Unblock downstream chain", "depends on gating step", None)
    r2 = _compute_leverage_score("Unblock downstream chain", "depends on gating step", None)
    assert r1["leverage_score"] == r2["leverage_score"]
    assert r1["recommendation"] == r2["recommendation"]


def test_compute_leverage_score_returns_0_to_1():
    from sovereign_agent.tools.leverage_tools import _compute_leverage_score
    for text in ["do nothing", "this blocks everything urgent", "delete all data", "enable cascade"]:
        result = _compute_leverage_score(text, None, None)
        assert 0.0 <= result["leverage_score"] <= 1.0


def test_recommendation_is_valid():
    from sovereign_agent.tools.leverage_tools import _compute_leverage_score
    valid = {"do_first", "do_normal", "defer", "skip"}
    for text in ["block", "cascade enable", "simple cleanup", "force delete"]:
        result = _compute_leverage_score(text, None, None)
        assert result["recommendation"] in valid


# ── score_leverage tool tests ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_score_leverage_executes():
    from sovereign_agent.tools.leverage_tools import ScoreLeverageTool
    tool = ScoreLeverageTool()
    result = await tool.execute(
        tool.Args(action_description="Fix blocking test failure", context="blocks CI pipeline"),
        trace_id="t1",
    )
    assert result.ok
    assert "leverage_score" in result.output
    assert "recommendation" in result.output
    assert "reasoning" in result.output
    assert "factors" in result.output


@pytest.mark.asyncio
async def test_score_leverage_rejects_empty():
    from sovereign_agent.tools.leverage_tools import ScoreLeverageTool
    tool = ScoreLeverageTool()
    result = await tool.execute(tool.Args(action_description="   "), trace_id="t1")
    assert not result.ok
    assert "empty" in result.error


@pytest.mark.asyncio
async def test_score_leverage_with_alternatives():
    from sovereign_agent.tools.leverage_tools import ScoreLeverageTool
    tool = ScoreLeverageTool()
    result = await tool.execute(
        tool.Args(
            action_description="Refactor auth module",
            alternatives=["Skip and keep tech debt", "Defer to next sprint"],
        ),
        trace_id="t1",
    )
    assert result.ok
    assert result.output["opportunity_cost"] in {"low", "medium", "high"}


# ── leverage_audit tests ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_leverage_audit_empty_events():
    from sovereign_agent.tools.leverage_tools import LeverageAuditTool
    tool = LeverageAuditTool()
    with patch("sovereign_agent.tools.leverage_tools._load_action_events", return_value=[]):
        result = await tool.execute(tool.Args(), trace_id="t1")
    assert result.ok
    assert "high" in result.output
    assert "low" in result.output
    assert "pattern_insights" in result.output
    assert result.output["stats"]["total_audited"] == 0


@pytest.mark.asyncio
async def test_leverage_audit_with_events():
    from sovereign_agent.tools.leverage_tools import LeverageAuditTool
    tool = LeverageAuditTool()
    mock_events = [
        {"flag": "commit-d", "payload": {"message": "fix blocking test failure"}},
        {"flag": "tool-start-d", "payload": {"tool": "read_file"}},
    ]
    with patch("sovereign_agent.tools.leverage_tools._load_action_events", return_value=mock_events):
        result = await tool.execute(tool.Args(), trace_id="t1")
    assert result.ok
    assert result.output["stats"]["total_audited"] == 2


# ── prioritize_objectives tests ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_prioritize_objectives_empty():
    from sovereign_agent.tools.leverage_tools import PrioritizeObjectivesTool
    from sovereign_agent.objective_map import _objectives
    _objectives.clear()
    tool = PrioritizeObjectivesTool()
    result = await tool.execute(tool.Args(), trace_id="t1")
    assert result.ok
    assert result.output["count"] == 0
    _objectives.clear()


@pytest.mark.asyncio
async def test_prioritize_objectives_sorts_by_score():
    from sovereign_agent.tools.leverage_tools import PrioritizeObjectivesTool
    from sovereign_agent.objective_map import get_objective_map, _objectives
    _objectives.clear()
    obj_map = get_objective_map()
    obj_map.add("fix blocking downstream dependency", priority="secondary")
    obj_map.add("add extra comment to readme", priority="secondary")

    tool = PrioritizeObjectivesTool()
    result = await tool.execute(tool.Args(), trace_id="t1")
    assert result.ok
    objectives = result.output["objectives"]
    assert len(objectives) == 2
    # Both scored; order by final_score
    assert objectives[0]["final_score"] >= objectives[1]["final_score"]
    _objectives.clear()


# ── loop.py marker test ───────────────────────────────────────────────────────


def test_loop_has_leverage_oracle_marker():
    import pathlib
    p = pathlib.Path(__file__).resolve()
    for _ in range(8):
        c = p.parent / "src" / "sovereign_agent" / "loop.py"
        if c.exists():
            src = c.read_text()
            assert "leverage-oracle-d" in src, "leverage-oracle-d missing from loop.py"
            return
        p = p.parent
    pytest.skip("loop.py not found")
