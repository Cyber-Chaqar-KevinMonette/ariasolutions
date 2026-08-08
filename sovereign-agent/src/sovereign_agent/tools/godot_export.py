"""godot_export — Tier 2. Headless Godot release export.

Split out of the original combined godot_run.py (2026-07-20) — see
godot_check.py's docstring for the full reasoning. `export` DOES write a
build artifact to disk (a more consequential, rarer action than
validation), so it stays at Tier 2, same shape/allowlist discipline as
git_write.py. This means it's NOT reachable during an unattended /auto
session (Mode.BUSY's tier ceiling is hardcoded to 1) — a deliberate,
narrower gap than the original all-or-nothing godot_run had: she can
validate constantly while building alone, and export/ship when Kevin is
present (an interactive mode) or explicitly widens this later.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from pydantic import BaseModel, Field

from ..game_projects import game_workspace_dir, load_by_slug
from ..modes import Mode
from ..pathguard import PathScopeViolation, check_write_path
from .base import Tool, ToolResult

# timeout-hardening-d (Kevin, 2026-07-21): "adaptable timeouts... and
# longer timeouts." This was a hardcoded 120s with no way to ask for
# more -- a real gap for a bigger project's export, which this file's OWN
# comment already admitted "can genuinely take a while." Now a default
# (same 120s, nothing gets slower by default) with an adjustable ceiling.
_DEFAULT_TIMEOUT = 120
_MAX_TIMEOUT = 900  # 15 min ceiling for a genuinely large project's export
_GODOT_BIN = "flatpak"
_GODOT_ARGS_PREFIX = ["run", "org.godotengine.Godot"]

_PRESET_NAME_RE = re.compile(r'name\s*=\s*"([^"]+)"')


def _known_presets(export_presets_cfg: Path) -> set[str]:
    if not export_presets_cfg.is_file():
        return set()
    try:
        text = export_presets_cfg.read_text(encoding="utf-8")
    except OSError:
        return set()
    return set(_PRESET_NAME_RE.findall(text))


class _Args(BaseModel):
    project_slug: str = Field(description="Slug of a registered game project")
    preset: str = Field(description="Must match a preset name already defined "
                                    "in the project's export_presets.cfg.")
    output_relative_path: str = Field(description="Output path relative to the "
                                                   "project workspace, e.g. 'builds/game.pck'.")
    timeout: int = Field(default=_DEFAULT_TIMEOUT, ge=10, le=_MAX_TIMEOUT,
                         description="Seconds to allow before giving up — "
                                     "raise this for a bigger project's export.")


class GodotExportTool(Tool[_Args]):
    name = "godot_export"
    tier = 2
    description = (
        "Run a headless Godot release export for a registered game "
        "project, using a preset already defined in the project's own "
        "export_presets.cfg — the preset name is validated, never "
        "freeform. Writes a build artifact to disk (a real, if scoped, "
        "write) — not reachable inside an unattended /auto session; use "
        "an interactive mode when Kevin is present, or godot_check for "
        "cheap validation during autonomous building. Args include an "
        "optional timeout (default 120s, up to 900s) — raise it for a "
        "genuinely large project rather than letting it time out. "
        "FAILURE MODES: unknown_project; godot_not_found; timeout; "
        "unknown_preset; missing_output_path; path_scope_violation; "
        "godot_exited_nonzero."
    )
    failure_modes = (
        "unknown_project",
        "godot_not_found",
        "timeout",
        "unknown_preset",
        "missing_output_path",
        "path_scope_violation",
        "godot_exited_nonzero",
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

        if not args.preset.strip():
            return ToolResult(ok=False, error="unknown_preset: preset is required")
        known = _known_presets(workspace / "export_presets.cfg")
        if args.preset not in known:
            return ToolResult(
                ok=False,
                error=f"unknown_preset: {args.preset!r} not in {sorted(known)}",
            )
        if not args.output_relative_path.strip():
            return ToolResult(ok=False, error="missing_output_path")
        try:
            output_path = check_write_path(
                workspace / args.output_relative_path, self._mode
            )
        except PathScopeViolation as e:
            return ToolResult(ok=False, error=f"path_scope_violation: {e}")
        output_path.parent.mkdir(parents=True, exist_ok=True)

        argv = [_GODOT_BIN, *_GODOT_ARGS_PREFIX,
                "--headless", "--path", str(workspace),
                "--export-release", args.preset, str(output_path)]
        try:
            r = subprocess.run(
                argv, capture_output=True, text=True, errors="replace",
                timeout=args.timeout, stdin=subprocess.DEVNULL,
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
        return ToolResult(ok=True, output={"stdout": output, "stderr": errtext})


__all__ = ["GodotExportTool"]
