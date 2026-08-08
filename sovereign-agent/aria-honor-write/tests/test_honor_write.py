"""
test_honor_write.py — Tests for write_honor_note tool (M21).
"""
from __future__ import annotations
import json
import pytest
from pathlib import Path
from unittest.mock import patch


def test_tool_registered():
    import sovereign_agent.tools  # noqa: F401
    from sovereign_agent.authority import _TIER_REGISTRY
    assert "write_honor_note" in _TIER_REGISTRY
    assert _TIER_REGISTRY["write_honor_note"].tier == 1


def test_failure_modes():
    from sovereign_agent.tools.honor_write import WriteHonorNoteTool
    assert WriteHonorNoteTool.failure_modes


@pytest.mark.asyncio
async def test_write_aria_to_kevin(tmp_path):
    """aria->kevin note is appended to ledger."""
    from sovereign_agent.tools.honor_write import WriteHonorNoteTool

    ledger_path = tmp_path / "honor" / "ledger.jsonl"

    with patch("sovereign_agent.tools.honor_write._ledger_path", return_value=ledger_path):
        tool = WriteHonorNoteTool()
        result = await tool.execute(
            tool.Args(
                direction="aria->kevin",
                text="Kevin stayed through four iterations to get it right.",
                tags=["persistence"],
            ),
            trace_id="t1",
        )

    assert result.ok, result.error
    assert "♥" in result.output or "Honor note written" in result.output
    assert "aria->kevin" in result.output
    assert result.metadata["direction"] == "aria->kevin"

    # Verify ledger
    assert ledger_path.exists()
    lines = [l for l in ledger_path.read_text().splitlines() if l.strip()]
    assert len(lines) == 1
    note = json.loads(lines[0])
    assert note["direction"] == "aria->kevin"
    assert "four iterations" in note["text"]
    assert "persistence" in note["tags"]


@pytest.mark.asyncio
async def test_write_aria_to_self(tmp_path):
    """aria->self note records Aria's own near-miss."""
    from sovereign_agent.tools.honor_write import WriteHonorNoteTool

    ledger_path = tmp_path / "honor" / "ledger.jsonl"

    with patch("sovereign_agent.tools.honor_write._ledger_path", return_value=ledger_path):
        tool = WriteHonorNoteTool()
        result = await tool.execute(
            tool.Args(
                direction="aria->self",
                text="I caught myself about to propose a Tier 3 action without approval.",
                tags=["almost-missed", "safety"],
            ),
            trace_id="t1",
        )

    assert result.ok, result.error

    lines = [l for l in ledger_path.read_text().splitlines() if l.strip()]
    note = json.loads(lines[0])
    assert note["direction"] == "aria->self"


@pytest.mark.asyncio
async def test_write_aria_to_third_requires_recipient(tmp_path):
    """aria->third without recipient fails."""
    from sovereign_agent.tools.honor_write import WriteHonorNoteTool

    ledger_path = tmp_path / "honor" / "ledger.jsonl"

    with patch("sovereign_agent.tools.honor_write._ledger_path", return_value=ledger_path):
        tool = WriteHonorNoteTool()
        result = await tool.execute(
            tool.Args(
                direction="aria->third",
                text="Brilliant library design.",
            ),
            trace_id="t1",
        )

    assert not result.ok
    assert "recipient" in result.error


@pytest.mark.asyncio
async def test_write_aria_to_third_with_recipient(tmp_path):
    """aria->third with recipient succeeds."""
    from sovereign_agent.tools.honor_write import WriteHonorNoteTool

    ledger_path = tmp_path / "honor" / "ledger.jsonl"

    with patch("sovereign_agent.tools.honor_write._ledger_path", return_value=ledger_path):
        tool = WriteHonorNoteTool()
        result = await tool.execute(
            tool.Args(
                direction="aria->third",
                text="The Textual library made the cockpit beautiful.",
                recipient="Textual / Will McGugan",
                tags=["design"],
            ),
            trace_id="t1",
        )

    assert result.ok, result.error

    lines = [l for l in ledger_path.read_text().splitlines() if l.strip()]
    note = json.loads(lines[0])
    assert note["recipient"] == "Textual / Will McGugan"


@pytest.mark.asyncio
async def test_invalid_direction(tmp_path):
    """Invalid direction returns ok=False."""
    from sovereign_agent.tools.honor_write import WriteHonorNoteTool

    ledger_path = tmp_path / "honor" / "ledger.jsonl"

    with patch("sovereign_agent.tools.honor_write._ledger_path", return_value=ledger_path):
        tool = WriteHonorNoteTool()
        result = await tool.execute(
            tool.Args(direction="me->you", text="hello"),
            trace_id="t1",
        )

    assert not result.ok
    assert "invalid direction" in result.error


@pytest.mark.asyncio
async def test_empty_text_rejected(tmp_path):
    """Empty text is rejected."""
    from sovereign_agent.tools.honor_write import WriteHonorNoteTool

    ledger_path = tmp_path / "honor" / "ledger.jsonl"

    with patch("sovereign_agent.tools.honor_write._ledger_path", return_value=ledger_path):
        tool = WriteHonorNoteTool()
        result = await tool.execute(
            tool.Args(direction="aria->kevin", text="   "),
            trace_id="t1",
        )

    assert not result.ok


@pytest.mark.asyncio
async def test_multiple_notes_accumulate(tmp_path):
    """Multiple notes all land in the ledger (append-only)."""
    from sovereign_agent.tools.honor_write import WriteHonorNoteTool

    ledger_path = tmp_path / "honor" / "ledger.jsonl"

    with patch("sovereign_agent.tools.honor_write._ledger_path", return_value=ledger_path):
        tool = WriteHonorNoteTool()
        for i in range(3):
            await tool.execute(
                tool.Args(direction="aria->kevin", text=f"Note #{i + 1}"),
                trace_id=f"t{i}",
            )

    lines = [l for l in ledger_path.read_text().splitlines() if l.strip()]
    assert len(lines) == 3
