"""define_movie_project — Tier 1. She can define a new movie project herself.

movie-studio-d (Kevin, 2026-07-28): mirrors define_game_project.py exactly
— defining direction is cheap and safe; producing the actual film is the
real work, gated by the usual generation tools. Same validation as the
Movie Studio cockpit form (genre/style must be real or explained, title
must be sane).

Tier 1 — a sandboxed, reversible metadata write (a JSON record, not
footage), available in every mode including /auto.
"""
from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from ..movie_projects import MovieProject, save, slugify, validate
from .base import Tool, ToolResult


class _Args(BaseModel):
    title: str = Field(description="A short, sane movie title")
    genre: str = Field(
        default="short-film",
        description="One of the curated genre keys (see movie_projects.MOVIE_GENRES), "
                    "or 'other' with genre_other set.",
    )
    genre_other: str = Field(default="", description="Required if genre == 'other'")
    logline: str = Field(default="", description="The one-line pitch")
    style: str = Field(
        default="animated",
        description="animated | live-action | mixed | other",
    )
    monetization_note: str = Field(default="", description="How this one might make "
                                                            "even a little money")


class DefineMovieProjectTool(Tool[_Args]):
    name = "define_movie_project"
    tier = 1
    description = (
        "Define a new movie project (title, genre, logline, style) — the "
        "direction, not the footage. Define before production, same "
        "discipline as everywhere else in this project. Does not set "
        "focus — call set_movie_focus separately if this should become "
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

        proj = MovieProject(
            title=args.title, genre=args.genre,
            genre_other=args.genre_other, logline=args.logline,
            style=args.style, monetization_note=args.monetization_note,
        )
        errs = validate(proj)
        if errs:
            return ToolResult(ok=False, error="invalid_project: " + "; ".join(errs))

        save(proj, data_dir)
        return ToolResult(ok=True, output={
            "slug": slugify(proj.title),
            "title": proj.title,
            "message": f"Defined movie project {proj.title!r} "
                      f"({proj.genre_label}). Not focused yet — call "
                      "set_movie_focus if this should become active.",
        })


__all__ = ["DefineMovieProjectTool"]
