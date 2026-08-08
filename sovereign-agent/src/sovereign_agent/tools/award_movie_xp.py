"""award_movie_xp — Tier 1. She records her own Movie Studio XP events.

movie-studio-d (Kevin, 2026-07-28): mirrors award_game_xp.py exactly.
Honesty is enforced structurally, not just by instruction: event_type
must be one of the named constants in movie_dev_xp.py (no arbitrary XP
amount is possible), and `note` is required — every award names the real
thing that happened.
"""
from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from .. import movie_dev_xp
from ..movie_projects import load_by_slug
from .base import Tool, ToolResult


class _Args(BaseModel):
    project_slug: str = Field(description="Slug of a registered movie project")
    event_type: str = Field(
        description=f"One of: {sorted(movie_dev_xp.EVENT_TYPES)}. "
                    "treatment_drafted=a real treatment/script outline written. "
                    "storyboard_generated=a real storyboard/key-art still generated. "
                    "pitch_accepted=a drafted pitch was picked and became this "
                    "project. milestone=a real, judged milestone — say why in "
                    "note. shipped=a real finished/shared cut."
    )
    note: str = Field(description="What actually happened — required, no empty awards.")


class AwardMovieXPTool(Tool[_Args]):
    name = "award_movie_xp"
    tier = 1
    description = (
        "Record one real XP event for a movie project (treatment_drafted, "
        "storyboard_generated, pitch_accepted, milestone, or shipped). XP "
        "values are fixed named constants, never arbitrary. `note` is "
        "required: name the real thing that happened. Never award for "
        "something that didn't genuinely occur. "
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
            ev = movie_dev_xp.award(args.project_slug, args.event_type, args.note,
                                    data_dir=data_dir)
        except ValueError as e:
            return ToolResult(ok=False, error=f"unknown_event_type: {e}")

        total = movie_dev_xp.total_xp(data_dir=data_dir)
        level = movie_dev_xp.level_for_xp(total)
        return ToolResult(ok=True, output={
            "awarded_xp": ev.xp,
            "event_type": ev.event_type,
            "total_xp": total,
            "level": level,
            "message": f"+{ev.xp} XP ({ev.event_type}) — now Lv.{level}, {total} total XP.",
        })


__all__ = ["AwardMovieXPTool"]
