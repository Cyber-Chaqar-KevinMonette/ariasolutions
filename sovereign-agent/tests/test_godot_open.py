"""Tests for game-studio-open-d — godot_open: verify-before-act GUI launch."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from sovereign_agent.game_projects import GameProject, save
from sovereign_agent.tools.godot_open import GodotOpenTool, godot_gui_pids


def test_tool_registered():
    import sovereign_agent.tools  # noqa: F401
    from sovereign_agent.authority import _TIER_REGISTRY
    assert "godot_open" in _TIER_REGISTRY
    assert _TIER_REGISTRY["godot_open"].tier == 1


# ── godot_gui_pids() — the verify-before-act logic itself ─────────────────

def _pgrep_result(stdout: str, returncode: int = 0) -> MagicMock:
    return MagicMock(returncode=returncode, stdout=stdout)


def test_no_processes_found():
    with patch("sovereign_agent.tools.godot_open.subprocess.run",
              return_value=_pgrep_result("", returncode=1)):
        assert godot_gui_pids() == []


def test_headless_invocation_is_excluded():
    """godot_run.py's own check/export calls must NOT count as 'the GUI is
    open' -- this is the exact false-positive this tool was built to avoid."""
    with patch("sovereign_agent.tools.godot_open.subprocess.run",
              return_value=_pgrep_result(
                  "12345 flatpak run org.godotengine.Godot --headless --check-only --path /x\n"
              )), \
         patch("sovereign_agent.tools.godot_open.Path.exists", return_value=True):
        assert godot_gui_pids() == []


def test_real_gui_process_is_detected():
    with patch("sovereign_agent.tools.godot_open.subprocess.run",
              return_value=_pgrep_result(
                  "12345 flatpak run org.godotengine.Godot --path /home/x/games/alpha\n"
              )), \
         patch("sovereign_agent.tools.godot_open.Path.exists", return_value=True):
        assert godot_gui_pids() == [12345]


def test_stale_pid_that_already_exited_is_excluded():
    """Observed directly while building this: pgrep can return a PID that
    has already exited by the time you act on it. /proc/<pid> is
    re-checked at decision time, not trusted from pgrep alone."""
    with patch("sovereign_agent.tools.godot_open.subprocess.run",
              return_value=_pgrep_result(
                  "99999 flatpak run org.godotengine.Godot --path /x\n"
              )), \
         patch("sovereign_agent.tools.godot_open.Path.exists", return_value=False):
        assert godot_gui_pids() == []


def test_bwrap_wrapped_real_process_shapes_are_detected():
    """The real bug, reproduced live 2026-08-02: flatpak runs Godot under
    bubblewrap, and NONE of the real processes' cmdlines contain the old
    search string "org.godotengine.Godot" at all — confirmed against this
    machine's actual running Godot (4 processes: two `bwrap --args ...`
    wrappers, a `/bin/sh /app/bin/godot` shim, and the real
    `/app/bin/godot-bin` engine). godot_gui_pids() had never once
    detected a real running GUI before this fix."""
    stdout = (
        "502114 bwrap --args 77 -- godot -e --path /home/x/games/ember-keep\n"
        "502126 bwrap --args 77 -- godot -e --path /home/x/games/ember-keep\n"
        "502127 /bin/sh /app/bin/godot -e --path /home/x/games/ember-keep\n"
        "502158 /app/bin/godot-bin -e --path /home/x/games/ember-keep\n"
    )
    with patch("sovereign_agent.tools.godot_open.subprocess.run",
              return_value=_pgrep_result(stdout)), \
         patch("sovereign_agent.tools.godot_open.Path.exists", return_value=True):
        assert godot_gui_pids() == [502114, 502126, 502127, 502158]


