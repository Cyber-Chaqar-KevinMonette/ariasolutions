"""set_game_focus — Tier 1. She can switch (or set) her own focused game
project, with a required reason — an audit trail, not a hard lock.

Kevin (2026-07-20): "make sure in auto mode she is capable of all of
those tasks." Real gap: game_projects.set_focus() existed and was
already careful (required reason, bounded history) but had NO tool
wrapper — only the Game Studio cockpit screen (Kevin-only, a button
click) could call it. She had no way to act on her own focus discipline
during autonomous work: staying on the current project by default, or
switching for an explicit reason.

Tier 1 (matches game_projects.py's own design intent — "the tool
description she reads" already assumed this tool would exist and state
the rule; it just hadn't been built yet). Available in every mode,
including /auto.

The behavioral rule (unchanged from game_projects.py, restated here
since this is what she actually reads before calling it): don't switch
focus without either an explicit operator instruction or a genuinely
vital reason, and say which one it was in `reason`. Nothing here
enforces that mechanically — `reason` is required and permanently
logged, but the judgment is hers, same as everywhere else in this
project's propose/observe doctrine.
"""
from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from ..game_projects import set_focus
from .base import Tool, ToolResult


class _Args(BaseModel):
    project_slug: str = Field(description="Slug of the game project to focus on")
    reason: str = Field(
        description="Why switching now — must be either an explicit operator "
                    "instruction ('Kevin asked to switch to X') or a genuinely "
                    "vital reason ('vital: blocked on missing asset in Y'). "
                    "Required, always logged."
    )
    vital: bool = Field(
        default=False,
        description="True only for a genuinely vital, unprompted switch — not "
                    "for ordinary preference. Logged alongside the reason.",
    )


class SetGameFocusTool(Tool[_Args]):
    name = "set_game_focus"
    tier = 1
    description = (
        "Switch (or set) which game project is currently focused. Stay "
        "on the current focus by default — only call this with an "
        "explicit operator instruction to switch, or a genuinely vital "
        "reason (name which one in `reason`). Never switch out of mere "
        "preference or to avoid a hard problem on the current project. "
        "Every switch is permanently logged with its reason — this is an "
        "audit trail, not a hard lock, but treat the discipline as real. "
        "FAILURE MODES: unknown_project; empty_reason."
    )
    failure_modes = ("unknown_project", "empty_reason")
    Args = _Args

    def __init__(self, data_dir: Path | None = None) -> None:
        self._data_dir = data_dir

    async def execute(self, args: _Args, *, trace_id: str) -> ToolResult:  # noqa: ARG002
        data_dir = self._data_dir
        if data_dir is None:
            from ..config import SETTINGS
            data_dir = SETTINGS.paths.data_dir

        try:
            state = set_focus(args.project_slug, args.reason, data_dir, vital=args.vital)
        except ValueError as e:
            msg = str(e)
            if "reason" in msg:
                return ToolResult(ok=False, error=f"empty_reason: {msg}")
            return ToolResult(ok=False, error=f"unknown_project: {msg}")

        return ToolResult(ok=True, output={
            "focused_slug": state.slug,
            "since": state.since,
            "vital": args.vital,
            "message": f"Focus set to {state.slug!r} — {args.reason}",
        })


__all__ = ["SetGameFocusTool"]
