"""list_dir — Tier 0 (read-only)."""
from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from .base import Tool, ToolResult


class _Args(BaseModel):
    path: str = Field(description="Directory to list")
    max_entries: int = Field(default=500, ge=1, le=10_000)
    include_hidden: bool = Field(default=False, description="Show dotfiles")


class ListDirTool(Tool[_Args]):
    name = "list_dir"
    tier = 0
    description = (
        "List the contents of a directory. Returns names with type (file/dir) and "
        "size for files. FAILURE MODES: directory does not exist; path is a file "
        "(not a directory); permission denied; entry count exceeds max_entries "
        "(returns truncated with a warning)."
    )
    failure_modes = (
        "dir_not_found",
        "not_a_directory",
        "permission_denied",
        "truncated",
    )
    Args = _Args

    async def execute(self, args: _Args, *, trace_id: str) -> ToolResult:  # noqa: ARG002
        p = Path(args.path).expanduser()
        try:
            if not p.exists():
                return ToolResult(ok=False, error=f"directory not found: {p}")
            if not p.is_dir():
                return ToolResult(ok=False, error=f"not a directory: {p}")
            entries = []
            truncated = False
            for i, child in enumerate(sorted(p.iterdir(), key=lambda c: c.name)):
                if not args.include_hidden and child.name.startswith("."):
                    continue
                if i >= args.max_entries:
                    truncated = True
                    break
                try:
                    is_dir = child.is_dir()
                    size = None if is_dir else child.stat().st_size
                except OSError:
                    is_dir = False
                    size = None
                entries.append(
                    {
                        "name": child.name,
                        "type": "dir" if is_dir else "file",
                        "size_bytes": size,
                    }
                )
            return ToolResult(
                ok=True,
                output=entries,
                metadata={"path": str(p), "count": len(entries), "truncated": truncated},
            )
        except PermissionError as e:
            return ToolResult(ok=False, error=f"permission denied: {e}")
        except OSError as e:
            return ToolResult(ok=False, error=f"OS error: {e}")
