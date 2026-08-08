"""test_auto_crown.py — Tests for M43 (Timed Autonomous Operation)."""
from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ── AutoCrownStore unit tests ─────────────────────────────────────────────────


def test_auto_session_dataclass():
    from sovereign_agent.auto_crown import AutoSession
    s = AutoSession(
        session_id="s-1",
        started_at="2026-06-20T00:00:00+00:00",
        duration_hours=1.0,
        expires_at=time.time() + 3600,
        trust_tier=1,
        reason="test",
        status="active",
    )
    assert s.session_id == "s-1"
    assert s.remaining_minutes() > 50
    d = s.as_dict()
    assert d["session_id"] == "s-1"
    assert d["status"] == "active"


def test_auto_session_is_expired():
    from sovereign_agent.auto_crown import AutoSession
    s = AutoSession(
        session_id="s-2",
        started_at="2026-06-20T00:00:00+00:00",
        duration_hours=1.0,
        expires_at=time.time() - 10,  # already expired
        trust_tier=1,
        reason="test",
        status="active",
    )
    assert s.remaining_seconds() == 0.0
    assert s.remaining_minutes() == 0.0


def test_auto_crown_store_start_and_status(tmp_path):
    from sovereign_agent.auto_crown import AutoCrownStore
    store = AutoCrownStore(data_dir=tmp_path)
    session = store.start(0.5, 1, "test run", "sess-abc")
    assert session.status == "active"
    assert session.trust_tier == 1
    assert session.duration_hours == 0.5
    assert session.session_id == "sess-abc"

    fetched = store.status()
    assert fetched is not None
    assert fetched.session_id == "sess-abc"


def test_auto_crown_is_expired_false(tmp_path):
    from sovereign_agent.auto_crown import AutoCrownStore
    store = AutoCrownStore(data_dir=tmp_path)
    store.start(1.0, 1, "test", "sess-1")
    assert store.is_expired() is False


def test_auto_crown_is_expired_true(tmp_path):
    from sovereign_agent.auto_crown import AutoCrownStore
    store = AutoCrownStore(data_dir=tmp_path)
    session = store.start(1.0, 1, "test", "sess-2")
    session.expires_at = time.time() - 1
    store._write(session)
    assert store.is_expired() is True


def test_auto_crown_trust_tier_enforcement(tmp_path):
    from sovereign_agent.auto_crown import AutoCrownStore
    store = AutoCrownStore(data_dir=tmp_path)
    # Default max_tier=1, so tier 2 should fail
    with pytest.raises(ValueError, match="exceeds max allowed"):
        store.start(1.0, 2, "too high", "sess-x")


def test_auto_crown_duration_enforcement(tmp_path):
    from sovereign_agent.auto_crown import AutoCrownStore
    store = AutoCrownStore(data_dir=tmp_path)
    # Tier 1 allows max 1hr; requesting 2hr should fail
    with pytest.raises(ValueError, match="exceeds max"):
        store.start(2.0, 1, "too long", "sess-y")


def test_auto_crown_cancel(tmp_path):
    from sovereign_agent.auto_crown import AutoCrownStore
    store = AutoCrownStore(data_dir=tmp_path)
    store.start(1.0, 1, "test", "sess-3")
    store.cancel("Kevin stopped early")
    s = store.status()
    assert s is not None
    assert s.status == "cancelled"
    assert "Kevin stopped early" in (s.work_done_summary or "")


def test_auto_crown_set_trust_tier(tmp_path):
    from sovereign_agent.auto_crown import AutoCrownStore
    store = AutoCrownStore(data_dir=tmp_path)
    store.set_trust_tier(2)
    assert store.get_max_trust_tier() == 2
    store.set_trust_tier(1)
    assert store.get_max_trust_tier() == 1


def test_auto_crown_set_trust_tier_invalid(tmp_path):
    from sovereign_agent.auto_crown import AutoCrownStore
    store = AutoCrownStore(data_dir=tmp_path)
    with pytest.raises(ValueError, match="Invalid trust tier"):
        store.set_trust_tier(5)


def test_auto_crown_expire(tmp_path):
    from sovereign_agent.auto_crown import AutoCrownStore
    store = AutoCrownStore(data_dir=tmp_path)
    store.start(1.0, 1, "test", "sess-4")
    store.expire()
    s = store.status()
    assert s is not None
    assert s.status == "expired"
    # is_expired returns False for expired (non-active) status
    assert store.is_expired() is False


def test_auto_crown_no_session(tmp_path):
    from sovereign_agent.auto_crown import AutoCrownStore
    store = AutoCrownStore(data_dir=tmp_path)
    assert store.status() is None
    assert store.is_expired() is False


# ── Tool registration tests ───────────────────────────────────────────────────


def test_auto_tools_registered():
    import sovereign_agent.tools  # noqa: F401
    from sovereign_agent.authority import _TIER_REGISTRY
    assert "auto_status" in _TIER_REGISTRY
    assert "start_auto" in _TIER_REGISTRY
    assert "stop_auto" in _TIER_REGISTRY
    assert "extend_auto" in _TIER_REGISTRY
    assert "set_auto_trust_tier" in _TIER_REGISTRY
    assert _TIER_REGISTRY["auto_status"].tier == 0
    assert _TIER_REGISTRY["start_auto"].tier == 2
    assert _TIER_REGISTRY["stop_auto"].tier == 1
    assert _TIER_REGISTRY["extend_auto"].tier == 3
    assert _TIER_REGISTRY["set_auto_trust_tier"].tier == 3


