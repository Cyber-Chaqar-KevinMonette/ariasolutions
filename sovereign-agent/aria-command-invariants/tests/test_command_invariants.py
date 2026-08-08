"""
test_command_invariants.py — tests for the command invariant registry.
"""
from __future__ import annotations

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch


def _mock_settings(tmp_path: Path) -> MagicMock:
    s = MagicMock()
    s.paths.data_dir = tmp_path
    return s


def test_tools_registered():
    import sovereign_agent.tools  # noqa
    from sovereign_agent.authority import _TIER_REGISTRY
    assert "list_command_invariants" in _TIER_REGISTRY
    assert "read_command_invariant" in _TIER_REGISTRY
    assert "write_command_note" in _TIER_REGISTRY
    assert _TIER_REGISTRY["list_command_invariants"].tier == 0
    assert _TIER_REGISTRY["read_command_invariant"].tier == 0
    assert _TIER_REGISTRY["write_command_note"].tier == 1


@pytest.mark.asyncio
async def test_list_empty(tmp_path):
    from sovereign_agent.tools.command_invariants import ListCommandInvariantsTool
    with patch("sovereign_agent.tools.command_invariants.SETTINGS", _mock_settings(tmp_path), create=True):
        tool = ListCommandInvariantsTool()
        result = await tool.execute(tool.Args(), trace_id="t1")
    assert result.ok
    assert result.metadata["count"] == 0
    assert "No invariant profiles" in result.output


@pytest.mark.asyncio
async def test_write_and_read_roundtrip(tmp_path):
    from sovereign_agent.tools.command_invariants import WriteCommandNoteTool, ReadCommandInvariantTool
    fake = _mock_settings(tmp_path)
    with patch("sovereign_agent.tools.command_invariants.SETTINGS", fake, create=True):
        # write
        write_tool = WriteCommandNoteTool()
        w = await write_tool.execute(
            write_tool.Args(command="sov-doctor", content="must check all sentinel health levels", section="invariants"),
            trace_id="t2w"
        )
        assert w.ok
        # read back
        read_tool = ReadCommandInvariantTool()
        r = await read_tool.execute(
            read_tool.Args(command="sov-doctor", section="invariants"),
            trace_id="t2r"
        )
    assert r.ok
    assert "must check all sentinel health levels" in r.output
    assert "sov-doctor" in r.output


@pytest.mark.asyncio
async def test_write_creates_directory(tmp_path):
    from sovereign_agent.tools.command_invariants import WriteCommandNoteTool
    fake = _mock_settings(tmp_path)
    with patch("sovereign_agent.tools.command_invariants.SETTINGS", fake, create=True):
        tool = WriteCommandNoteTool()
        result = await tool.execute(
            tool.Args(command="analyze-image", content="use focus=code for screenshots", section="notes"),
            trace_id="t3"
        )
    assert result.ok
    assert (tmp_path / "command-invariants" / "analyze-image" / "notes.md").exists()


@pytest.mark.asyncio
async def test_list_shows_written_profiles(tmp_path):
    from sovereign_agent.tools.command_invariants import WriteCommandNoteTool, ListCommandInvariantsTool
    fake = _mock_settings(tmp_path)
    with patch("sovereign_agent.tools.command_invariants.SETTINGS", fake, create=True):
        w = WriteCommandNoteTool()
        await w.execute(w.Args(command="generate-image", content="prefer flux-schnell for quality"), trace_id="t4w")
        l = ListCommandInvariantsTool()
        result = await l.execute(l.Args(), trace_id="t4l")
    assert result.ok
    assert "generate-image" in result.output
    assert result.metadata["count"] == 1


@pytest.mark.asyncio
async def test_read_missing_profile_gives_error(tmp_path):
    from sovereign_agent.tools.command_invariants import ReadCommandInvariantTool
    fake = _mock_settings(tmp_path)
    with patch("sovereign_agent.tools.command_invariants.SETTINGS", fake, create=True):
        tool = ReadCommandInvariantTool()
        result = await tool.execute(tool.Args(command="nonexistent-cmd"), trace_id="t5")
    assert not result.ok
    assert "no invariant profile" in result.error


@pytest.mark.asyncio
async def test_write_invalid_section(tmp_path):
    from sovereign_agent.tools.command_invariants import WriteCommandNoteTool
    fake = _mock_settings(tmp_path)
    with patch("sovereign_agent.tools.command_invariants.SETTINGS", fake, create=True):
        tool = WriteCommandNoteTool()
        result = await tool.execute(
            tool.Args(command="test", content="test", section="all"),
            trace_id="t6"
        )
    assert not result.ok


@pytest.mark.asyncio
async def test_multiple_sections(tmp_path):
    from sovereign_agent.tools.command_invariants import WriteCommandNoteTool, ReadCommandInvariantTool
    fake = _mock_settings(tmp_path)
    with patch("sovereign_agent.tools.command_invariants.SETTINGS", fake, create=True):
        w = WriteCommandNoteTool()
        await w.execute(w.Args(command="vessel-status", content="check VRAM free before heavy tools", section="invariants"), trace_id="a")
        await w.execute(w.Args(command="vessel-status", content="add GPU temp to output", section="improvements"), trace_id="b")
        r = ReadCommandInvariantTool()
        result = await r.execute(r.Args(command="vessel-status", section="all"), trace_id="c")
    assert result.ok
    assert "VRAM free" in result.output
    assert "GPU temp" in result.output
    assert "INVARIANTS" in result.output
    assert "IMPROVEMENTS" in result.output
