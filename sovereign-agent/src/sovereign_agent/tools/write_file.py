"""write_file — Tier 1 (scoped writes).

Architecture §6 invariant 6 + §7 matrix. In BUSY mode, ``path`` must resolve
to a descendant of ``$AGENT_HOME/sandbox`` (runtime check via ``pathguard``).
In ONESHOT/TIMED/UNTIL the bwrap layout is the second line of defense.
"""
from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, Field

from ..modes import Mode
from ..pathguard import PathScopeViolation, check_write_path
from .base import Tool, ToolResult


class _Args(BaseModel):
    path: str = Field(description="Destination path (BUSY: must be under sandbox)")
    content: str = Field(description="UTF-8 text to write")
    overwrite: bool = Field(
        default=False,
        description="If True, replace existing file. If False, refuse on collision.",
    )
    make_parents: bool = Field(
        default=True,
        description="Create parent directories if they don't exist",
    )


class WriteFileTool(Tool[_Args]):
    name = "write_file"
    tier = 1
    description = (
        "Write text content to a file. Atomic (writes to .tmp, then renames). "
        "Path must resolve under sandbox in BUSY mode. "
        "FAILURE MODES: path-scope violation; file exists and overwrite=False; "
        "permission denied; disk full; parent dir missing and make_parents=False."
    )
    failure_modes = (
        "path_scope_violation",
        "file_exists",
        "permission_denied",
        "disk_full",
        "parent_missing",
    )
    Args = _Args

    def __init__(self, mode: Mode | None = None) -> None:
        # Mode passed in by the loop's tool registry; defaults to ONESHOT for
        # standalone use (path guard is a no-op in non-BUSY).
        self._mode = mode or Mode.ONESHOT

    async def execute(self, args: _Args, *, trace_id: str) -> ToolResult:  # noqa: ARG002
        try:
            target = check_write_path(args.path, self._mode)
        except PathScopeViolation as e:
            return ToolResult(ok=False, error=str(e))

        target = Path(target)
        if target.exists() and not args.overwrite:
            return ToolResult(
                ok=False,
                error=f"file exists and overwrite=False: {target}",
            )
        if not target.parent.exists():
            if args.make_parents:
                target.parent.mkdir(parents=True, exist_ok=True)
            else:
                return ToolResult(ok=False, error=f"parent missing: {target.parent}")

        # Atomic write: tmp + rename
        tmp = target.with_suffix(target.suffix + ".tmp")
        try:
            tmp.write_text(args.content, encoding="utf-8")
            os.replace(tmp, target)
        except PermissionError as e:
            tmp.unlink(missing_ok=True)
            return ToolResult(ok=False, error=f"permission denied: {e}")
        except OSError as e:
            tmp.unlink(missing_ok=True)
            if "No space left" in str(e):
                return ToolResult(ok=False, error=f"disk full: {e}")
            return ToolResult(ok=False, error=f"OS error: {e}")

        return ToolResult(
            ok=True,
            output={"path": str(target), "bytes_written": len(args.content.encode("utf-8"))},
            metadata={"path": str(target)},
        )