def test_unrelated_process_mentioning_godot_without_path_is_excluded():
    """Searching "godot" alone (needed for the bwrap fix above) is broad
    enough to self-match unrelated noise — e.g. a shell wrapper whose own
    command text happens to mention "godot" (observed live testing this
    exact fix). Requiring --path (which every one of OUR OWN launches,
    GUI and headless alike, always carries) is the real, specific signal
    that excludes this."""
    stdout = (
        '77777 /bin/bash -c \'echo "checking godot version" && some_other_cmd\'\n'
    )
    with patch("sovereign_agent.tools.godot_open.subprocess.run",
              return_value=_pgrep_result(stdout)), \
         patch("sovereign_agent.tools.godot_open.Path.exists", return_value=True):
        assert godot_gui_pids() == []


def test_pgrep_not_found_degrades_to_empty():
    with patch("sovereign_agent.tools.godot_open.subprocess.run",
              side_effect=FileNotFoundError()):
        assert godot_gui_pids() == []


# ── the tool itself ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_unknown_project_refused(tmp_path):
    tool = GodotOpenTool(data_dir=tmp_path)
    result = await tool.execute(tool.Args(project_slug="ghost"), trace_id="t1")
    assert not result.ok
    assert "unknown_project" in result.error


@pytest.mark.asyncio
async def test_already_running_does_not_launch_a_duplicate(tmp_path):
    save(GameProject(project_name="Alpha"), tmp_path)
    tool = GodotOpenTool(data_dir=tmp_path)
    with patch("sovereign_agent.tools.godot_open.godot_gui_pids", return_value=[555]), \
         patch("sovereign_agent.tools.godot_open.subprocess.Popen") as popen:
        result = await tool.execute(tool.Args(project_slug="alpha"), trace_id="t1")
    popen.assert_not_called()
    assert result.ok
    assert result.output["already_running"] is True
    assert result.output["pids"] == [555]


@pytest.mark.asyncio
async def test_launches_when_nothing_running(tmp_path):
    save(GameProject(project_name="Alpha"), tmp_path)
    tool = GodotOpenTool(data_dir=tmp_path)
    fake_proc = MagicMock(pid=4242)
    with patch("sovereign_agent.tools.godot_open.godot_gui_pids", return_value=[]), \
         patch("sovereign_agent.tools.godot_open.subprocess.Popen", return_value=fake_proc) as popen:
        result = await tool.execute(tool.Args(project_slug="alpha"), trace_id="t1")
    assert result.ok
    assert result.output["already_running"] is False
    assert result.output["launched_pid"] == 4242
    argv = popen.call_args.args[0]
    assert "--headless" not in argv  # a real GUI launch, not a headless one
    assert "flatpak" in argv[0]
    assert "-e" in argv  # editor UI, not "run the project" (DEBUG play window)


@pytest.mark.asyncio
async def test_launch_is_non_blocking_no_wait_called(tmp_path):
    """Popen, not run() -- this must return immediately, not block until
    the editor window closes."""
    save(GameProject(project_name="Alpha"), tmp_path)
    tool = GodotOpenTool(data_dir=tmp_path)
    fake_proc = MagicMock(pid=1)
    with patch("sovereign_agent.tools.godot_open.godot_gui_pids", return_value=[]), \
         patch("sovereign_agent.tools.godot_open.subprocess.Popen", return_value=fake_proc):
        result = await tool.execute(tool.Args(project_slug="alpha"), trace_id="t1")
    assert result.ok
    fake_proc.wait.assert_not_called()


@pytest.mark.asyncio
async def test_flatpak_not_found_reported(tmp_path):
    save(GameProject(project_name="Alpha"), tmp_path)
    tool = GodotOpenTool(data_dir=tmp_path)
    with patch("sovereign_agent.tools.godot_open.godot_gui_pids", return_value=[]), \
         patch("sovereign_agent.tools.godot_open.subprocess.Popen", side_effect=FileNotFoundError()):
        result = await tool.execute(tool.Args(project_slug="alpha"), trace_id="t1")
    assert not result.ok
    assert "godot_not_found" in result.error
