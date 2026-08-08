"""game_file_tools.py — Tier 0/1. Path-safe file access for game projects,
scoped by project_slug instead of a raw filesystem path.

Kevin (2026-08-03), after watching it happen live: Aria's first real
GDScript edit attempt guessed a plausible-but-wrong path
(projects/ember-keep/fire.gd, relative to the sovereign-agent repo)
instead of the real sandbox workspace path, because edit_file/read_file
are generic tools that require a caller-supplied absolute path — and
nothing forced her to look it up first. scan_game_project, godot_check,
and place_game_sprite never have this problem: they all take
project_slug and resolve the real path internally via
game_workspace_dir(). These two tools close that same gap for the one
remaining generic-path chokepoint: reading/editing a project's own
source files.

Thin wrappers, not reimplementations — read delegates to ReadFileTool,
edit delegates to EditFileTool, both against the resolved absolute
path, so behavior (atomic writes, ambiguous-match refusal, size limits)
stays identical to the generic tools; only the path-guessing failure
mode is removed.
"""
from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from ..game_projects import game_workspace_dir, load_by_slug
from ..modes import Mode
from .base import Tool, ToolResult
from .edit_file import EditFileTool
from .read_file import ReadFileTool


def _resolve_within_workspace(
    project_slug: str, relative_path: str, data_dir: Path,
) -> tuple[Path | None, str | None]:
    if load_by_slug(project_slug, data_dir) is None:
        return None, f"unknown_project: {project_slug!r}"
    workspace = game_workspace_dir(project_slug, sandbox_dir=None).resolve()
    target = (workspace / relative_path).resolve()
    try:
        target.relative_to(workspace)
    except ValueError:
        return None, f"path_escapes_workspace: {relative_path!r} resolves outside {workspace}"
    return target, None


class _ReadArgs(BaseModel):
    project_slug: str = Field(description="Slug of a registered game project")
    relative_path: str = Field(
        description="Path relative to the project's workspace root, e.g. "
                    "'fire.gd' or 'assets/sprites/ember_core.png.import' — "
                    "not an absolute path."
    )
    max_bytes: int = Field(default=200_000, ge=1, le=2_000_000)


class ReadGameFileTool(Tool[_ReadArgs]):
    name = "read_game_file"
    tier = 0
    description = (
        "Read a text file from a registered game project by project_slug + "
        "relative_path — never guess or construct the absolute path "
        "yourself, this resolves it the same way scan_game_project does. "
        "Call scan_game_project first if you don't know what files exist. "
        "FAILURE MODES: unknown_project; path_escapes_workspace; "
        "file_not_found; binary_file; size_limit_exceeded; permission_denied."
    )
    failure_modes = (
        "unknown_project",
        "path_escapes_workspace",
        "file_not_found",
        "binary_file",
        "size_limit_exceeded",
        "permission_denied",
    )
    Args = _ReadArgs

    def __init__(self, data_dir: Path | None = None) -> None:
        self._data_dir = data_dir

    async def execute(self, args: _ReadArgs, *, trace_id: str) -> ToolResult:
        data_dir = self._data_dir
        if data_dir is None:
            from ..config import SETTINGS
            data_dir = SETTINGS.paths.data_dir

        target, err = _resolve_within_workspace(args.project_slug, args.relative_path, data_dir)
        if err:
            return ToolResult(ok=False, error=err)

        inner = ReadFileTool()
        return await inner.execute(
            inner.Args(path=str(target), max_bytes=args.max_bytes), trace_id=trace_id,
        )


class _EditArgs(BaseModel):
    project_slug: str = Field(description="Slug of a registered game project")
    relative_path: str = Field(
        description="Path relative to the project's workspace root, e.g. "
                    "'fire.gd' — not an absolute path."
    )
    old_str: str = Field(description="Exact string to find. Must be unique in file.")
    new_str: str = Field(default="", description="Replacement (empty string deletes)")


class EditGameFileTool(Tool[_EditArgs]):
    name = "edit_game_file"
    tier = 1
    description = (
        "Edit a file in a registered game project by project_slug + "
        "relative_path — never guess or construct the absolute path "
        "yourself, this resolves it the same way scan_game_project does. "
        "Same exact-match-once semantics as edit_file. Call scan_game_project "
        "or read_game_file first if you don't know the file's current "
        "content. FAILURE MODES: unknown_project; path_escapes_workspace; "
        "file_not_found; old_str_not_found; old_str_ambiguous; "
        "permission_denied."
    )
    failure_modes = (
        "unknown_project",
        "path_escapes_workspace",
        "file_not_found",
        "old_str_not_found",
        "old_str_ambiguous",
        "permission_denied",
    )
    Args = _EditArgs

    def __init__(self, mode: Mode | None = None, data_dir: Path | None = None) -> None:
        self._mode = mode or Mode.ONESHOT
        self._data_dir = data_dir

    async def execute(self, args: _EditArgs, *, trace_id: str) -> ToolResult:
        data_dir = self._data_dir
        if data_dir is None:
            from ..config import SETTINGS
            data_dir = SETTINGS.paths.data_dir

        target, err = _resolve_within_workspace(args.project_slug, args.relative_path, data_dir)
        if err:
            return ToolResult(ok=False, error=err)

        inner = EditFileTool(mode=self._mode)
        return await inner.execute(
            inner.Args(path=str(target), old_str=args.old_str, new_str=args.new_str),
            trace_id=trace_id,
        )


__all__ = ["ReadGameFileTool", "EditGameFileTool"]
