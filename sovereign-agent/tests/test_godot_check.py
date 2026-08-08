"""Tests for game-studio-capabilities-d — godot_check (Tier 1, split out
of the old combined godot_run so it's reachable during BUSY/Auto)."""
from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from sovereign_agent.game_projects import GameProject, game_workspace_dir, save
from sovereign_agent.tools.godot_check import GodotCheckTool


def test_tool_registered_at_tier_1():
    import sovereign_agent.tools  # noqa: F401
    from sovereign_agent.authority import _TIER_REGISTRY
    assert "godot_check" in _TIER_REGISTRY
    assert _TIER_REGISTRY["godot_check"].tier == 1


def test_reachable_under_busy_mode_ceiling():
    """The whole point of the split: Mode.BUSY's ceiling is 1, so this
    tool (unlike the old Tier-2 godot_run) must be visible there."""
    from sovereign_agent.authority import tools_available_in_mode
    from sovereign_agent.modes import Mode
    import sovereign_agent.tools  # noqa: F401
    names = {m.name for m in tools_available_in_mode(Mode.BUSY)}
    assert "godot_check" in names


@pytest.mark.asyncio
async def test_unknown_project_refused(tmp_path):
    tool = GodotCheckTool(data_dir=tmp_path)
    result = await tool.execute(tool.Args(project_slug="ghost"), trace_id="t1")
    assert not result.ok
    assert "unknown_project" in result.error


@pytest.mark.asyncio
async def test_check_invokes_godot_headless_check_only(tmp_path):
    save(GameProject(project_name="Alpha"), tmp_path)
    workspace = game_workspace_dir("alpha", sandbox_dir=tmp_path / "sandbox")
    fake = MagicMock(returncode=0, stdout="No errors.\n", stderr="")
    with patch("sovereign_agent.tools.godot_check.subprocess.run", return_value=fake) as m, \
         patch("sovereign_agent.tools.godot_check.game_workspace_dir", return_value=workspace), \
         patch("sovereign_agent.tools.godot_check.check_write_path", side_effect=lambda p, mode: p):
        tool = GodotCheckTool(data_dir=tmp_path)
        result = await tool.execute(tool.Args(project_slug="alpha"), trace_id="t1")
    assert result.ok
    argv = m.call_args.args[0]
    assert "--headless" in argv and "--check-only" in argv
    # scaffold-verify-d (2026-08-02): confirmed LIVE against the real
    # installed Godot binary that --check-only alone hangs until timeout
    # -- --quit is required to actually terminate the process.
    assert "--quit" in argv


@pytest.mark.asyncio
async def test_nonzero_exit_reported(tmp_path):
    save(GameProject(project_name="Alpha"), tmp_path)
    workspace = game_workspace_dir("alpha", sandbox_dir=tmp_path / "sandbox")
    fake = MagicMock(returncode=1, stdout="", stderr="Parse Error: broken.gd")
    with patch("sovereign_agent.tools.godot_check.subprocess.run", return_value=fake), \
         patch("sovereign_agent.tools.godot_check.game_workspace_dir", return_value=workspace), \
         patch("sovereign_agent.tools.godot_check.check_write_path", side_effect=lambda p, mode: p):
        tool = GodotCheckTool(data_dir=tmp_path)
        result = await tool.execute(tool.Args(project_slug="alpha"), trace_id="t1")
    assert not result.ok
    assert "godot_exited_nonzero" in result.error


@pytest.mark.asyncio
async def test_script_error_in_stderr_reported_despite_zero_exit(tmp_path):
    """Real bug, found live 2026-08-03: `--check-only --quit` exits 0 even
    when Godot logged a genuine GDScript parse error to stderr — confirmed
    against an actual broken script on the real installed Godot binary.
    returncode alone is not a reliable success signal."""
    save(GameProject(project_name="Alpha"), tmp_path)
    workspace = game_workspace_dir("alpha", sandbox_dir=tmp_path / "sandbox")
    fake = MagicMock(
        returncode=0,
        stdout="Godot Engine v4.7.stable\n",
        stderr='SCRIPT ERROR: Parse Error: Unexpected "?" in source.\n'
               '          at: GDScript::reload (res://fire.gd:25)\n'
               'ERROR: Failed to load script "res://fire.gd" with error "Parse error".\n',
    )
    with patch("sovereign_agent.tools.godot_check.subprocess.run", return_value=fake), \
         patch("sovereign_agent.tools.godot_check.game_workspace_dir", return_value=workspace), \
         patch("sovereign_agent.tools.godot_check.check_write_path", side_effect=lambda p, mode: p):
        tool = GodotCheckTool(data_dir=tmp_path)
        result = await tool.execute(tool.Args(project_slug="alpha"), trace_id="t1")
    assert not result.ok
    assert "script_error" in result.error


@pytest.mark.asyncio
async def test_warning_only_stderr_still_ok(tmp_path):
    """A WARNING: line is not a validation failure — only SCRIPT ERROR/
    ERROR: lines should flip ok to False."""
    save(GameProject(project_name="Alpha"), tmp_path)
    workspace = game_workspace_dir("alpha", sandbox_dir=tmp_path / "sandbox")
    fake = MagicMock(
        returncode=0,
        stdout="Godot Engine v4.7.stable\n",
        stderr="WARNING: some_node.gd:10: Deprecated method used.\n",
    )
    with patch("sovereign_agent.tools.godot_check.subprocess.run", return_value=fake), \
         patch("sovereign_agent.tools.godot_check.game_workspace_dir", return_value=workspace), \
         patch("sovereign_agent.tools.godot_check.check_write_path", side_effect=lambda p, mode: p):
        tool = GodotCheckTool(data_dir=tmp_path)
        result = await tool.execute(tool.Args(project_slug="alpha"), trace_id="t1")
    assert result.ok


@pytest.mark.asyncio
async def test_timeout_reported(tmp_path):
    save(GameProject(project_name="Alpha"), tmp_path)
    workspace = game_workspace_dir("alpha", sandbox_dir=tmp_path / "sandbox")
    with patch("sovereign_agent.tools.godot_check.subprocess.run",
              side_effect=subprocess.TimeoutExpired(cmd="godot", timeout=60)), \
         patch("sovereign_agent.tools.godot_check.game_workspace_dir", return_value=workspace), \
         patch("sovereign_agent.tools.godot_check.check_write_path", side_effect=lambda p, mode: p):
        tool = GodotCheckTool(data_dir=tmp_path)
        result = await tool.execute(tool.Args(project_slug="alpha"), trace_id="t1")
    assert not result.ok
    assert result.error == "timeout"
