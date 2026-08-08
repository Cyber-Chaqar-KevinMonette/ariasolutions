"""
test_researcher.py — Tests for M39 (Theoretical Researcher tools).
"""
from __future__ import annotations

import json
import pytest
from unittest.mock import patch, MagicMock


# ── Tool registration tests ───────────────────────────────────────────────────


def test_researcher_tools_registered():
    import sovereign_agent.tools  # noqa: F401
    from sovereign_agent.authority import _TIER_REGISTRY
    assert "form_hypothesis" in _TIER_REGISTRY
    assert "design_experiment" in _TIER_REGISTRY
    assert "evaluate_result" in _TIER_REGISTRY
    assert "research_queue" in _TIER_REGISTRY
    for name in ("form_hypothesis", "design_experiment", "evaluate_result", "research_queue"):
        assert _TIER_REGISTRY[name].tier == 0, f"{name} should be T0"


def test_researcher_tools_have_failure_modes():
    from sovereign_agent.tools.researcher_tools import (
        FormHypothesisTool, DesignExperimentTool, EvaluateResultTool, ResearchQueueTool,
    )
    for cls in (FormHypothesisTool, DesignExperimentTool, EvaluateResultTool, ResearchQueueTool):
        assert cls.failure_modes, f"{cls.name} missing failure_modes"


# ── form_hypothesis tests ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_form_hypothesis_returns_structure():
    from sovereign_agent.tools.researcher_tools import FormHypothesisTool
    tool = FormHypothesisTool()
    with patch("sovereign_agent.tools.researcher_tools._write_hypothesis_atom", return_value="hyp-001"):
        result = await tool.execute(
            tool.Args(
                question="does caching reduce tool latency?",
                context="T0 tools are called repeatedly with same args",
                estimated_value=0.8,
                estimated_cost="low",
            ),
            trace_id="t1",
        )
    assert result.ok
    output = result.output
    assert output["id"] == "hyp-001"
    assert "hypothesis" in output
    assert "null_hypothesis" in output
    assert "prediction" in output
    assert output["falsifiable"] is True
    assert 0.0 <= output["confidence_prior"] <= 1.0
    assert output["estimated_test_cost"] == "low"
    assert isinstance(output["go_nogo"], bool)


@pytest.mark.asyncio
async def test_form_hypothesis_rejects_invalid_cost():
    from sovereign_agent.tools.researcher_tools import FormHypothesisTool
    tool = FormHypothesisTool()
    result = await tool.execute(
        tool.Args(question="?", context="ctx", estimated_cost="ultra"),
        trace_id="t1",
    )
    assert not result.ok
    assert "invalid cost level" in result.error


def test_go_nogo_high_value_low_cost():
    from sovereign_agent.tools.researcher_tools import _compute_go_nogo
    assert _compute_go_nogo(0.9, "low") is True


def test_go_nogo_low_value_high_cost():
    from sovereign_agent.tools.researcher_tools import _compute_go_nogo
    assert _compute_go_nogo(0.1, "high") is False


def test_go_nogo_deterministic():
    from sovereign_agent.tools.researcher_tools import _compute_go_nogo
    result1 = _compute_go_nogo(0.7, "medium")
    result2 = _compute_go_nogo(0.7, "medium")
    assert result1 == result2


# ── design_experiment tests ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_design_experiment_returns_steps():
    from sovereign_agent.tools.researcher_tools import DesignExperimentTool
    tool = DesignExperimentTool()
    mock_hyp = {
        "hypothesis": "if we cache, latency drops",
        "null_hypothesis": "no change",
        "prediction": "cache hits reduce calls by 50%",
        "value_if_confirmed": 0.8,
        "estimated_test_cost": "low",
    }
    with patch("sovereign_agent.tools.researcher_tools._load_hypothesis", return_value=mock_hyp):
        result = await tool.execute(
            tool.Args(hypothesis_id="hyp-001"),
            trace_id="t1",
        )
    assert result.ok
    output = result.output
    assert len(output["steps"]) >= 3
    assert "success_criteria" in output
    assert "failure_criteria" in output
    assert isinstance(output["go_nogo"], bool)


@pytest.mark.asyncio
async def test_design_experiment_not_found():
    from sovereign_agent.tools.researcher_tools import DesignExperimentTool
    tool = DesignExperimentTool()
    with patch("sovereign_agent.tools.researcher_tools._load_hypothesis", return_value=None):
        result = await tool.execute(tool.Args(hypothesis_id="no-such-id"), trace_id="t1")
    assert not result.ok
    assert "not found" in result.error


