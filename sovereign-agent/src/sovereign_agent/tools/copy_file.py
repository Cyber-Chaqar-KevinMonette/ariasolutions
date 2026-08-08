"""copy_file — Tier 1 (scoped writes).

Source can be any readable path; destination is path-guarded just like
``write_file``. Useful for staging research artifacts into the sandbox so
they can be referenced by atoms.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from pydantic import BaseModel, Field

from ..modes import Mode
from ..pathguard import PathScopeViolation, check_write_path
from .base import Tool, ToolResult


class _Args(BaseModel):
    source: str = Field(description="Source file (can be anywhere readable)")
    dest: str = Field(description="Destination (BUSY: must be under sandbox)")
    overwrite: bool = Field(default=False)


class CopyFileTool(Tool[_Args]):
    name = "copy_file"
    tier = 1
    description = (
        "Copy a file from source to dest. Source may be anywhere readable. "
        "Dest must resolve under sandbox in BUSY mode. "
        "FAILURE MODES: source not found; dest exists with overwrite=False; "
        "path-scope violation; permission denied; same source and dest."
    )
    failure_modes = (
        "source_not_found",
        "dest_exists",
        "path_scope_violation",
        "permission_denied",
        "same_path",
    )
    Args = _Args

    def __init__(self, mode: Mode | None = None) -> None:
        self._mode = mode or Mode.ONESHOT

    async def execute(self, args: _Args, *, trace_id: str) -> ToolResult:  # noqa: ARG002
        src = Path(args.source).expanduser().resolve()
        if not src.exists():
            return ToolResult(ok=False, error=f"source not found: {src}")
        if not src.is_file():
            return ToolResult(ok=False, error=f"source not a file: {src}")

        try:
            dest = Path(check_write_path(args.dest, self._mode))
        except PathScopeViolation as e:
            return ToolResult(ok=False, error=str(e))

        if src == dest:
            return ToolResult(ok=False, error="source and dest are the same path")
        if dest.exists() and not args.overwrite:
            return ToolResult(ok=False, error=f"dest exists and overwrite=False: {dest}")

        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
        except PermissionError as e:
            return ToolResult(ok=False, error=f"permission denied: {e}")
        except OSError as e:
            return ToolResult(ok=False, error=f"OS error: {e}")

        return ToolResult(
            ok=True,
            output={"source": str(src), "dest": str(dest), "size_bytes": dest.stat().st_size},
            metadata={"path": str(dest)},
        )
