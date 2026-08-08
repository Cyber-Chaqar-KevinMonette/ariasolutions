"""edit_file — Tier 1 (scoped writes).

Replaces an exact string match in a file. Like ``str_replace`` but
path-guarded under the agent's authority model. The match must be unique
within the file — ambiguous edits are rejected so the agent can't silently
corrupt the wrong instance.
"""
from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, Field

from ..modes import Mode
from ..pathguard import PathScopeViolation, check_write_path
from .base import Tool, ToolResult


class _Args(BaseModel):
    path: str = Field(description="Target file (BUSY: must be under sandbox)")
    old_str: str = Field(description="Exact string to find. Must be unique in file.")
    new_str: str = Field(default="", description="Replacement (empty string deletes)")


class EditFileTool(Tool[_Args]):
    name = "edit_file"
    tier = 1
    description = (
        "Replace an exact string in a file. The old string must appear EXACTLY "
        "once — ambiguous edits are refused. Atomic (writes via .tmp + rename). "
        "FAILURE MODES: file not found; old_str not found; old_str ambiguous "
        "(multiple matches); path-scope violation; permission denied."
    )
    failure_modes = (
        "file_not_found",
        "old_str_not_found",
        "old_str_ambiguous",
        "path_scope_violation",
        "permission_denied",
    )
    Args = _Args

    def __init__(self, mode: Mode | None = None) -> None:
        self._mode = mode or Mode.ONESHOT

    async def execute(self, args: _Args, *, trace_id: str) -> ToolResult:  # noqa: ARG002
        try:
            target = Path(check_write_path(args.path, self._mode))
        except PathScopeViolation as e:
            return ToolResult(ok=False, error=str(e))

        if not target.exists():
            return ToolResult(ok=False, error=f"file not found: {target}")

        try:
            content = target.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return ToolResult(ok=False, error="file is not valid UTF-8")
        except PermissionError as e:
            return ToolResult(ok=False, error=f"permission denied: {e}")

        count = content.count(args.old_str)
        if count == 0:
            return ToolResult(ok=False, error="old_str not found")
        if count > 1:
            return ToolResult(
                ok=False,
                error=f"old_str ambiguous: appears {count} times",
            )

        new_content = content.replace(args.old_str, args.new_str, 1)

        tmp = target.with_suffix(target.suffix + ".tmp")
        try:
            tmp.write_text(new_content, encoding="utf-8")
            os.replace(tmp, target)
        except OSError as e:
            tmp.unlink(missing_ok=True)
            return ToolResult(ok=False, error=f"write failed: {e}")

        return ToolResult(
            ok=True,
            output={
                "path": str(target),
                "bytes_before": len(content.encode("utf-8")),
                "bytes_after": len(new_content.encode("utf-8")),
            },
            metadata={"path": str(target)},
        )
