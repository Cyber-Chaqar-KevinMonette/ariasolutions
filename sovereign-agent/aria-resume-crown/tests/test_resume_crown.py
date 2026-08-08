"""
test_resume_crown.py — Tests for M42 (Deep Resume + Pre-Action Checkpoints).
"""
from __future__ import annotations

import json
import pytest
from unittest.mock import patch, MagicMock


# ── CheckpointStore unit tests ────────────────────────────────────────────────


def test_checkpoint_store_write_pre_creates_pending():
    from sovereign_agent.checkpoint import CheckpointStore, ActionCheckpoint
    store = CheckpointStore()
    with patch("sovereign_agent.checkpoint._write_checkpoint_atom") as mock_write:
        ckpt = store.write_pre(
            tool_name="run_command",
            args={"cmd": ["git", "push"]},
            tier=2,
            session_id="sess-abc",
        )
    mock_write.assert_called_once()
    assert ckpt.status == "pending"
    assert ckpt.tool_name == "run_command"
    assert ckpt.tier == 2
    assert ckpt.session_id == "sess-abc"
    assert ckpt.checkpoint_id


def test_checkpoint_store_resolve():
    from sovereign_agent.checkpoint import CheckpointStore
    store = CheckpointStore()
    with patch("sovereign_agent.checkpoint._write_checkpoint_atom"):
        ckpt = store.write_pre("edit_file", {"path": "/tmp/f"}, 2, "sess-1")
    with patch("sovereign_agent.checkpoint._update_checkpoint_status") as mock_update:
        store.resolve(ckpt.checkpoint_id)
    mock_update.assert_called_once_with(ckpt.checkpoint_id, "resolved", mock_update.call_args[0][2], None)


def test_checkpoint_store_abandon():
    from sovereign_agent.checkpoint import CheckpointStore
    store = CheckpointStore()
    with patch("sovereign_agent.checkpoint._write_checkpoint_atom"):
        ckpt = store.write_pre("run_shell", {}, 2, "sess-2")
    with patch("sovereign_agent.checkpoint._update_checkpoint_status") as mock_update:
        store.abandon(ckpt.checkpoint_id, "Kevin confirmed: skip")
    mock_update.assert_called_once_with(ckpt.checkpoint_id, "abandoned", None, "Kevin confirmed: skip")


def test_action_checkpoint_as_dict():
    from sovereign_agent.checkpoint import ActionCheckpoint
    ckpt = ActionCheckpoint(
        checkpoint_id="ckpt-1",
        session_id="sess-x",
        tool_name="git_commit",
        args_summary='{"message": "test"}',
        pre_state_hash="abc123",
        tier=2,
        created_at="2026-06-19T00:00:00Z",
    )
    d = ckpt.as_dict()
    assert d["checkpoint_id"] == "ckpt-1"
    assert d["status"] == "pending"
    assert d["tool_name"] == "git_commit"


def test_hash_args_deterministic():
    from sovereign_agent.checkpoint import _hash_args
    args = {"cmd": ["git", "push"], "path": "/home/k"}
    h1 = _hash_args(args)
    h2 = _hash_args(args)
    assert h1 == h2
    assert len(h1) == 16


# ── Tool registration tests ───────────────────────────────────────────────────


def test_resume_tools_registered():
    import sovereign_agent.tools  # noqa: F401
    from sovereign_agent.authority import _TIER_REGISTRY
    assert "session_resume_audit" in _TIER_REGISTRY
    assert "read_checkpoints" in _TIER_REGISTRY
    assert "abandon_checkpoint" in _TIER_REGISTRY
    assert _TIER_REGISTRY["session_resume_audit"].tier == 0
    assert _TIER_REGISTRY["read_checkpoints"].tier == 0
    assert _TIER_REGISTRY["abandon_checkpoint"].tier == 1


