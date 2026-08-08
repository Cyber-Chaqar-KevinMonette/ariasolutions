"""scaffold_game_docs — Tier 1. Generate real starter docs into a game
project's workspace, so she has something concrete to read/scan before
building, instead of starting cold.

Kevin (2026-07-20): "can we create started docs for her to work with?
Could you place them somewhere for her, and then I can have her scan
them to start? Can we make that a thing?" — a repeatable mechanism, not
one-off files. This tool IS that mechanism: callable for this project and
every future one, pulling real data from the project's own GameProject
record (name, genre, concept, monetization note) rather than generic
filler, plus a fixed reference on the tools/workflow she actually has.

Two files, written to the project workspace root (where she already
reads/writes everything else via existing tools — no new location, no
new "docs" convention to remember):

  GAME_BRIEF.md      — this project's own pitch + a design checklist to
                       fill in as work progresses (core loop, win/lose,
                       art style, audio plan, first milestone target).
  GETTING_STARTED.md — the fixed reference: what tools exist
                       (godot_check/godot_export/godot_open/
                       download_game_asset/award_game_xp/set_game_focus),
                       the focus discipline, the validate-often loop, and
                       how XP/learning actually get recorded. Same content
                       for every project; regenerating it is cheap and
                       keeps it current if the toolset changes later.

Deliberately NOT auto-triggered by define_game_project() — Kevin's own
phrasing ("place them somewhere... then I can have her scan them") wants
this as a distinct, visible step he controls the timing of, not a silent
side effect of defining a project.
"""
from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from ..game_projects import game_workspace_dir, load_by_slug
from .base import Tool, ToolResult


def _game_brief(project) -> str:
    concept = project.concept.strip() or "(not written yet — describe the loop and the hook)"
    monetization = project.monetization_note.strip() or "(not decided yet)"
    return f"""# {project.project_name} — Game Brief

**Genre:** {project.genre_label}
**Engine:** {project.engine}
**Status:** {project.status}

## The pitch

{concept}

## Monetization idea

{monetization}

## Design checklist — fill these in as the real answers emerge

Don't treat this as paperwork to finish before building — answer each
one for real, from what actually feels good once something is playable.
A checklist filled in from imagination before anything runs is a guess;
filled in after playing the actual build, it's a design decision.

- [ ] **Core loop** — what does the player do, over and over, for 30-90
      seconds? What makes that loop satisfying by itself?
- [ ] **Win / lose / progress** — what tells the player they're doing
      well or poorly? What's the smallest visible sign of progress?
- [ ] **Art style** — palette, shapes, mood. Simple and consistent beats
      ambitious and mismatched for a solo/AI-built scope.
- [ ] **Audio plan** — procedural/synthesized SFX (GDScript
      AudioStreamGenerator, no new tooling needed) or downloaded assets
      (download_game_asset — CC0/public-domain/CC-BY only, always
      recorded in ASSET_LICENSES.md).
- [ ] **First real milestone** — the smallest version of this that's
      genuinely fun to play once, even rough. Aim there first, not at
      the full scope.

## Notes

(running log of decisions, dead ends, things that turned out different
than expected once actually playtested — add to this as you go)
"""


_GETTING_STARTED = """# Getting Started — the tools and workflow for this project

## Tools you have

- **write_file / edit_file / copy_file** — scaffold and change the actual
  Godot project files (project.godot, .tscn scenes, .gd scripts). All
  sandboxed to this project's own workspace already.
- **godot_check** — headless validate (zero writes, cheap). Call this
  after every meaningful change, not just before a milestone — it's cheap
  enough that the tight iteration loop a human wouldn't bother with is
  exactly what you can afford.
- **godot_export** — headless release export. Writes a real build
  artifact, so it's gated to when Kevin's present (not reachable during
  an unattended /auto session, on purpose) — use godot_check for the
  constant validate-as-you-go loop instead.
- **godot_open** — opens the real Godot GUI editor so Kevin can watch you
  work live. Checks first whether one's already running; never opens a
  duplicate.
- **download_game_asset** — audio/art from kenney.nl, opengameart.org, or
  freesound.org. Only CC0 / public-domain / CC-BY licenses are accepted —
  anything else is refused before a byte is written. Every accepted
  download is recorded in this workspace's ASSET_LICENSES.md.
- **award_game_xp** — record real XP (task_completed, lesson_logged,
  milestone, session_focused, shipped). The amounts are fixed named
  constants, not something to invent — award for what genuinely
  happened, and say why in `note`. A milestone is judged by real
  game-feel ("the jump finally feels right"), not "the scene loads."
- **set_game_focus** — stay on this project by default. Only switch with
  an explicit ask from Kevin, or a genuinely vital reason (name which one
  in the reason field) — never out of preference or to dodge a hard
  problem here.

## The actual loop

1. Small, verifiable step (one scene, one mechanic, one fix).
2. godot_check.
3. If it's a real milestone (not just "it runs" — it *feels* like
   something), award_game_xp("milestone", note="...") and say what
   changed.
4. Keep a journal reflection on anything genuinely learned along the way
   — that's what the Reflector and success-pattern matching actually
   learn from, same as any other work here.

## Mode

Real autonomous work only happens via an explicit `/work <goal>` from
Kevin, inside an armed auto session — never on your own initiative.
Checking `auto_status()` tells you how much time is left in the current
session if one's active.
"""


class _Args(BaseModel):
    project_slug: str = Field(description="Slug of a registered game project")


class ScaffoldGameDocsTool(Tool[_Args]):
    name = "scaffold_game_docs"
    tier = 1
    description = (
        "Generate GAME_BRIEF.md and GETTING_STARTED.md into a registered "
        "game project's workspace — real starter docs pulled from the "
        "project's own concept/genre/monetization fields plus a fixed "
        "reference on the tools and workflow available. Call this once "
        "a project is defined, before starting real work, or again later "
        "to refresh GETTING_STARTED.md if the toolset has changed. "
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
        started_path = workspace / "GETTING_STARTED.md"
        brief_path.write_text(_game_brief(project), encoding="utf-8")
        started_path.write_text(_GETTING_STARTED, encoding="utf-8")

        return ToolResult(ok=True, output={
            "brief_path": str(brief_path),
            "getting_started_path": str(started_path),
            "message": f"Wrote GAME_BRIEF.md and GETTING_STARTED.md for "
                      f"{project.project_name!r} — read them to start.",
        })


__all__ = ["ScaffoldGameDocsTool"]
