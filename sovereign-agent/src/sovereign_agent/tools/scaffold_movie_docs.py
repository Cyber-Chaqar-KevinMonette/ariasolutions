"""scaffold_movie_docs — Tier 1. Generate real starter docs into a movie
project's workspace, so she has something concrete to work from instead
of starting cold.

movie-studio-d (Kevin, 2026-07-28): mirrors scaffold_game_docs.py exactly.
Two files, written to the project workspace root:

  TREATMENT.md      — this project's own pitch + a real film-treatment
                      checklist (logline, genre, style, monetization,
                      first real milestone).
  SCRIPT_OUTLINE.md — a fixed structural reference (act breaks / beat
                      sheet skeleton) to fill in as the story takes shape.

Deliberately NOT auto-triggered by define_movie_project() — same distinct,
visible, operator-timed step as scaffold_game_docs.py.
"""
from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from ..movie_projects import load_by_slug, movie_workspace_dir
from .base import Tool, ToolResult


def _treatment(project) -> str:
    logline = project.logline.strip() or "(not written yet — one sentence: who, wants what, why it matters)"
    monetization = project.monetization_note.strip() or "(not decided yet)"
    return f"""# {project.title} — Treatment

**Genre:** {project.genre_label}
**Style:** {project.style_label}
**Status:** {project.status}

## Logline

{logline}

## Monetization idea

{monetization}

## Design checklist — fill these in as the real answers emerge

Don't treat this as paperwork to finish before production — answer each
one for real, from what actually feels right once something is on screen.

- [ ] **Core visual idea** — the one image or moment the whole thing is
      built around. If you can't say it in one sentence, it isn't locked yet.
- [ ] **Structure** — how many scenes/shots, roughly how long each runs.
- [ ] **Look** — palette, shapes, mood. Simple and consistent beats
      ambitious and mismatched for a solo/AI-built scope.
- [ ] **Sound** — dialogue, score, or silence — what's the plan, even if
      rough.
- [ ] **First real milestone** — the smallest version of this that's
      genuinely compelling once storyboarded, even rough. Aim there
      first, not at the full scope.

## Notes

(running log of decisions, dead ends, things that turned out different
than expected once actually storyboarded — add to this as you go)
"""


_SCRIPT_OUTLINE = """# Script Outline

A skeleton to fill in as the story takes shape — replace each bracketed
line with the real beat once it's decided, don't leave placeholders in
a "finished" outline.

## Act / Beat structure

1. **Opening image** — [what we see first, before anything is explained]
2. **Setup** — [who/where/what's normal, in as few beats as possible]
3. **Turn** — [what changes or is asked]
4. **Development** — [the real body of the piece — one beat per shot
   sequence, add rows as needed]
5. **Turn / climax** — [the moment the whole thing has been building to]
6. **Closing image** — [what we're left with]

## Shot list (fill in per scene once storyboarded)

| # | Scene | Description | Storyboard asset |
|---|-------|-------------|-------------------|
| 1 |       |             |                   |
"""


class _Args(BaseModel):
    project_slug: str = Field(description="Slug of a registered movie project")


class ScaffoldMovieDocsTool(Tool[_Args]):
    name = "scaffold_movie_docs"
    tier = 1
    description = (
        "Generate TREATMENT.md and SCRIPT_OUTLINE.md into a registered "
        "movie project's workspace — real starter docs pulled from the "
        "project's own logline/genre/style/monetization fields plus a "
        "fixed structural skeleton to fill in. Call this once a project "
        "is defined, before writing real script content. "
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

        workspace = movie_workspace_dir(args.project_slug, sandbox_dir=None)
        treatment_path = workspace / "TREATMENT.md"
        outline_path = workspace / "SCRIPT_OUTLINE.md"
        treatment_path.write_text(_treatment(project), encoding="utf-8")
        outline_path.write_text(_SCRIPT_OUTLINE, encoding="utf-8")

        from .. import movie_assets
        movie_assets.record_asset(
            workspace, relative_path="TREATMENT.md",
            kind="script", source_tool="scaffold_movie_docs")

        return ToolResult(ok=True, output={
            "treatment_path": str(treatment_path),
            "script_outline_path": str(outline_path),
            "message": f"Wrote TREATMENT.md and SCRIPT_OUTLINE.md for "
                      f"{project.title!r} — read them to start.",
        })


__all__ = ["ScaffoldMovieDocsTool"]
