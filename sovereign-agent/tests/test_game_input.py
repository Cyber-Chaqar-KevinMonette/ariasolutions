"""Tests for game_input — synthetic mouse/keyboard via ydotool.
No real ydotoold needed — subprocess calls and the socket-path check are
mocked."""
from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest


def _proc(returncode=0, stdout="", stderr=""):
    return MagicMock(spec=subprocess.CompletedProcess, returncode=returncode, stdout=stdout, stderr=stderr)


def test_game_input_tool_registered():
    import sovereign_agent.tools  # noqa: F401
    from sovereign_agent.authority import _TIER_REGISTRY
    assert "game_input" in _TIER_REGISTRY
    assert _TIER_REGISTRY["game_input"].tier == 1


@pytest.mark.asyncio
async def test_ydotool_not_found():
    from sovereign_agent.tools.game_input import GameInputTool
    with patch("sovereign_agent.tools.game_input.shutil.which", return_value=None):
        tool = GameInputTool()
        result = await tool.execute(tool.Args(action="click"), trace_id="t1")
    assert not result.ok
    assert "ydotool_not_found" in result.error


@pytest.mark.asyncio
async def test_daemon_unreachable():
    from sovereign_agent.tools.game_input import GameInputTool
    with (
        patch("sovereign_agent.tools.game_input.shutil.which", return_value="/usr/bin/ydotool"),
        patch("sovereign_agent.tools.game_input._SOCKET_PATH") as mock_path,
    ):
        mock_path.exists.return_value = False
        tool = GameInputTool()
        result = await tool.execute(tool.Args(action="click"), trace_id="t2")
    assert not result.ok
    assert "daemon_unreachable" in result.error


@pytest.mark.asyncio
async def test_click_calls_ydotool_click():
    from sovereign_agent.tools.game_input import GameInputTool
    with (
        patch("sovereign_agent.tools.game_input.shutil.which", return_value="/usr/bin/ydotool"),
        patch("sovereign_agent.tools.game_input._SOCKET_PATH") as mock_path,
        patch("sovereign_agent.tools.game_input._run", return_value=_proc(0)) as m,
    ):
        mock_path.exists.return_value = True
        tool = GameInputTool()
        result = await tool.execute(tool.Args(action="click", button=1), trace_id="t3")
    assert result.ok
    m.assert_called_once_with(["ydotool", "click", "1"])


@pytest.mark.asyncio
async def test_click_at_homes_then_moves_then_clicks():
    """click_at must issue: home move, target move, click — in that order,
    and bail before clicking if either move fails."""
    from sovereign_agent.tools.game_input import GameInputTool
    calls = []

    def _fake_run(argv):
        calls.append(argv)
        return _proc(0)

    with (
        patch("sovereign_agent.tools.game_input.shutil.which", return_value="/usr/bin/ydotool"),
        patch("sovereign_agent.tools.game_input._SOCKET_PATH") as mock_path,
        patch("sovereign_agent.tools.game_input._run", side_effect=_fake_run),
    ):
        mock_path.exists.return_value = True
        tool = GameInputTool()
        result = await tool.execute(tool.Args(action="click_at", x=630, y=350), trace_id="t4")

    assert result.ok
    assert len(calls) == 3
    assert calls[0] == ["ydotool", "mousemove", "--", "-10000", "-10000"]
    assert calls[1] == ["ydotool", "mousemove", "630", "350"]
    assert calls[2] == ["ydotool", "click", "1"]


@pytest.mark.asyncio
async def test_click_at_bails_if_homing_move_fails():
    from sovereign_agent.tools.game_input import GameInputTool
    calls = []

    def _fake_run(argv):
        calls.append(argv)
        return _proc(returncode=1, stderr="uinput busy")

    with (
        patch("sovereign_agent.tools.game_input.shutil.which", return_value="/usr/bin/ydotool"),
        patch("sovereign_agent.tools.game_input._SOCKET_PATH") as mock_path,
        patch("sovereign_agent.tools.game_input._run", side_effect=_fake_run),
    ):
        mock_path.exists.return_value = True
        tool = GameInputTool()
        result = await tool.execute(tool.Args(action="click_at", x=630, y=350), trace_id="t5")

    assert not result.ok
    assert len(calls) == 1  # never got to the target move or the click
    assert "homing move failed" in result.error


@pytest.mark.asyncio
async def test_click_at_requires_x_and_y():
    from sovereign_agent.tools.game_input import GameInputTool
    with (
        patch("sovereign_agent.tools.game_input.shutil.which", return_value="/usr/bin/ydotool"),
        patch("sovereign_agent.tools.game_input._SOCKET_PATH") as mock_path,
    ):
        mock_path.exists.return_value = True
        tool = GameInputTool()
        result = await tool.execute(tool.Args(action="click_at"), trace_id="t6")
    assert not result.ok
    assert "missing_args" in result.error


@pytest.mark.asyncio
async def test_key_action():
    from sovereign_agent.tools.game_input import GameInputTool
    with (
        patch("sovereign_agent.tools.game_input.shutil.which", return_value="/usr/bin/ydotool"),
        patch("sovereign_agent.tools.game_input._SOCKET_PATH") as mock_path,
        patch("sovereign_agent.tools.game_input._run", return_value=_proc(0)) as m,
    ):
        mock_path.exists.return_value = True
        tool = GameInputTool()
        result = await tool.execute(tool.Args(action="key", keys="F5"), trace_id="t7")
    assert result.ok
    m.assert_called_once_with(["ydotool", "key", "F5"])


@pytest.mark.asyncio
async def test_move_relative_requires_dx_dy():
    from sovereign_agent.tools.game_input import GameInputTool
    with (
        patch("sovereign_agent.tools.game_input.shutil.which", return_value="/usr/bin/ydotool"),
        patch("sovereign_agent.tools.game_input._SOCKET_PATH") as mock_path,
    ):
        mock_path.exists.return_value = True
        tool = GameInputTool()
        result = await tool.execute(tool.Args(action="move_relative"), trace_id="t8")
    assert not result.ok
    assert "missing_args" in result.error


@pytest.mark.asyncio
async def test_subprocess_nonzero_exit_reported():
    from sovereign_agent.tools.game_input import GameInputTool
    with (
        patch("sovereign_agent.tools.game_input.shutil.which", return_value="/usr/bin/ydotool"),
        patch("sovereign_agent.tools.game_input._SOCKET_PATH") as mock_path,
        patch("sovereign_agent.tools.game_input._run", return_value=_proc(1, stderr="boom")),
    ):
        mock_path.exists.return_value = True
        tool = GameInputTool()
        result = await tool.execute(tool.Args(action="click"), trace_id="t9")
    assert not result.ok
    assert "boom" in result.error
