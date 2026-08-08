"""define_game_project — Tier 1. She can define a new game project herself.

Kevin's original Game Studio design already said it plainly: "Kevin or
Aria defines the real concept deliberately" — but only the cockpit
screen (Kevin-only, a form) could actually call game_projects.save().
This closes that gap with a tool wrapper, same validation as the form
(genre must be real or explained via genre_other, name must be sane).

Tier 1 — a sandboxed, reversible metadata write (a JSON record, not game
code), available in every mode including /auto. Mirrors bot_projects.py's
own precedent: defining direction is cheap and safe; building against it
is the real work, gated by the usual write tools.
"""
from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from ..game_projects import GameProject, save, slugify, validate
from .base import Tool, ToolResult


class _Args(BaseModel):
    project_name: str = Field(description="A short, sane project name")
    genre: str = Field(
        default="idle-incremental",
        description="One of the curated genre keys (see game_projects.GENRES), "
                    "or 'other' with genre_other set.",
    )
    genre_other: str = Field(default="", description="Required if genre == 'other'")
    concept: str = Field(default="", description="The pitch — the loop, the hook, "
                                                 "why it's worth finishing")
    monetization_note: str = Field(default="", description="How this one might make "
                                                            "even a little money")


class DefineGameProjectTool(Tool[_Args]):
    name = "define_game_project"
    tier = 1
    description = (
        "Define a new game project (name, genre, concept, monetization "
        "idea) — the direction, not the code. Define before build, same "
        "discipline as everywhere else in this project. Does not set "
        "focus — call set_game_focus separately if this should become "
        "the active project. "
        "FAILURE MODES: invalid_project."
    )
    failure_modes = ("invalid_project",)
    Args = _Args

    def __init__(self, data_dir: Path | None = None) -> None:
        self._data_dir = data_dir

    async def execute(self, args: _Args, *, trace_id: str) -> ToolResult:  # noqa: ARG002
        data_dir = self._data_dir
        if data_dir is None:
            from ..config import SETTINGS
            data_dir = SETTINGS.paths.data_dir

        proj = GameProject(
            project_name=args.project_name, genre=args.genre,
            genre_other=args.genre_other, concept=args.concept,
            monetization_note=args.monetization_note,
        )
        errs = validate(proj)
        if errs:
            return ToolResult(ok=False, error="invalid_project: " + "; ".join(errs))

        save(proj, data_dir)
        return ToolResult(ok=True, output={
            "slug": slugify(proj.project_name),
            "project_name": proj.project_name,
            "message": f"Defined game project {proj.project_name!r} "
                      f"({proj.genre_label}). Not focused yet — call "
                      "set_game_focus if this should become active.",
        })


__all__ = ["DefineGameProjectTool"]
