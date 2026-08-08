"""
test_session_memory.py — verify session memory improvements.
"""
from __future__ import annotations

import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch


def test_summary_budget_is_4000():
    """completed_summary_for_prompt default must be 4000 chars (raised from 2000)."""
    import inspect
    from sovereign_agent import agent_session
    src = inspect.getsource(agent_session.SessionState.completed_summary_for_prompt
                            if hasattr(agent_session.SessionState, "completed_summary_for_prompt")
                            else agent_session)
    # Check the function signature directly
    import sovereign_agent.agent_session as _as
    import inspect as _inspect
    sig = _inspect.signature(_as.SessionState.completed_summary_for_prompt)
    default = sig.parameters.get("max_chars", None)
    if default is not None:
        assert default.default == 4000, f"Expected 4000, got {default.default}"


def test_loop_system_prompt_mentions_read_session():
    """The loop system prompt must instruct Aria to call read_session on resume."""
    from sovereign_agent.loop import SYSTEM_PROMPT_TEMPLATE
    assert "read_session" in SYSTEM_PROMPT_TEMPLATE, (
        "read_session not in loop system prompt — run apply_session_memory.sh"
    )


def test_read_session_tool_registered():
    """ReadSessionTool must be in the authority tool registry after import."""
    import sovereign_agent.tools  # noqa: F401
    from sovereign_agent.authority import _TIER_REGISTRY
    assert "read_session" in _TIER_REGISTRY, "ReadSessionTool not registered"
    assert _TIER_REGISTRY["read_session"].tier == 0


@pytest.mark.asyncio
async def test_read_session_no_session_found(tmp_path):
    """When no sessions exist, tool returns a clear error."""
    from sovereign_agent.tools.session_review import ReadSessionTool

    fake_settings = MagicMock()
    fake_settings.paths.data_dir = tmp_path

    with patch("sovereign_agent.config.SETTINGS", fake_settings, create=True):
        tool = ReadSessionTool()
        result = await tool.execute(tool.Args(), trace_id="t1")

    assert not result.ok
    assert "no active session" in result.error or "not found" in result.error


@pytest.mark.asyncio
async def test_read_session_loads_and_formats(tmp_path):
    """ReadSessionTool reads a real session file and formats it correctly."""
    from sovereign_agent.tools.session_review import ReadSessionTool
    from sovereign_agent.agent_session import SessionState, Subtask, SessionStore

    # Create a minimal session file
    state = SessionState(
        session_id="test-session-123",
        goal="test reading session state",
        mode="oneshot",
        status="active",
    )
    # Add a mock subtask
    subtask = Subtask(
        id="sub-001",
        description="read the important file",
        status="done",
        result_summary="found 42 relevant lines",
    )
    state.subtasks = [subtask]

    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    session_file = sessions_dir / "test-session-123.json"
    import dataclasses
    session_file.write_text(json.dumps(dataclasses.asdict(state)))

    mock_store = MagicMock()
    mock_store.load.return_value = state

    fake_settings = MagicMock()
    fake_settings.paths.data_dir = tmp_path

    with (
        patch("sovereign_agent.agent_session.SessionStore", return_value=mock_store),
        patch("sovereign_agent.config.SETTINGS", fake_settings, create=True),
    ):
        tool = ReadSessionTool()
        result = await tool.execute(tool.Args(session_id="test-session-123"), trace_id="t2")

    assert result.ok
    assert "test-session-123" in result.output
    assert "read the important file" in result.output
    assert "found 42 relevant lines" in result.output
    assert result.metadata["done"] == 1


@pytest.mark.asyncio
async def test_read_session_filters_completed_when_requested(tmp_path):
    """include_completed=False hides done subtasks."""
    from sovereign_agent.tools.session_review import ReadSessionTool
    from sovereign_agent.agent_session import SessionState, Subtask

    state = SessionState(
        session_id="sess-filter",
        goal="test filter",
        mode="oneshot",
        status="active",
    )
    done_task = Subtask(id="d1", description="already done", status="done",
                        result_summary="completed earlier")
    pending_task = Subtask(id="p1", description="still to do", status="pending")
    state.subtasks = [done_task, pending_task]

    mock_store = MagicMock()
    mock_store.load.return_value = state

    fake_settings = MagicMock()
    fake_settings.paths.data_dir = tmp_path

    with (
        patch("sovereign_agent.agent_session.SessionStore", return_value=mock_store),
        patch("sovereign_agent.config.SETTINGS", fake_settings, create=True),
    ):
        tool = ReadSessionTool()
        result = await tool.execute(
            tool.Args(session_id="sess-filter", include_completed=False),
            trace_id="t3",
        )

    assert result.ok
    assert "already done" not in result.output
    assert "still to do" in result.output
