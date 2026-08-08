"""
test_prompt_forge.py — Tests for M32 (forge_prompt, roadblock_protocol, confidence_check).
"""
from __future__ import annotations

import pytest


def test_tools_registered():
    import sovereign_agent.tools  # noqa: F401
    from sovereign_agent.authority import _TIER_REGISTRY
    for name in ("forge_prompt", "roadblock_protocol", "confidence_check"):
        assert name in _TIER_REGISTRY, f"{name} not registered"
        assert _TIER_REGISTRY[name].tier == 0


# ── forge_prompt ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_forge_prompt_returns_structure():
    from sovereign_agent.tools.prompt_forge import ForgePromptTool

    tool = ForgePromptTool()
    result = await tool.execute(
        tool.Args(goal="Analyze the test suite for coverage gaps", task_type="analysis"),
        trace_id="t1",
    )
    assert result.ok
    assert "system_prompt" in result.output
    assert "user_message" in result.output
    assert "reasoning" in result.output
    assert "confidence" in result.output
    assert 0.0 <= result.output["confidence"] <= 1.0


@pytest.mark.asyncio
async def test_forge_prompt_all_task_types():
    from sovereign_agent.tools.prompt_forge import ForgePromptTool
    tool = ForgePromptTool()
    for tt in ("analysis", "generation", "debugging", "research", "planning"):
        result = await tool.execute(
            tool.Args(goal=f"test {tt}", task_type=tt), trace_id="t1"
        )
        assert result.ok, f"forge_prompt failed for task_type={tt!r}: {result.error}"
        assert result.output["task_type"] == tt


@pytest.mark.asyncio
async def test_forge_prompt_unknown_type_rejected():
    from sovereign_agent.tools.prompt_forge import ForgePromptTool
    tool = ForgePromptTool()
    result = await tool.execute(
        tool.Args(goal="do something", task_type="magic"), trace_id="t1"
    )
    assert not result.ok
    assert "unknown task_type" in result.error


@pytest.mark.asyncio
async def test_forge_prompt_with_constraints():
    from sovereign_agent.tools.prompt_forge import ForgePromptTool
    tool = ForgePromptTool()
    result = await tool.execute(
        tool.Args(
            goal="Generate a data model",
            task_type="generation",
            constraints=["must use pydantic", "no external dependencies"],
        ),
        trace_id="t1",
    )
    assert result.ok
    assert "pydantic" in result.output["system_prompt"]


@pytest.mark.asyncio
async def test_forge_prompt_context_raises_confidence():
    from sovereign_agent.tools.prompt_forge import ForgePromptTool
    tool = ForgePromptTool()
    r_no_ctx = await tool.execute(
        tool.Args(goal="analyze something", task_type="analysis"), trace_id="t1"
    )
    r_with_ctx = await tool.execute(
        tool.Args(goal="analyze something", task_type="analysis", context="rich background"),
        trace_id="t1",
    )
    assert r_with_ctx.output["confidence"] >= r_no_ctx.output["confidence"]


# ── roadblock_protocol ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_roadblock_classifies_missing_dep():
    from sovereign_agent.tools.prompt_forge import RoadblockProtocolTool
    tool = RoadblockProtocolTool()
    result = await tool.execute(
        tool.Args(
            obstacle="ModuleNotFoundError: No module named 'torch'",
            attempted_approaches=[],
        ),
        trace_id="t1",
    )
    assert result.ok
    assert result.output["obstacle_class"] == "dependency-missing"
    assert result.output["severity"] == "recoverable"
    assert len(result.output["next_approaches"]) >= 1
    assert all("confidence" in a for a in result.output["next_approaches"])


@pytest.mark.asyncio
async def test_roadblock_classifies_timeout():
    from sovereign_agent.tools.prompt_forge import RoadblockProtocolTool
    tool = RoadblockProtocolTool()
    result = await tool.execute(
        tool.Args(obstacle="subprocess.TimeoutExpired: command timed out after 30s"),
        trace_id="t1",
    )
    assert result.ok
    assert result.output["obstacle_class"] == "timeout"


@pytest.mark.asyncio
async def test_roadblock_escalates_after_multiple_tries():
    from sovereign_agent.tools.prompt_forge import RoadblockProtocolTool
    tool = RoadblockProtocolTool()
    result = await tool.execute(
        tool.Args(
            obstacle="completely unknown error that doesn't match anything",
            attempted_approaches=["tried A", "tried B", "tried C"],
        ),
        trace_id="t1",
    )
    assert result.ok
    assert result.output["escalate_to_human"] is True
    assert result.output["escalation_message"] != ""


@pytest.mark.asyncio
async def test_roadblock_includes_derivatives():
    from sovereign_agent.tools.prompt_forge import RoadblockProtocolTool
    tool = RoadblockProtocolTool()
    result = await tool.execute(
        tool.Args(
            obstacle="permission denied",
            goal_context="writing test results to disk",
        ),
        trace_id="t1",
    )
    assert result.ok
    assert len(result.output["derivatives"]) >= 1


# ── confidence_check ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_confidence_no_evidence():
    from sovereign_agent.tools.prompt_forge import ConfidenceCheckTool
    tool = ConfidenceCheckTool()
    result = await tool.execute(
        tool.Args(claim="The config file is correct."), trace_id="t1"
    )
    assert result.ok
    assert result.output["confidence"] < 0.5
    assert result.output["verdict"] == "uncertain"
    assert result.output["needs_operator_review"] is True


@pytest.mark.asyncio
async def test_confidence_strong_evidence():
    from sovereign_agent.tools.prompt_forge import ConfidenceCheckTool
    tool = ConfidenceCheckTool()
    result = await tool.execute(
        tool.Args(
            claim="Tests are passing.",
            evidence_refs=[
                "pytest ran 2171 tests",
                "exit code was 0",
                "no failures reported",
                "ci output shows green",
                "no error events in log",
            ],
        ),
        trace_id="t1",
    )
    assert result.ok
    assert result.output["confidence"] >= 0.7
    assert result.output["verdict"] == "supported"


@pytest.mark.asyncio
async def test_confidence_threshold_flag():
    from sovereign_agent.tools.prompt_forge import ConfidenceCheckTool
    tool = ConfidenceCheckTool()
    result = await tool.execute(
        tool.Args(
            claim="Memory is intact.",
            evidence_refs=["one observation"],
            threshold=0.9,
        ),
        trace_id="t1",
    )
    assert result.ok
    assert result.output["needs_operator_review"] is True  # below 0.9 threshold


def test_loop_has_plan_approval():
    import pathlib
    p = pathlib.Path(__file__).resolve()
    for _ in range(8):
        c = p.parent / "src" / "sovereign_agent" / "loop.py"
        if c.exists():
            src = c.read_text()
            assert "plan-approval-d" in src, \
                "PLAN APPROVAL section missing — run apply_prompt_forge.sh"
            assert "confidence-derivatives-d" in src
            return
        p = p.parent
    pytest.skip("loop.py not found")