# ── evaluate_result tests ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_evaluate_result_confirmed():
    from sovereign_agent.tools.researcher_tools import EvaluateResultTool
    tool = EvaluateResultTool()
    mock_hyp = {
        "hypothesis": "caching helps",
        "confidence_prior": 0.5,
        "null_hypothesis": "no change",
        "prediction": "hit rate > 0",
    }
    with patch("sovereign_agent.tools.researcher_tools._load_hypothesis", return_value=mock_hyp), \
         patch("sovereign_agent.tools.researcher_tools._write_evaluation_atom", return_value="eval-001"):
        result = await tool.execute(
            tool.Args(
                hypothesis_id="hyp-001",
                observation="cache hit rate was 42% — latency down 30ms",
                verdict="confirmed",
            ),
            trace_id="t1",
        )
    assert result.ok
    output = result.output
    assert output["verdict"] == "confirmed"
    assert output["confidence_delta"] == pytest.approx(0.3)
    assert output["new_confidence"] > 0.5
    assert "lesson_material" in output
    assert len(output["next_actions"]) > 0


@pytest.mark.asyncio
async def test_evaluate_result_refuted():
    from sovereign_agent.tools.researcher_tools import EvaluateResultTool
    tool = EvaluateResultTool()
    mock_hyp = {"hypothesis": "...", "confidence_prior": 0.6, "null_hypothesis": "...", "prediction": "..."}
    with patch("sovereign_agent.tools.researcher_tools._load_hypothesis", return_value=mock_hyp), \
         patch("sovereign_agent.tools.researcher_tools._write_evaluation_atom", return_value="eval-002"):
        result = await tool.execute(
            tool.Args(hypothesis_id="hyp-002", observation="no change observed", verdict="refuted"),
            trace_id="t1",
        )
    assert result.ok
    assert result.output["confidence_delta"] == pytest.approx(-0.3)
    assert result.output["new_confidence"] < 0.6


@pytest.mark.asyncio
async def test_evaluate_result_invalid_verdict():
    from sovereign_agent.tools.researcher_tools import EvaluateResultTool
    tool = EvaluateResultTool()
    result = await tool.execute(
        tool.Args(hypothesis_id="h1", observation="obs", verdict="maybe"),
        trace_id="t1",
    )
    assert not result.ok
    assert "invalid verdict" in result.error


# ── research_queue tests ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_research_queue_returns_filtered():
    from sovereign_agent.tools.researcher_tools import ResearchQueueTool
    tool = ResearchQueueTool()
    mock_hypotheses = [
        {"id": "h1", "value_if_confirmed": 0.9, "estimated_test_cost": "low", "hypothesis": "A"},
        {"id": "h2", "value_if_confirmed": 0.3, "estimated_test_cost": "low", "hypothesis": "B"},
        {"id": "h3", "value_if_confirmed": 0.8, "estimated_test_cost": "high", "hypothesis": "C"},
    ]
    with patch("sovereign_agent.tools.researcher_tools._load_pending_hypotheses", return_value=mock_hypotheses):
        result = await tool.execute(
            tool.Args(min_value=0.5, max_cost="medium"),
            trace_id="t1",
        )
    assert result.ok
    queue = result.output["queue"]
    # h2 filtered (value < 0.5), h3 filtered (cost too high), only h1
    assert len(queue) == 1
    assert queue[0]["id"] == "h1"


@pytest.mark.asyncio
async def test_research_queue_sorts_by_value_cost():
    from sovereign_agent.tools.researcher_tools import ResearchQueueTool
    tool = ResearchQueueTool()
    mock_hypotheses = [
        {"id": "h1", "value_if_confirmed": 0.6, "estimated_test_cost": "medium", "hypothesis": "A"},
        {"id": "h2", "value_if_confirmed": 0.9, "estimated_test_cost": "low", "hypothesis": "B"},
    ]
    with patch("sovereign_agent.tools.researcher_tools._load_pending_hypotheses", return_value=mock_hypotheses):
        result = await tool.execute(tool.Args(min_value=0.0, max_cost="medium"), trace_id="t1")
    assert result.ok
    queue = result.output["queue"]
    # h2 should score higher (0.9/2 > 0.6/2)
    assert queue[0]["id"] == "h2"


# ── loop.py marker test ───────────────────────────────────────────────────────


def test_loop_has_theoretical_researcher_marker():
    import pathlib
    p = pathlib.Path(__file__).resolve()
    for _ in range(8):
        c = p.parent / "src" / "sovereign_agent" / "loop.py"
        if c.exists():
            src = c.read_text()
            assert "theoretical-researcher-d" in src, "theoretical-researcher-d missing from loop.py"
            return
        p = p.parent
    pytest.skip("loop.py not found")
