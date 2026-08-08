"""godot_open — Tier 1. Open the real Godot GUI editor herself, checking
first whether one is already running.

Kevin (2026-07-20): "We want her to open it herself, and verify if it is
open before she tries to open it. She should always try to verify before
taking actions." Companion to godot_run.py's headless check/export — this
is the one GUI-facing action: launching the actual interactive Godot
editor window (non-headless) pointed at a project's workspace, so Kevin
can watch her work live in the FileSystem dock as she writes files
(exactly the "live, literal watching" path named in the Game Studio
design). Launch is via subprocess.Popen, detached and non-blocking — a
GUI editor is meant to stay open indefinitely; this tool call returns as
soon as it launches, it does not wait for the window to close.

Verify-before-act, done carefully, not naively: matching on the flatpak
app ID alone is NOT enough. Two real false-positive traps were found
while building this, both worth naming so they don't get silently
reintroduced:

  1. godot_run.py's OWN headless check/export calls launch the exact same
     flatpak app ID with `--headless` — a naive `pgrep -f
     org.godotengine.Godot` would see a quick validate call in progress
     and wrongly conclude "the GUI is open." Filtered out explicitly:
     any matched process whose full command line contains `--headless`
     is not a GUI instance.
  2. pgrep can return PIDs of processes that have ALREADY EXITED by the
     time you act on them (observed directly while building this: two
     PIDs came back from a plain `pgrep -f`, and both were already gone
     one `ps` call later) — a real TOCTOU race, not a hypothetical one.
     Every candidate PID is re-checked against /proc/<pid> at the moment
     of the decision, not just at the moment pgrep ran.

Note this is a DIFFERENT trap than the shell-wrapper self-match seen
elsewhere this session (an interactive shell embedding its own search
string in its own command line) — this module's checks run through a
direct subprocess.run() call with an argv list, never a shell string, so
that specific failure mode doesn't apply here. The two traps above are
real regardless.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from pydantic import BaseModel, Field

from ..game_projects import game_workspace_dir, load_by_slug
from .base import Tool, ToolResult

_PGREP_TIMEOUT = 5


def godot_gui_pids() -> list[int]:
    """PIDs of any currently-running, non-headless Godot GUI instance.
    Empty list means no GUI is open right now.

    Found live 2026-08-02: the pattern used to be "org.godotengine.Godot"
    (the flatpak app ID) — but flatpak runs the app under bubblewrap
    (bwrap), and NONE of the real processes' cmdlines contain that app-ID
    string at all (confirmed on this machine: `bwrap --args 77 -- godot
    -e --path ...`, `/bin/sh /app/bin/godot ...`, `/app/bin/godot-bin
    ...`). This meant godot_gui_pids() had NEVER once actually detected a
    running GUI instance — the "refuse to launch a duplicate" guard was
    silently dead code. Fixed to match "godot" instead, but "godot" alone
    is broad enough to self-match unrelated shell noise (e.g. this exact
    docstring, or a command mentioning the word) — every one of our own
    launches (GUI and headless alike) always passes --path <workspace>,
    so requiring BOTH substrings is the real, specific signal."""
    try:
        r = subprocess.run(
            ["pgrep", "-af", "godot"],
            capture_output=True, text=True, timeout=_PGREP_TIMEOUT,
            stdin=subprocess.DEVNULL,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    if r.returncode != 0:
        return []
    pids: list[int] = []
    for line in r.stdout.splitlines():
        parts = line.split(maxsplit=1)
        if len(parts) != 2:
            continue
        pid_str, cmdline = parts
        if not pid_str.isdigit():
            continue
        if "--path" not in cmdline:
            continue  # not one of our own launches — avoid broad "godot" false-positives
        if "--headless" in cmdline:
            continue  # a godot_run check/export call, not a GUI instance
        pid = int(pid_str)
        if Path(f"/proc/{pid}").exists():  # still alive right now, not a stale match
            pids.append(pid)
    return pids


class _Args(BaseModel):
    project_slug: str = Field(description="Slug of a registered game project")


class GodotOpenTool(Tool[_Args]):
    name = "godot_open"
    tier = 1
    description = (
        "Open the real Godot GUI editor for a registered game project, so "
        "Kevin can watch you work live. ALWAYS checks whether a Godot GUI "
        "is already running first (a headless godot_run check/export "
        "in-progress does NOT count as 'open') — refuses to launch a "
        "duplicate window and reports the existing one instead. "
        "Non-blocking: returns immediately once the editor starts. "
        "FAILURE MODES: unknown_project; already_running (not a failure — "
        "ok=True, reports the existing window rather than launching); "
        "godot_not_found; launch_failed."
    )
    failure_modes = (
        "unknown_project",
        "godot_not_found",
        "launch_failed",
    )
    Args = _Args

    def __init__(self, data_dir: Path | None = None) -> None:
        self._data_dir = data_dir

    async def execute(self, args: _Args, *, trace_id: str) -> ToolResult:  # noqa: ARG002
        data_dir = self._data_dir
        if data_dir is None:
            from ..config import SETTINGS
            data_dir = SETTINGS.paths.data_dir

        if load_by_slug(args.project_slug, data_dir) is None:
            return ToolResult(ok=False, error=f"unknown_project: {args.project_slug!r}")

        running = godot_gui_pids()
        if running:
            return ToolResult(ok=True, output={
                "already_running": True,
                "pids": running,
                "message": "Godot GUI is already open — not launching a duplicate.",
            })

        workspace = game_workspace_dir(args.project_slug, sandbox_dir=None)
        # -e/--editor: without it Godot RUNS the project's main scene instead
        # of opening the editor UI (confirmed live: launched straight into
        # the "<name> (DEBUG)" play window, not the FileSystem-dock editor
        # Kevin needs to watch her work).
        argv = ["flatpak", "run", "org.godotengine.Godot", "-e", "--path", str(workspace)]
        try:
            proc = subprocess.Popen(
                argv,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL, start_new_session=True,
            )
        except FileNotFoundError:
            return ToolResult(ok=False, error="godot_not_found: flatpak not in PATH")
        except Exception as exc:  # noqa: BLE001
            return ToolResult(ok=False, error=f"launch_failed: {exc!r}")

        return ToolResult(ok=True, output={
            "already_running": False,
            "launched_pid": proc.pid,
            "message": f"Launched Godot GUI editor for {args.project_slug} (pid {proc.pid}).",
        })


__all__ = ["GodotOpenTool", "godot_gui_pids"]
