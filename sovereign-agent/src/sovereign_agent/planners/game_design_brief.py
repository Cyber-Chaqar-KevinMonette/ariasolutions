"""
╔══════════════════════════════════════════════════════════════════════════╗
║  game_design_brief.py — generate a structured Godot game design brief    ║
╚══════════════════════════════════════════════════════════════════════════╝

Kevin (2026-08-02): "I want to do none of the game design at all, 0% of
it — I want it all to be her," then "make her a world class expert game
designer optimized for Godot engine." Mirrors marketing_brief.py's shape
exactly: decomposes a registered game project into six composable design
sections, each rendered as one `compose_game_design_section` step the
agent runs through the orchestrator. `game_design_doctrine.notes_for()`
is threaded into every section's prompt — that's the actual expertise;
this planner is just the deterministic decomposition and ordering,
same discipline as marketing_brief.py's own docstring.

Sections (in order):
  1. core-loop                      the single thing the player does, over and over
  2. mechanics                      systems, how they interlock, difficulty curve
  3. art-direction                  visual style/palette — feeds place_game_sprite prompts
  4. scene-architecture             Godot-specific: scene tree, autoloads, signals, resources
  5. level-plan                     content/level structure and pacing
  6. progression-and-monetization   XP hooks (award_game_xp) + the project's monetization_note

This planner is intentionally OPINIONATED on structure, same reasoning as
marketing_brief.py: every brief has these six sections, in this order,
with this naming, so output is diffable across projects.

Authority tier: 1 (writes markdown to a single output path). No external
calls; the orchestrator handles all LLM work, same as marketing_brief.py.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .. import game_design_doctrine
from ..continuation import Step
from ..game_projects import load_by_slug
from .base import PlanResult, Planner, PlannerError

SECTIONS: tuple[tuple[str, str], ...] = (
    (
        "core-loop",
        "Compose the CORE LOOP section: name the single thing the player "
        "does over and over, describe one full cycle of it (30 seconds to "
        "a few minutes depending on genre), and state why it's worth "
        "repeating. End with the target session length.",
    ),
    (
        "mechanics",
        "Compose the MECHANICS section: list the systems that support the "
        "core loop (3-6 max — this is a solo-scoped project, not an AAA "
        "budget), how they interlock, and how difficulty/complexity ramps "
        "over a full playthrough. Flag anything that risks scope creep.",
    ),
    (
        "art-direction",
        "Compose the ART DIRECTION section: visual style (e.g. pixel art, "
        "flat vector, low-poly 3D), a palette description, and a "
        "one-sentence art-generation prompt template other sprites for "
        "this project should follow for consistency. This section is read "
        "directly by whoever prompts place_game_sprite later — be concrete "
        "enough to reuse verbatim.",
    ),
    (
        "scene-architecture",
        "Compose the SCENE ARCHITECTURE section: the actual Godot scene "
        "tree — root node type, main child scenes/nodes, which state "
        "belongs in an autoload singleton vs. a local node, and which "
        "cross-node communication uses signals. Follow the ENGINE GUIDANCE "
        "and GODOT CORE PRINCIPLES given above precisely — this is the "
        "one section a Godot engineer would check line-by-line.",
    ),
    (
        "level-plan",
        "Compose the LEVEL PLAN section: how content is structured (levels, "
        "waves, runs, or scenes depending on genre), roughly how many for "
        "a shippable first version, and the pacing curve across them "
        "(easy/teaching first, escalating after).",
    ),
    (
        "progression-and-monetization",
        "Compose the PROGRESSION AND MONETIZATION section: what milestones "
        "should award XP (this project already has an award_game_xp tool "
        "for milestone events — name 3-5 concrete milestones), and one "
        "concrete monetization angle appropriate to a small solo-shipped "
        "game (not a live-service assumption).",
    ),
)


class GameDesignBriefPlanner(Planner):
    name = "game-design-brief"
    description = (
        "Generate a structured Godot game design brief (core loop, "
        "mechanics, art direction, scene architecture, level plan, "
        "progression & monetization) for a registered game project into "
        "<output> — grounded in game_design_doctrine's Godot-specific "
        "expertise, not generic guesses."
    )

    def required_args(self) -> tuple[str, ...]:
        return ("project_slug", "output")

    def plan(self, **kwargs: Any) -> PlanResult:
        project_slug = kwargs.get("project_slug")
        output_arg = kwargs.get("output")

        if not project_slug:
            raise PlannerError("game-design-brief: 'project_slug' is required")
        if not output_arg:
            raise PlannerError("game-design-brief: 'output' is required")

        project_slug = str(project_slug).strip()
        output = Path(str(output_arg)).expanduser().resolve()

        data_dir = kwargs.get("data_dir")
        if data_dir is None:
            from ..config import SETTINGS
            data_dir = SETTINGS.paths.data_dir
        else:
            data_dir = Path(data_dir)

        project = load_by_slug(project_slug, data_dir)
        if project is None:
            raise PlannerError(f"game-design-brief: unknown project {project_slug!r}")

        doctrine_notes = game_design_doctrine.notes_for(project)

        skip = set(s.strip().lower() for s in (kwargs.get("skip") or []))
        sections = [(n, p) for (n, p) in SECTIONS if n not in skip]
        if not sections:
            raise PlannerError(
                "game-design-brief: all sections excluded — nothing to plan"
            )

        steps: list[Step] = []
        for i, (section_name, prompt) in enumerate(sections, start=1):
            steps.append(
                Step(
                    id=i,
                    kind="compose_game_design_section",
                    args={
                        "project_name": project.project_name,
                        "genre_label": project.genre_label,
                        "concept": project.concept,
                        "dimension": project.dimension,
                        "doctrine_notes": doctrine_notes,
                        "section": section_name,
                        "prompt": prompt,
                        "output": str(output),
                    },
                )
            )

        return PlanResult(
            goal=f"Godot game design brief for {project.project_name} ({project_slug}) → {output}",
            steps=steps,
            output_path=str(output),
            notes=(
                "Sections (in order): "
                + ", ".join(name for (name, _) in sections)
            ),
        )

    def render_step(self, step: Step, planner_args: dict) -> str:
        a = step.args
        project_name = a.get("project_name", "the project")
        genre_label = a.get("genre_label", "")
        concept = a.get("concept", "")
        dimension = a.get("dimension", "2d")
        doctrine_notes = a.get("doctrine_notes", "")
        section = a.get("section", "section")
        prompt = a.get("prompt", "")

        parts = [
            "You are a world-class expert game designer, optimized for the "
            f"Godot engine, writing the **{section}** section of a design "
            f"brief for **{project_name}** ({genre_label}, {dimension}).",
        ]
        if concept:
            parts.append(f"Concept: {concept}.")
        if doctrine_notes:
            parts.append(doctrine_notes)
        parts.append(prompt)
        parts.append(
            "Output: well-formed markdown, no preamble, no postamble. "
            "Start with a level-2 heading naming the section."
        )
        return "\n\n".join(parts)


__all__ = ["GameDesignBriefPlanner", "SECTIONS"]