def test_resume_tools_have_failure_modes():
    from sovereign_agent.tools.resume_tools import (
        SessionResumeAuditTool, ReadCheckpointsTool, AbandonCheckpointTool,
    )
    for cls in (SessionResumeAuditTool, ReadCheckpointsTool, AbandonCheckpointTool):
        assert cls.failure_modes, f"{cls.name} missing failure_modes"


# ── session_resume_audit tests ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_session_resume_audit_clean_start():
    from sovereign_agent.tools.resume_tools import SessionResumeAuditTool
    from sovereign_agent.checkpoint import CheckpointStore
    tool = SessionResumeAuditTool()
    mock_store = MagicMock(spec=CheckpointStore)
    mock_store.all_pending.return_value = []
    with patch("sovereign_agent.tools.resume_tools.get_checkpoint_store", return_value=mock_store):
        result = await tool.execute(tool.Args(), trace_id="t1")
    assert result.ok
    assert result.output["has_incomplete_actions"] is False
    assert result.output["count"] == 0
    assert "clean" in result.output["message"]


@pytest.mark.asyncio
async def test_session_resume_audit_with_pending():
    from sovereign_agent.tools.resume_tools import SessionResumeAuditTool
    from sovereign_agent.checkpoint import ActionCheckpoint, CheckpointStore
    tool = SessionResumeAuditTool()
    mock_ckpt = ActionCheckpoint(
        checkpoint_id="ckpt-x",
        session_id="prev-sess",
        tool_name="git_push",
        args_summary='{"remote": "origin"}',
        pre_state_hash="abc",
        tier=2,
        created_at="2026-06-18T23:00:00Z",
    )
    mock_store = MagicMock(spec=CheckpointStore)
    mock_store.all_pending.return_value = [mock_ckpt]
    with patch("sovereign_agent.tools.resume_tools.get_checkpoint_store", return_value=mock_store):
        result = await tool.execute(tool.Args(), trace_id="t1")
    assert result.ok
    assert result.output["has_incomplete_actions"] is True
    assert result.output["count"] == 1
    assert "ATTENTION" in result.output["message"]


# ── read_checkpoints tests ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_read_checkpoints_pending():
    from sovereign_agent.tools.resume_tools import ReadCheckpointsTool
    from sovereign_agent.checkpoint import CheckpointStore
    tool = ReadCheckpointsTool()
    mock_store = MagicMock(spec=CheckpointStore)
    mock_store.all_pending.return_value = []
    with patch("sovereign_agent.tools.resume_tools.get_checkpoint_store", return_value=mock_store):
        result = await tool.execute(tool.Args(status="pending"), trace_id="t1")
    assert result.ok
    assert result.output["count"] == 0


# ── abandon_checkpoint tests ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_abandon_checkpoint_executes():
    from sovereign_agent.tools.resume_tools import AbandonCheckpointTool
    from sovereign_agent.checkpoint import CheckpointStore
    tool = AbandonCheckpointTool()
    mock_store = MagicMock(spec=CheckpointStore)
    mock_store.abandon.return_value = None
    with patch("sovereign_agent.tools.resume_tools.get_checkpoint_store", return_value=mock_store):
        result = await tool.execute(
            tool.Args(checkpoint_id="ckpt-123", reason="Kevin confirmed: already done manually"),
            trace_id="t1",
        )
    assert result.ok
    assert result.output["status"] == "abandoned"
    assert result.output["checkpoint_id"] == "ckpt-123"
    mock_store.abandon.assert_called_once_with("ckpt-123", "Kevin confirmed: already done manually")


# ── loop.py marker test ───────────────────────────────────────────────────────


def test_loop_has_resume_crown_marker():
    import pathlib
    p = pathlib.Path(__file__).resolve()
    for _ in range(8):
        c = p.parent / "src" / "sovereign_agent" / "loop.py"
        if c.exists():
            src = c.read_text()
            assert "resume-crown-doctrine-d" in src, "resume-crown-doctrine-d missing from loop.py"
            return
        p = p.parent
    pytest.skip("loop.py not found")
