"""set_movie_focus — Tier 1. She can switch (or set) her own focused movie
project, with a required reason — an audit trail, not a hard lock.

movie-studio-d (Kevin, 2026-07-28): mirrors set_game_focus.py exactly. The
behavioral rule (unchanged): don't switch focus without either an explicit
operator instruction or a genuinely vital reason, and say which one it was
in `reason`. Nothing here enforces that mechanically — `reason` is
required and permanently logged, but the judgment is hers.
"""
from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from ..movie_projects import set_focus
from .base import Tool, ToolResult


class _Args(BaseModel):
    project_slug: str = Field(description="Slug of the movie project to focus on")
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


class SetMovieFocusTool(Tool[_Args]):
    name = "set_movie_focus"
    tier = 1
    description = (
        "Switch (or set) which movie project is currently focused. Stay "
        "on the current focus by default — only call this with an "
        "explicit operator instruction to switch, or a genuinely vital "
        "reason (name which one in `reason`). Every switch is permanently "
        "logged with its reason — this is an audit trail, not a hard "
        "lock, but treat the discipline as real. "
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


__all__ = ["SetMovieFocusTool"]
