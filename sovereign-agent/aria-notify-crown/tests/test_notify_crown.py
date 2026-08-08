"""test_notify_crown.py — Tests for M51 (Notify Crown)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── _gdbus_available helper tests ─────────────────────────────────────────────


def test_gdbus_available_true():
    from sovereign_agent.tools.notify_tools import _gdbus_available
    mock_result = MagicMock()
    mock_result.returncode = 0
    with patch("subprocess.run", return_value=mock_result):
        assert _gdbus_available() is True


def test_gdbus_available_false_on_error():
    from sovereign_agent.tools.notify_tools import _gdbus_available
    with patch("subprocess.run", side_effect=FileNotFoundError("gdbus not found")):
        assert _gdbus_available() is False


def test_gdbus_available_false_on_nonzero():
    from sovereign_agent.tools.notify_tools import _gdbus_available
    mock_result = MagicMock()
    mock_result.returncode = 1
    with patch("subprocess.run", return_value=mock_result):
        assert _gdbus_available() is False


# ── _send_notification helper tests ──────────────────────────────────────────


def test_send_notification_success():
    from sovereign_agent.tools.notify_tools import _send_notification
    mock_result = MagicMock()
    mock_result.returncode = 0
    with patch("subprocess.run", return_value=mock_result) as mock_run:
        result = _send_notification("Title", "Body", "dialog-information", 5000)
    assert result is True
    call_args = mock_run.call_args[0][0]
    assert "gdbus" in call_args
    assert "Title" in call_args
    assert "Body" in call_args


def test_send_notification_fails_gracefully():
    from sovereign_agent.tools.notify_tools import _send_notification
    with patch("subprocess.run", side_effect=Exception("dbus error")):
        result = _send_notification("Title", "Body", "dialog-information", 5000)
    assert result is False


# ── notify tool tests ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_notify_returns_ok_on_success():
    from sovereign_agent.tools.notify_tools import NotifyTool
    tool = NotifyTool()
    with patch("asyncio.to_thread", new=AsyncMock(return_value=True)):
        result = await tool.execute(
            tool.Args(title="Task Complete", body="M49 tests passed", urgency="normal"),
            trace_id="t1",
        )
    assert result.ok
    assert result.output["title"] == "Task Complete"
    assert result.output["urgency"] == "normal"
    assert "Notification sent" in result.output["message"]


@pytest.mark.asyncio
async def test_notify_returns_error_when_dbus_fails():
    from sovereign_agent.tools.notify_tools import NotifyTool
    tool = NotifyTool()
    with patch("asyncio.to_thread", new=AsyncMock(return_value=False)):
        result = await tool.execute(
            tool.Args(title="Alert", body="Something happened"),
            trace_id="t1",
        )
    assert not result.ok
    assert "failed" in result.error.lower() or "not available" in result.error.lower()


@pytest.mark.asyncio
async def test_notify_critical_uses_warning_icon():
    from sovereign_agent.tools.notify_tools import NotifyTool
    tool = NotifyTool()
    with patch("asyncio.to_thread", new=AsyncMock(return_value=True)):
        result = await tool.execute(
            tool.Args(title="Critical Alert", urgency="critical"),
            trace_id="t1",
        )
    assert result.ok
    assert result.output["icon"] == "dialog-warning"
    assert result.output["timeout_ms"] == 0  # persistent


@pytest.mark.asyncio
async def test_notify_timeout_by_urgency():
    from sovereign_agent.tools.notify_tools import NotifyTool
    tool = NotifyTool()
    for urgency, expected_ms in [("low", 5000), ("normal", 10000), ("critical", 0)]:
        with patch("asyncio.to_thread", new=AsyncMock(return_value=True)):
            result = await tool.execute(
                tool.Args(title="Test", urgency=urgency),
                trace_id="t1",
            )
        assert result.ok
        assert result.output["timeout_ms"] == expected_ms, f"wrong timeout for {urgency}"


# ── notify_status tool tests ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_notify_status_available():
    from sovereign_agent.tools.notify_tools import NotifyStatusTool
    tool = NotifyStatusTool()
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "('cosmic-notifications', 'System76', '0.1.0', '1.2')\n"
    with patch("asyncio.to_thread", new=AsyncMock(return_value=mock_result)):
        result = await tool.execute(tool.Args(), trace_id="t1")
    assert result.ok
    assert result.output["available"] is True
    assert "gdbus" in result.output["backend"]


@pytest.mark.asyncio
async def test_notify_status_unavailable():
    from sovereign_agent.tools.notify_tools import NotifyStatusTool
    tool = NotifyStatusTool()
    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stdout = ""
    with patch("asyncio.to_thread", new=AsyncMock(return_value=mock_result)):
        result = await tool.execute(tool.Args(), trace_id="t1")
    assert result.ok
    assert result.output["available"] is False


# ── Tool registration tests ───────────────────────────────────────────────────


def test_notify_tools_registered():
    import sovereign_agent.tools  # noqa: F401
    from sovereign_agent.authority import _TIER_REGISTRY
    assert "notify" in _TIER_REGISTRY
    assert "notify_status" in _TIER_REGISTRY
    assert _TIER_REGISTRY["notify"].tier == 0
    assert _TIER_REGISTRY["notify_status"].tier == 0


def test_notify_tools_have_failure_modes():
    from sovereign_agent.tools.notify_tools import NotifyTool, NotifyStatusTool
    for cls in (NotifyTool, NotifyStatusTool):
        assert cls.failure_modes, f"{cls.name} missing failure_modes"


# ── loop marker test ──────────────────────────────────────────────────────────


def test_loop_has_notify_crown_marker():
    import pathlib
    p = pathlib.Path(__file__).resolve()
    for _ in range(8):
        c = p.parent / "src" / "sovereign_agent" / "loop.py"
        if c.exists():
            src = c.read_text()
            assert "notify-crown-d" in src, "notify-crown-d missing from loop.py"
            return
        p = p.parent
    pytest.skip("loop.py not found")
