"""award_aria_xp — Tier 1. She records her own general task-scoring events.

Kevin (2026-07-25): "For each task in the live window. The AI can score
points. Good and successful task plus 10 points. If the AI does
something bad or makes a mistake minus 5 points."

Mirrors award_game_xp.py's exact precedent (Tier 1, available in every
mode including unattended /auto, honesty enforced structurally via named
constants + a required note) but for aria_xp.py's general ledger instead
of a game-project-scoped one. A mistake is NOT just a point deduction —
event_type="mistake" here requires how_to_avoid too, and routes through
aria_xp.record_mistake(), which opens a real Conflict->Diagnosis->
Resolution case in diagnosis.ConflictCatalog before the points land, so
"lock it in memory" means something real.
"""
from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from .. import aria_xp
from .base import Tool, ToolResult


class _Args(BaseModel):
    event_type: str = Field(
        description=f"One of: {sorted(aria_xp.EVENT_TYPES)}. "
                    "task_success=a real task genuinely finished well. "
                    "mistake=something went wrong (requires how_to_avoid too). "
                    "pattern_recognized/pattern_recalled/atom_written/"
                    "memory_written/interpretation_recorded/field_note_written="
                    "a real, already-happened action of that kind."
    )
    note: str = Field(description="What actually happened — required, no empty awards.")
    how_to_avoid: str = Field(
        default="",
        description="REQUIRED when event_type='mistake': how to avoid this in "
                    "the future. Opens a real diagnosis.py case before the "
                    "points land — this is not just a deduction.",
    )


class AwardAriaXPTool(Tool[_Args]):
    name = "award_aria_xp"
    tier = 1
    description = (
        "Record one real XP event for general work (task_success, mistake, "
        "pattern_recognized, pattern_recalled, atom_written, memory_written, "
        "interpretation_recorded, field_note_written). XP values are fixed "
        "named constants, never arbitrary. `note` is required. For "
        "event_type='mistake', `how_to_avoid` is ALSO required — it opens a "
        "real, reviewable Conflict->Diagnosis->Resolution case before the "
        "points are deducted; never award for something that didn't genuinely "
        "happen. "
        "FAILURE MODES: unknown_event_type; empty_note; missing_how_to_avoid."
    )
    failure_modes = ("unknown_event_type", "empty_note", "missing_how_to_avoid")
    Args = _Args

    def __init__(self, data_dir: Path | None = None) -> None:
        self._data_dir = data_dir

    async def execute(self, args: _Args, *, trace_id: str) -> ToolResult:  # noqa: ARG002
        data_dir = self._data_dir
        if data_dir is None:
            from ..config import SETTINGS
            data_dir = SETTINGS.paths.data_dir

        if not args.note.strip():
            return ToolResult(ok=False, error="empty_note: name what actually happened")
        if args.event_type not in aria_xp.EVENT_TYPES:
            return ToolResult(
                ok=False,
                error=f"unknown_event_type: {args.event_type!r} — one of "
                     f"{sorted(aria_xp.EVENT_TYPES)}",
            )

        if args.event_type == "mistake":
            if not args.how_to_avoid.strip():
                return ToolResult(
                    ok=False,
                    error="missing_how_to_avoid: a mistake needs a real plan "
                         "to avoid it, not just a point deduction",
                )
            ev = aria_xp.record_mistake(
                what_happened=args.note, how_to_avoid=args.how_to_avoid,
                data_dir=data_dir,
            )
        else:
            ev = aria_xp.award(args.event_type, args.note, data_dir=data_dir)

        total = aria_xp.total_xp(data_dir=data_dir)
        level = aria_xp.level_for_xp(total)
        sign = "+" if ev.xp >= 0 else ""
        return ToolResult(ok=True, output={
            "awarded_xp": ev.xp,
            "event_type": ev.event_type,
            "case_id": ev.case_id,
            "total_xp": total,
            "level": level,
            "message": f"{sign}{ev.xp} XP ({ev.event_type}) — now Lv.{level}, {total} total XP.",
        })


__all__ = ["AwardAriaXPTool"]
