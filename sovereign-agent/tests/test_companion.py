"""
test_companion.py — Tests for M40 (Companion Doctrine + Presence tools).
"""
from __future__ import annotations

import json
import pytest
from unittest.mock import patch, MagicMock


# ── Tool registration tests ───────────────────────────────────────────────────


def test_companion_tools_registered():
    import sovereign_agent.tools  # noqa: F401
    from sovereign_agent.authority import _TIER_REGISTRY
    assert "presence_note" in _TIER_REGISTRY
    assert "value_report" in _TIER_REGISTRY
    assert "relationship_history" in _TIER_REGISTRY
    assert _TIER_REGISTRY["presence_note"].tier == 1
    assert _TIER_REGISTRY["value_report"].tier == 0
    assert _TIER_REGISTRY["relationship_history"].tier == 0


def test_companion_tools_have_failure_modes():
    from sovereign_agent.tools.companion_tools import (
        PresenceNoteTool, ValueReportTool, RelationshipHistoryTool,
    )
    for cls in (PresenceNoteTool, ValueReportTool, RelationshipHistoryTool):
        assert cls.failure_modes, f"{cls.name} missing failure_modes"


# ── presence_note tests ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_presence_note_executes():
    from sovereign_agent.tools.companion_tools import PresenceNoteTool
    tool = PresenceNoteTool()
    with patch("sovereign_agent.tools.companion_tools._write_presence_atom", return_value="atom-pn-1"):
        result = await tool.execute(
            tool.Args(observation="Kevin is deep in a complex refactor — energy is focused.", tone="warm"),
            trace_id="t1",
        )
    assert result.ok
    assert result.output["atom_id"] == "atom-pn-1"
    assert "observation" in result.output


@pytest.mark.asyncio
async def test_presence_note_rejects_invalid_tone():
    from sovereign_agent.tools.companion_tools import PresenceNoteTool
    tool = PresenceNoteTool()
    result = await tool.execute(
        tool.Args(observation="test", tone="robotic"),
        trace_id="t1",
    )
    assert not result.ok
    assert "invalid tone" in result.error


@pytest.mark.asyncio
async def test_presence_note_with_context_tag():
    from sovereign_agent.tools.companion_tools import PresenceNoteTool
    tool = PresenceNoteTool()
    with patch("sovereign_agent.tools.companion_tools._write_presence_atom", return_value="atom-pn-2"):
        result = await tool.execute(
            tool.Args(
                observation="Session started strong — all tests passing.",
                tone="direct",
                context_tag="session-start",
            ),
            trace_id="t1",
        )
    assert result.ok
    assert result.output["context_tag"] == "session-start"


# ── value_report tests ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_value_report_returns_structure():
    from sovereign_agent.tools.companion_tools import ValueReportTool
    tool = ValueReportTool()
    with patch("sovereign_agent.tools.companion_tools._load_recent_events_for_report", return_value=[]):
        result = await tool.execute(tool.Args(), trace_id="t1")
    assert result.ok
    output = result.output
    assert "accomplished" in output
    assert "value_shown" in output
    assert "seeds" in output
    assert output["overall_grade"] in {"A", "B", "C", "D"}
    assert "summary" in output


@pytest.mark.asyncio
async def test_value_report_with_commit_events():
    from sovereign_agent.tools.companion_tools import ValueReportTool
    tool = ValueReportTool()
    mock_events = [
        {"flag": "commit-d", "payload": {"message": "add M37 interjection system"}},
        {"flag": "commit-d", "payload": {"message": "add M38 confidence crown"}},
        {"flag": "lesson-d", "payload": {"lesson": "always patch idempotently"}},
        {"flag": "presence-note-d", "payload": {}},
    ]
    with patch("sovereign_agent.tools.companion_tools._load_recent_events_for_report", return_value=mock_events):
        result = await tool.execute(tool.Args(), trace_id="t1")
    assert result.ok
    output = result.output
    assert len(output["accomplished"]) >= 3
    assert output["overall_grade"] in {"A", "B", "C"}


def test_build_value_report_grade_scales():
    from sovereign_agent.tools.companion_tools import _build_value_report
    # Many high-signal events → A
    events = [{"flag": "commit-d", "payload": {}} for _ in range(10)]
    report = _build_value_report(events, None)
    assert report["overall_grade"] in {"A", "B"}

    # No events → D
    report_empty = _build_value_report([], None)
    assert report_empty["overall_grade"] == "D"


# ── relationship_history tests ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_relationship_history_no_notes():
    from sovereign_agent.tools.companion_tools import RelationshipHistoryTool
    tool = RelationshipHistoryTool()
    with patch("sovereign_agent.tools.companion_tools._load_presence_notes", return_value=[]):
        result = await tool.execute(tool.Args(), trace_id="t1")
    assert result.ok
    assert result.output["count"] == 0
    assert "No presence notes" in result.output["message"]


@pytest.mark.asyncio
async def test_relationship_history_returns_sorted():
    from sovereign_agent.tools.companion_tools import RelationshipHistoryTool
    tool = RelationshipHistoryTool()
    mock_notes = [
        {"atom_id": "n1", "observation": "Kevin was focused", "tone": "warm", "created_at": "2026-06-19T10:00:00Z"},
        {"atom_id": "n2", "observation": "Good energy today", "tone": "warm", "created_at": "2026-06-18T10:00:00Z"},
    ]
    with patch("sovereign_agent.tools.companion_tools._load_presence_notes", return_value=mock_notes):
        result = await tool.execute(tool.Args(limit=5), trace_id="t1")
    assert result.ok
    assert result.output["count"] == 2
    assert result.output["notes"][0]["atom_id"] == "n1"


@pytest.mark.asyncio
async def test_relationship_history_tone_filter():
    from sovereign_agent.tools.companion_tools import RelationshipHistoryTool
    tool = RelationshipHistoryTool()
    mock_notes = [
        {"atom_id": "n1", "observation": "Hard truth", "tone": "honest", "created_at": "2026-06-19"},
    ]
    with patch("sovereign_agent.tools.companion_tools._load_presence_notes", return_value=mock_notes):
        result = await tool.execute(tool.Args(tone_filter="honest"), trace_id="t1")
    assert result.ok
    assert result.output["count"] == 1


# ── loop.py marker test ───────────────────────────────────────────────────────


def test_loop_has_companion_doctrine_marker():
    import pathlib
    p = pathlib.Path(__file__).resolve()
    for _ in range(8):
        c = p.parent / "src" / "sovereign_agent" / "loop.py"
        if c.exists():
            src = c.read_text()
            assert "companion-doctrine-d" in src, "companion-doctrine-d missing from loop.py"
            return
        p = p.parent
    pytest.skip("loop.py not found")
