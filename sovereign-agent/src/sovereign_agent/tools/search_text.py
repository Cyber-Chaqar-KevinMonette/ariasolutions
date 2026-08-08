"""search_text — Tier 0 (read-only). ripgrep-style text search across a directory."""
from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel, Field

from .base import Tool, ToolResult


class _Args(BaseModel):
    pattern: str = Field(description="Regex (Python flavor) or literal string to search for")
    path: str = Field(description="Directory to search")
    is_regex: bool = Field(default=False, description="If false, escape pattern as literal")
    max_matches: int = Field(default=200, ge=1, le=5000)
    max_file_size: int = Field(
        default=1_000_000,
        ge=1,
        le=20_000_000,
        description="Skip files larger than this",
    )
    include_globs: list[str] = Field(default_factory=list)
    case_sensitive: bool = Field(default=True)


class SearchTextTool(Tool[_Args]):
    name = "search_text"
    tier = 0
    description = (
        "Search for a pattern (literal or regex) across files in a directory. Returns "
        "match locations with line numbers and surrounding text. FAILURE MODES: "
        "directory not found; invalid regex; no matches; results truncated at "
        "max_matches; binary files silently skipped."
    )
    failure_modes = (
        "dir_not_found",
        "invalid_regex",
        "no_matches",
        "truncated",
        "binary_files_skipped",
    )
    Args = _Args

    async def execute(self, args: _Args, *, trace_id: str) -> ToolResult:  # noqa: ARG002
        root = Path(args.path).expanduser()
        if not root.exists() or not root.is_dir():
            return ToolResult(ok=False, error=f"not a directory: {root}")

        pattern = args.pattern if args.is_regex else re.escape(args.pattern)
        flags = 0 if args.case_sensitive else re.IGNORECASE
        try:
            rx = re.compile(pattern, flags)
        except re.error as e:
            return ToolResult(ok=False, error=f"invalid regex: {e}")

        matches: list[dict] = []
        truncated = False
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            if path.stat().st_size > args.max_file_size:
                continue
            if args.include_globs and not any(path.match(g) for g in args.include_globs):
                continue
            try:
                with path.open("r", encoding="utf-8") as f:
                    for lineno, line in enumerate(f, start=1):
                        if rx.search(line):
                            matches.append(
                                {
                                    "file": str(path),
                                    "line": lineno,
                                    "text": line.rstrip("\n")[:500],
                                }
                            )
                            if len(matches) >= args.max_matches:
                                truncated = True
                                break
            except (UnicodeDecodeError, PermissionError, OSError):
                continue
            if truncated:
                break

        return ToolResult(
            ok=True,
            output=matches,
            metadata={
                "pattern": args.pattern,
                "path": str(root),
                "count": len(matches),
                "truncated": truncated,
            },
        )
