"""
test_mode_master.py — Tests for M35 (mode tools + dynamic mode transitions).
"""
from __future__ import annotations

import json
import time
import pytest
from pathlib import Path
from unittest.mock import patch


# ── Tool registration tests ───────────────────────────────────────────────────


def test_mode_tools_registered():
    import sovereign_agent.tools  # noqa: F401
    from sovereign_agent.authority import _TIER_REGISTRY
    assert "mode_status" in _TIER_REGISTRY
    assert "switch_mode" in _TIER_REGISTRY
    assert "request_mode_upgrade" in _TIER_REGISTRY
    assert _TIER_REGISTRY["mode_status"].tier == 0
    assert _TIER_REGISTRY["switch_mode"].tier == 1
    assert _TIER_REGISTRY["request_mode_upgrade"].tier == 2


def test_mode_tools_have_failure_modes():
    from sovereign_agent.tools.mode_tools import ModeStatusTool, SwitchModeTool, RequestModeUpgradeTool
    for cls in (ModeStatusTool, SwitchModeTool, RequestModeUpgradeTool):
        assert cls.failure_modes, f"{cls.name} missing failure_modes"


# ── mode_status tests ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_mode_status_returns_structure():
    from sovereign_agent.tools.mode_tools import ModeStatusTool
    tool = ModeStatusTool()
    result = await tool.execute(tool.Args(), trace_id="t1")
    assert result.ok
    assert "current_mode" in result.output
    assert "tier_ceiling" in result.output
    assert "mode_history" in result.output
    assert "allowed_auto_transitions" in result.output


# ── switch_mode tests ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_switch_mode_busy_to_timed(tmp_path):
    from sovereign_agent.tools.mode_tools import SwitchModeTool, _mode_history
    tool = SwitchModeTool()
    initial_len = len(_mode_history)

    with patch("sovereign_agent.tools.mode_tools._get_effective_mode", return_value="busy"), \
         patch("sovereign_agent.config.SETTINGS") as mock_settings:
        mock_settings.paths.data_dir = tmp_path
        result = await tool.execute(
            tool.Args(target_mode="timed", reason="switching to responsive mode"),
            trace_id="t1",
        )

    assert result.ok
    assert result.output["to_mode"] == "timed"
    override_file = tmp_path / "mode_override.json"
    assert override_file.exists()
    data = json.loads(override_file.read_text())
    assert data["target_mode"] == "timed"
    assert data["expires_at"] > time.time()
    assert len(_mode_history) > initial_len


@pytest.mark.asyncio
async def test_switch_mode_blocks_non_auto_transition(tmp_path):
    from sovereign_agent.tools.mode_tools import SwitchModeTool
    tool = SwitchModeTool()

    with patch("sovereign_agent.tools.mode_tools._get_effective_mode", return_value="oneshot"), \
         patch("sovereign_agent.config.SETTINGS") as mock_settings:
        mock_settings.paths.data_dir = tmp_path
        result = await tool.execute(
            tool.Args(target_mode="busy", reason="trying to switch from oneshot"),
            trace_id="t1",
        )

    assert not result.ok
    assert "not allowed" in result.error


@pytest.mark.asyncio
async def test_switch_mode_timed_to_busy(tmp_path):
    from sovereign_agent.tools.mode_tools import SwitchModeTool
    tool = SwitchModeTool()

    with patch("sovereign_agent.tools.mode_tools._get_effective_mode", return_value="timed"), \
         patch("sovereign_agent.config.SETTINGS") as mock_settings:
        mock_settings.paths.data_dir = tmp_path
        result = await tool.execute(
            tool.Args(target_mode="busy", reason="background drain mode"),
            trace_id="t1",
        )

    assert result.ok
    assert result.output["to_mode"] == "busy"


# ── request_mode_upgrade tests ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_request_mode_upgrade_valid_mode(tmp_path):
    from sovereign_agent.tools.mode_tools import RequestModeUpgradeTool
    tool = RequestModeUpgradeTool()

    with patch("sovereign_agent.tools.mode_tools._get_effective_mode", return_value="busy"), \
         patch("sovereign_agent.config.SETTINGS") as mock_settings:
        mock_settings.paths.data_dir = tmp_path
        result = await tool.execute(
            tool.Args(target_mode="oneshot", reason="need tier 3 for git push", duration_seconds=1800),
            trace_id="t1",
        )

    assert result.ok
    assert result.output["to_mode"] == "oneshot"
    data = json.loads((tmp_path / "mode_override.json").read_text())
    assert data["requested_by"] == "operator"


@pytest.mark.asyncio
async def test_request_mode_upgrade_rejects_invalid_mode(tmp_path):
    from sovereign_agent.tools.mode_tools import RequestModeUpgradeTool
    tool = RequestModeUpgradeTool()

    with patch("sovereign_agent.config.SETTINGS") as mock_settings:
        mock_settings.paths.data_dir = tmp_path
        result = await tool.execute(
            tool.Args(target_mode="turbo_god", reason="test", duration_seconds=60),
            trace_id="t1",
        )

    assert not result.ok
    assert "invalid mode" in result.error


# ── _read_override helper tests ───────────────────────────────────────────────


def test_read_override_returns_none_when_missing(tmp_path):
    from sovereign_agent.tools.mode_tools import _read_override
    assert _read_override(tmp_path) is None


def test_read_override_returns_valid_override(tmp_path):
    from sovereign_agent.tools.mode_tools import _read_override, _write_override
    override = {
        "target_mode": "timed",
        "reason": "test",
        "requested_by": "aria",
        "expires_at": time.time() + 3600,
        "created_at": time.time(),
    }
    _write_override(tmp_path, override)
    result = _read_override(tmp_path)
    assert result is not None
    assert result["target_mode"] == "timed"


def test_read_override_returns_none_when_expired(tmp_path):
    from sovereign_agent.tools.mode_tools import _read_override, _write_override
    override = {
        "target_mode": "timed",
        "reason": "test",
        "requested_by": "aria",
        "expires_at": time.time() - 1,  # already expired
        "created_at": time.time() - 100,
    }
    _write_override(tmp_path, override)
    assert _read_override(tmp_path) is None


# ── loop.py marker tests ──────────────────────────────────────────────────────


def test_loop_has_mode_master_markers():
    import pathlib
    p = pathlib.Path(__file__).resolve()
    for _ in range(8):
        c = p.parent / "src" / "sovereign_agent" / "loop.py"
        if c.exists():
            src = c.read_text()
            assert "mode-master-check-d" in src, "mode-master-check-d missing"
            assert "mode-awareness-d" in src, "mode-awareness-d missing"
            return
        p = p.parent
    pytest.skip("loop.py not found")