def test_auto_tools_have_failure_modes():
    from sovereign_agent.tools.auto_tools import (
        AutoStatusTool, StartAutoTool, StopAutoTool, ExtendAutoTool, SetAutoTrustTierTool,
    )
    for cls in (AutoStatusTool, StartAutoTool, StopAutoTool, ExtendAutoTool, SetAutoTrustTierTool):
        assert cls.failure_modes, f"{cls.name} missing failure_modes"


# ── auto_status tool tests ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_auto_status_no_session():
    from sovereign_agent.tools.auto_tools import AutoStatusTool
    from sovereign_agent.auto_crown import AutoCrownStore
    tool = AutoStatusTool()
    mock_store = MagicMock(spec=AutoCrownStore)
    mock_store.status.return_value = None
    mock_store.get_max_trust_tier.return_value = 1
    with patch("sovereign_agent.tools.auto_tools.get_auto_crown_store", return_value=mock_store):
        result = await tool.execute(tool.Args(), trace_id="t1")
    assert result.ok
    assert result.output["active"] is False
    assert result.output["max_trust_tier"] == 1


@pytest.mark.asyncio
async def test_auto_status_active_session():
    from sovereign_agent.tools.auto_tools import AutoStatusTool
    from sovereign_agent.auto_crown import AutoSession, AutoCrownStore
    tool = AutoStatusTool()
    mock_session = AutoSession(
        session_id="sess-x",
        started_at="2026-06-20T00:00:00+00:00",
        duration_hours=2.0,
        expires_at=time.time() + 7200,
        trust_tier=2,
        reason="working on backlog",
        status="active",
    )
    mock_store = MagicMock(spec=AutoCrownStore)
    mock_store.status.return_value = mock_session
    mock_store.get_max_trust_tier.return_value = 2
    with patch("sovereign_agent.tools.auto_tools.get_auto_crown_store", return_value=mock_store):
        result = await tool.execute(tool.Args(), trace_id="t1")
    assert result.ok
    assert result.output["active"] is True
    assert result.output["trust_tier"] == 2
    assert result.output["remaining_minutes"] > 100


# ── start_auto tool tests ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_start_auto_success():
    from sovereign_agent.tools.auto_tools import StartAutoTool
    from sovereign_agent.auto_crown import AutoSession, AutoCrownStore
    tool = StartAutoTool()
    mock_session = AutoSession(
        session_id="sess-new",
        started_at="2026-06-20T00:00:00+00:00",
        duration_hours=1.0,
        expires_at=time.time() + 3600,
        trust_tier=1,
        reason="drain backlog",
        status="active",
    )
    mock_store = MagicMock(spec=AutoCrownStore)
    mock_store.get_max_trust_tier.return_value = 1
    mock_store.start.return_value = mock_session
    with patch("sovereign_agent.tools.auto_tools.get_auto_crown_store", return_value=mock_store):
        result = await tool.execute(
            tool.Args(duration_hours=1.0, reason="drain backlog"),
            trace_id="t1",
        )
    assert result.ok
    assert "session_id" in result.output
    assert "message" in result.output
    assert "1.0h" in result.output["message"]


@pytest.mark.asyncio
async def test_start_auto_trust_tier_violated():
    from sovereign_agent.tools.auto_tools import StartAutoTool
    from sovereign_agent.auto_crown import AutoCrownStore
    tool = StartAutoTool()
    mock_store = MagicMock(spec=AutoCrownStore)
    mock_store.get_max_trust_tier.return_value = 1
    mock_store.start.side_effect = ValueError("Trust tier 2 exceeds max allowed (1).")
    with patch("sovereign_agent.tools.auto_tools.get_auto_crown_store", return_value=mock_store):
        result = await tool.execute(
            tool.Args(duration_hours=2.0, reason="too long"),
            trace_id="t1",
        )
    assert not result.ok
    assert "exceeds" in result.error


# ── stop_auto tool tests ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_stop_auto_success():
    from sovereign_agent.tools.auto_tools import StopAutoTool
    from sovereign_agent.auto_crown import AutoSession, AutoCrownStore
    tool = StopAutoTool()
    mock_session = AutoSession(
        session_id="sess-stop",
        started_at="2026-06-20T00:00:00+00:00",
        duration_hours=1.0,
        expires_at=time.time() + 3600,
        trust_tier=1,
        reason="test",
        status="active",
    )
    mock_store = MagicMock(spec=AutoCrownStore)
    mock_store.status.return_value = mock_session
    mock_store.cancel.return_value = None
    with patch("sovereign_agent.tools.auto_tools.get_auto_crown_store", return_value=mock_store):
        result = await tool.execute(
            tool.Args(reason="Kevin is back", work_done_summary="Finished 3 tasks."),
            trace_id="t1",
        )
    assert result.ok
    assert result.output["status"] == "cancelled"


@pytest.mark.asyncio
async def test_stop_auto_no_session():
    from sovereign_agent.tools.auto_tools import StopAutoTool
    from sovereign_agent.auto_crown import AutoCrownStore
    tool = StopAutoTool()
    mock_store = MagicMock(spec=AutoCrownStore)
    mock_store.status.return_value = None
    with patch("sovereign_agent.tools.auto_tools.get_auto_crown_store", return_value=mock_store):
        result = await tool.execute(tool.Args(reason="no session"), trace_id="t1")
    assert not result.ok
    assert "No active" in result.error


# ── loop.py marker test ───────────────────────────────────────────────────────


def test_loop_has_auto_crown_markers():
    import pathlib
    p = pathlib.Path(__file__).resolve()
    for _ in range(8):
        c = p.parent / "src" / "sovereign_agent" / "loop.py"
        if c.exists():
            src = c.read_text()
            assert "auto-crown-d" in src, "auto-crown-d missing from loop.py"
            assert "auto-crown-expiry-d" in src, "auto-crown-expiry-d missing from loop.py"
            return
        p = p.parent
    pytest.skip("loop.py not found")
