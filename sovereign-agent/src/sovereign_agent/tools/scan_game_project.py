"""scan_game_project — Tier 0. One-call refresh on a game project's real
current state, for resuming cold.

Kevin (2026-08-02): "she can do a full scan on the project if she needs
to refresh herself" — the resume flow (GamePane's "Open in Editor") gets
her INTO the editor fast, but nothing gave her a fast way to reload the
project's actual state into context: what's on disk, what she'd already
decided (GAME_BRIEF.md's Notes — the log of real, playtested decisions,
not guesses), how much XP/progress exists, what's licensed. Read-only,
Tier 0 — pure state assembly, no judgment, no writes.

Deliberately does NOT inline GETTING_STARTED.md's content — that's a
fixed reference (same for every project, doesn't change), not per-project
STATE. Scanning it every time would waste tokens on something she can
already read directly if she needs the reference refresher.
"""
from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from ..game_assets import asset_licenses_path
from ..game_dev_xp import level_for_xp, progress_to_next, recent_events, total_xp
from ..game_projects import game_workspace_dir, load_by_slug
from .base import Tool, ToolResult

_MAX_TREE_ENTRIES = 200
_MAX_NOTES_CHARS = 4000


def _file_tree(workspace: Path) -> list[str]:
    if not workspace.is_dir():
        return []
    entries = []
    for p in sorted(workspace.rglob("*")):
        if p.is_dir():
            continue
        if any(part.startswith(".") for part in p.relative_to(workspace).parts):
            continue
        entries.append(str(p.relative_to(workspace)))
        if len(entries) >= _MAX_TREE_ENTRIES:
            entries.append(f"… truncated at {_MAX_TREE_ENTRIES} files")
            break
    return entries


def _extract_notes(brief_text: str) -> str:
    marker = "## Notes"
    idx = brief_text.find(marker)
    if idx == -1:
        return ""
    return brief_text[idx + len(marker):].strip()[:_MAX_NOTES_CHARS]


def _scene_summary(workspace: Path) -> dict:
    scene_path = workspace / "main.tscn"
    if not scene_path.is_file():
        return {"exists": False}
    text = scene_path.read_text(encoding="utf-8", errors="replace")
    return {
        "exists": True,
        "node_count": text.count("[node "),
        "ext_resource_count": text.count("[ext_resource "),
        "has_script": 'script = ExtResource' in text,
    }


class _Args(BaseModel):
    project_slug: str = Field(description="Slug of a registered game project")


class ScanGameProjectTool(Tool[_Args]):
    name = "scan_game_project"
    tier = 0
    description = (
        "Read-only full-state scan of a registered game project: file "
        "tree, GAME_BRIEF.md's Notes (the real decisions/lessons log — "
        "not the static template), scene summary (node/resource counts), "
        "XP/level, asset license file presence, and status. Use this to "
        "refresh yourself on a project's real current state before "
        "resuming work on it, especially after a break. "
        "FAILURE MODES: unknown_project."
    )
    failure_modes = ("unknown_project",)
    Args = _Args

    def __init__(self, data_dir: Path | None = None) -> None:
        self._data_dir = data_dir

    async def execute(self, args: _Args, *, trace_id: str) -> ToolResult:  # noqa: ARG002
        data_dir = self._data_dir
        if data_dir is None:
            from ..config import SETTINGS
            data_dir = SETTINGS.paths.data_dir

        project = load_by_slug(args.project_slug, data_dir)
        if project is None:
            return ToolResult(ok=False, error=f"unknown_project: {args.project_slug!r}")

        workspace = game_workspace_dir(args.project_slug, sandbox_dir=None)
        brief_path = workspace / "GAME_BRIEF.md"
        notes = ""
        if brief_path.is_file():
            notes = _extract_notes(brief_path.read_text(encoding="utf-8", errors="replace"))

        licenses_path = asset_licenses_path(workspace)

        xp = total_xp(args.project_slug, data_dir)
        cur_level = level_for_xp(xp)
        into_level, needed = progress_to_next(xp)
        events = recent_events(10, args.project_slug, data_dir)

        return ToolResult(ok=True, output={
            "project_name": project.project_name,
            "genre": project.genre,
            "dimension": project.dimension,
            "engine": project.engine,
            "status": project.status,
            "concept": project.concept,
            "created_at": project.created_at,
            "modified_at": project.modified_at,
            "workspace": str(workspace),
            "file_tree": _file_tree(workspace),
            "scene": _scene_summary(workspace),
            "notes_log": notes,
            "has_getting_started_doc": (workspace / "GETTING_STARTED.md").is_file(),
            "has_asset_licenses": licenses_path.is_file(),
            "xp_total": xp,
            "level": cur_level,
            "xp_into_level": into_level,
            "xp_needed_for_next": needed,
            "recent_xp_events": [
                {"event_type": e.event_type, "note": e.note, "ts": e.ts, "xp": e.xp}
                for e in events
            ],
        })


__all__ = ["ScanGameProjectTool"]
