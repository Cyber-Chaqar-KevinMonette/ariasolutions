"""godot_check — Tier 1. Headless Godot syntax/scene validation.

Split out of the original combined godot_run.py (2026-07-20) after Kevin
asked directly: "make sure in auto mode she is capable of all of those
tasks" (building, among others). Real finding: `Mode.BUSY`'s tool tier
ceiling is hardcoded to 1 (modes.py, "the load-bearing safety design") —
during an actual /auto session she runs under BUSY, so a Tier-2 tool is
simply not in her visible toolset at all, regardless of trust tier. The
original combined godot_run (Tier 2, to match git_write.py's "shells out
via subprocess" precedent) made headless validation unreachable during
the exact multi-hour building sessions it was built for.

check-only validation performs ZERO writes — no file on disk is created
or modified, only godot's own internal parse/load is exercised. That
doesn't match Tier 2's own definition ("scoped destructive"); it matches
Tier 1 ("scoped writes (sandbox or memory subsystem)") more generously
than it even needs, kept there rather than Tier 0 only because it still
spawns a real subprocess against the sandboxed workspace. This is a
deliberate, explained tier assignment, not a casual downgrade — see
CLAUDE.md's authority-gate rule.

`export` (which DOES write a build artifact — a more consequential,
rarer action) stays at Tier 2 in the sibling godot_export.py tool,
unchanged.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from pydantic import BaseModel, Field

from ..game_projects import game_workspace_dir, load_by_slug
from ..modes import Mode
from ..pathguard import PathScopeViolation, check_write_path
from .base import Tool, ToolResult

_SAFE_TIMEOUT = 60  # headless check is quick — a full engine parse, not a build
_GODOT_BIN = "flatpak"
_GODOT_ARGS_PREFIX = ["run", "org.godotengine.Godot"]


class _Args(BaseModel):
    project_slug: str = Field(description="Slug of a registered game project")


class GodotCheckTool(Tool[_Args]):
    name = "godot_check"
    tier = 1
    description = (
        "Headlessly validate a registered game project's scenes/scripts "
        "(godot --headless --check-only). Zero writes — pure validation. "
        "Cheap enough to call after every meaningful change, not just "
        "before a milestone. Available in every mode, including an "
        "unattended /auto session. "
        "FAILURE MODES: unknown_project; godot_not_found; timeout; "
        "path_scope_violation; godot_exited_nonzero; script_error."
    )
    failure_modes = (
        "unknown_project",
        "godot_not_found",
        "timeout",
        "path_scope_violation",
        "godot_exited_nonzero",
        "script_error",
    )
    Args = _Args

    def __init__(self, mode: Mode | None = None, data_dir: Path | None = None) -> None:
        self._mode = mode or Mode.ONESHOT
        self._data_dir = data_dir

    async def execute(self, args: _Args, *, trace_id: str) -> ToolResult:  # noqa: ARG002
        data_dir = self._data_dir
        if data_dir is None:
            from ..config import SETTINGS
            data_dir = SETTINGS.paths.data_dir

        if load_by_slug(args.project_slug, data_dir) is None:
            return ToolResult(ok=False, error=f"unknown_project: {args.project_slug!r}")

        workspace = game_workspace_dir(args.project_slug, sandbox_dir=None)
        try:
            workspace = check_write_path(workspace, self._mode)
        except PathScopeViolation as e:
            return ToolResult(ok=False, error=f"path_scope_violation: {e}")

        # scaffold-verify-d (Kevin, 2026-08-02): confirmed LIVE against the
        # real installed Godot 4.7 binary (this tool's own tests fully mock
        # subprocess.run, so this had never actually been exercised) --
        # --check-only alone does NOT quit the engine afterward; without
        # --quit the process hangs until the timeout, every time, and
        # every real call would silently report "timeout" instead of
        # actually validating anything.
        argv = [_GODOT_BIN, *_GODOT_ARGS_PREFIX,
                "--headless", "--check-only", "--quit", "--path", str(workspace)]
        try:
            r = subprocess.run(
                argv, capture_output=True, text=True, errors="replace",
                timeout=_SAFE_TIMEOUT, stdin=subprocess.DEVNULL,
            )
        except subprocess.TimeoutExpired:
            return ToolResult(ok=False, error="timeout")
        except FileNotFoundError:
            return ToolResult(ok=False, error="godot_not_found: flatpak/godot not in PATH")
        except Exception as exc:  # noqa: BLE001
            return ToolResult(ok=False, error=f"subprocess error: {exc!r}")

        output = (r.stdout or "").strip()
        errtext = (r.stderr or "").strip()
        if r.returncode != 0:
            return ToolResult(
                ok=False,
                error=f"godot_exited_nonzero: {r.returncode}: {errtext or output}",
            )

        # real bug, found live 2026-08-03: --check-only --quit exits 0 even
        # when Godot logged a real script parse error to stderr (confirmed
        # against a genuine GDScript syntax error) — returncode alone is not
        # a reliable success signal. Godot's own log-level prefixes for a
        # real problem are "SCRIPT ERROR:" and lines starting "ERROR:";
        # "WARNING:" is left alone, that's not a validation failure.
        if "SCRIPT ERROR" in errtext or any(
            line.strip().startswith("ERROR:") for line in errtext.splitlines()
        ):
            return ToolResult(ok=False, error=f"script_error: {errtext}")

        return ToolResult(ok=True, output={"stdout": output, "stderr": errtext})


__all__ = ["GodotCheckTool"]
