"""read_file — Tier 0 (read-only)."""
from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from .base import Tool, ToolResult


class _Args(BaseModel):
    path: str = Field(description="Filesystem path to read")
    max_bytes: int = Field(
        default=200_000,
        ge=1,
        le=2_000_000,
        description="Refuse to read more than this many bytes",
    )


class ReadFileTool(Tool[_Args]):
    name = "read_file"
    tier = 0
    description = (
        "Read a UTF-8 text file from disk. Returns the file contents as a string. "
        "FAILURE MODES: file does not exist; file is binary (decode error); file "
        "exceeds max_bytes (refuses to read); permission denied."
    )
    failure_modes = (
        "file_not_found",
        "binary_file",
        "size_limit_exceeded",
        "permission_denied",
    )
    Args = _Args

    async def execute(self, args: _Args, *, trace_id: str) -> ToolResult:  # noqa: ARG002
        p = Path(args.path).expanduser()
        try:
            if not p.exists():
                return ToolResult(ok=False, error=f"file not found: {p}")
            if p.is_dir():
                return ToolResult(ok=False, error=f"path is a directory: {p}")
            size = p.stat().st_size
            if size > args.max_bytes:
                return ToolResult(
                    ok=False,
                    error=f"file size {size} exceeds max_bytes {args.max_bytes}",
                )
            try:
                content = p.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                return ToolResult(ok=False, error="file is not valid UTF-8")
            return ToolResult(
                ok=True,
                output=content,
                metadata={"size_bytes": size, "path": str(p)},
            )
        except PermissionError as e:
            return ToolResult(ok=False, error=f"permission denied: {e}")
        except OSError as e:
            return ToolResult(ok=False, error=f"OS error: {e}")
