"""award_game_xp — Tier 1. She records her own XP events.

Kevin (2026-07-20): "make sure in auto mode she is capable of all of
those tasks" — including "experience gathering." Real gap found while
checking this: game_dev_xp.py's award() function existed but had NO
tool wrapper at all — nothing in her own toolset could call it. The
"visible point system for working hard and doing a good job" had no way
for her to actually award herself a point during her own work; only
Python code calling award() directly could. This closes that gap.

Tier 1 (matches honor_write.py's "record an event to an append-only
ledger" precedent exactly) — available in every mode, including an
unattended /auto session, so XP is earned live during real building
work, not after the fact.

Honesty is enforced structurally, not just by instruction: event_type
must be one of the five named constants in game_dev_xp.py (no arbitrary
XP amount is possible), and `note` is required — every award names the
real thing that happened.
"""
from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from .. import game_dev_xp
from ..game_projects import load_by_slug
from .base import Tool, ToolResult


class _Args(BaseModel):
    project_slug: str = Field(description="Slug of a registered game project")
    event_type: str = Field(
        description=f"One of: {sorted(game_dev_xp.EVENT_TYPES)}. "
                    "task_completed=a real backlog task finished. "
                    "lesson_logged=a real lesson recorded (learning while building). "
                    "milestone=a real, playable milestone — judged by actual "
                    "game-feel, not 'the scene loads'. "
                    "session_focused=a full /auto block completed on this SAME "
                    "project without an unwarranted switch. shipped=a real "
                    "export/publish milestone."
    )
    note: str = Field(description="What actually happened — required, no empty awards.")


class AwardGameXPTool(Tool[_Args]):
    name = "award_game_xp"
    tier = 1
    description = (
        "Record one real XP event for a game project (task_completed, "
        "lesson_logged, milestone, session_focused, or shipped). XP "
        "values are fixed named constants, never arbitrary — this "
        "records real work, it doesn't let you invent a score. `note` "
        "is required: name the real thing that happened. Never award "
        "for something that didn't genuinely occur. "
        "FAILURE MODES: unknown_project; unknown_event_type; empty_note."
    )
    failure_modes = ("unknown_project", "unknown_event_type", "empty_note")
    Args = _Args

    def __init__(self, data_dir: Path | None = None) -> None:
        self._data_dir = data_dir

    async def execute(self, args: _Args, *, trace_id: str) -> ToolResult:  # noqa: ARG002
        data_dir = self._data_dir
        if data_dir is None:
            from ..config import SETTINGS
            data_dir = SETTINGS.paths.data_dir

        if load_by_slug(args.project_slug, data_dir) is None:
            return ToolResult(ok=False, error=f"unknown_project: {args.project_slug!r}")
        if not args.note.strip():
            return ToolResult(ok=False, error="empty_note: name what actually happened")

        try:
            ev = game_dev_xp.award(args.project_slug, args.event_type, args.note,
                                   data_dir=data_dir)
        except ValueError as e:
            return ToolResult(ok=False, error=f"unknown_event_type: {e}")

        total = game_dev_xp.total_xp(data_dir=data_dir)
        level = game_dev_xp.level_for_xp(total)
        return ToolResult(ok=True, output={
            "awarded_xp": ev.xp,
            "event_type": ev.event_type,
            "total_xp": total,
            "level": level,
            "message": f"+{ev.xp} XP ({ev.event_type}) — now Lv.{level}, {total} total XP.",
        })


__all__ = ["AwardGameXPTool"]
