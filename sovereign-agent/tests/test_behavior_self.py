"""
test_behavior_self.py — Tests for read/write behavior pattern tools (M20).
"""
from __future__ import annotations
import pytest
from pathlib import Path
from unittest.mock import patch


def test_tools_registered():
    import sovereign_agent.tools  # noqa: F401
    from sovereign_agent.authority import _TIER_REGISTRY
    assert "read_behavior_patterns" in _TIER_REGISTRY
    assert _TIER_REGISTRY["read_behavior_patterns"].tier == 0
    assert "write_behavior_pattern" in _TIER_REGISTRY
    assert _TIER_REGISTRY["write_behavior_pattern"].tier == 1


def test_failure_modes():
    from sovereign_agent.tools.behavior_tools import ReadBehaviorPatternsTool, WriteBehaviorPatternTool
    assert ReadBehaviorPatternsTool.failure_modes
    assert WriteBehaviorPatternTool.failure_modes


@pytest.mark.asyncio
async def test_read_empty_store(tmp_path):
    """Empty store returns ok=True with 'no patterns' message."""
    from sovereign_agent.tools.behavior_tools import ReadBehaviorPatternsTool

    store_path = tmp_path / "behavior-patterns.ndjson"

    with patch("sovereign_agent.tools.behavior_tools._store_path", return_value=store_path):
        tool = ReadBehaviorPatternsTool()
        result = await tool.execute(tool.Args(), trace_id="t1")

    assert result.ok
    assert "No active" in result.output
    assert result.metadata["count"] == 0


@pytest.mark.asyncio
async def test_write_then_read(tmp_path):
    """Write a pattern then read it back."""
    from sovereign_agent.tools.behavior_tools import WriteBehaviorPatternTool, ReadBehaviorPatternsTool

    store_path = tmp_path / "behavior-patterns.ndjson"

    with patch("sovereign_agent.tools.behavior_tools._store_path", return_value=store_path):
        write_tool = WriteBehaviorPatternTool()
        wr = await write_tool.execute(
            write_tool.Args(
                name="patient-complex-tasks",
                description=(
                    "When Kevin brings a multi-step complex task, the best shape is to "
                    "plan first, issue parallel tool calls, and summarize cleanly."
                ),
                action_shape="plan → parallel calls → clean summary",
                trigger_channels_any=["work", "code"],
                tags=["complex", "planning"],
            ),
            trace_id="t1",
        )
        assert wr.ok, wr.error
        assert "pattern_id" in wr.metadata

        read_tool = ReadBehaviorPatternsTool()
        rr = await read_tool.execute(read_tool.Args(), trace_id="t2")

    assert rr.ok
    assert rr.metadata["count"] == 1
    assert "patient-complex-tasks" in rr.output
    assert "plan →" in rr.output


@pytest.mark.asyncio
async def test_read_keyword_filter(tmp_path):
    """Context filter returns only matching patterns."""
    from sovereign_agent.tools.behavior_tools import WriteBehaviorPatternTool, ReadBehaviorPatternsTool

    store_path = tmp_path / "behavior-patterns.ndjson"

    with patch("sovereign_agent.tools.behavior_tools._store_path", return_value=store_path):
        write_tool = WriteBehaviorPatternTool()
        await write_tool.execute(
            write_tool.Args(
                name="gentle-late-night",
                description="When Kevin messages late, be gentler and more brief.",
                action_shape="brief + warm",
            ),
            trace_id="t1",
        )
        await write_tool.execute(
            write_tool.Args(
                name="deep-code-review",
                description="When Kevin asks for code review, be thorough.",
                action_shape="thorough analysis",
            ),
            trace_id="t2",
        )

        read_tool = ReadBehaviorPatternsTool()
        r_all = await read_tool.execute(read_tool.Args(), trace_id="t3")
        r_late = await read_tool.execute(read_tool.Args(context="late"), trace_id="t4")
        r_code = await read_tool.execute(read_tool.Args(context="code"), trace_id="t5")

    assert r_all.metadata["count"] == 2
    assert r_late.metadata["count"] == 1
    assert "gentle-late-night" in r_late.output
    assert r_code.metadata["count"] == 1
    assert "deep-code-review" in r_code.output


@pytest.mark.asyncio
async def test_write_requires_name_and_description(tmp_path):
    """write_behavior_pattern fails if name or description is empty."""
    from sovereign_agent.tools.behavior_tools import WriteBehaviorPatternTool

    store_path = tmp_path / "behavior-patterns.ndjson"

    with patch("sovereign_agent.tools.behavior_tools._store_path", return_value=store_path):
        tool = WriteBehaviorPatternTool()
        r1 = await tool.execute(
            tool.Args(name="", description="something"),
            trace_id="t1",
        )
        r2 = await tool.execute(
            tool.Args(name="something", description=""),
            trace_id="t2",
        )

    assert not r1.ok
    assert not r2.ok
