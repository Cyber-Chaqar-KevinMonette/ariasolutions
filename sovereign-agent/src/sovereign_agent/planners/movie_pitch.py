"""
╔══════════════════════════════════════════════════════════════════════════╗
║  movie_pitch.py — the Dream Pitch Generator for Movie Studio              ║
╚══════════════════════════════════════════════════════════════════════════╝

movie-studio-d (Kevin, 2026-07-28): "maybe a third feature turning AI
dreams into movies. Good AI dreams of the future maybe or whatever draws
attention." Mirrors marketing_brief.py's shape exactly: decomposes into
`compose_movie_pitch` steps the agent runs through the orchestrator — no
model is invoked here, this module is pure, deterministic decomposition.

`theme` is optional and defaults to an OPEN prompt (a hopeful AI-and-
humanity future, or whatever's most attention-grabbing) rather than a
narrow hardcoded topic — honoring "whatever draws attention" literally
instead of picking one theme for Kevin. One pitch per step, each asked to
be distinct from the others in the same batch. Output: N candidate
pitches written to a single review file at <output>; picking one feeds
`define_movie_project` — zero new cost, same local-LLM inference path
already used everywhere else.

Authority tier: 1 (writes markdown to a single output path). No external
calls; the orchestrator handles all LLM work, same as marketing_brief.py.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ..continuation import Step
from .base import PlanResult, Planner, PlannerError

DEFAULT_THEME = (
    "a hopeful vision of an AI-and-humanity future, or whatever's most "
    "likely to grab attention — your call"
)
DEFAULT_PITCH_COUNT = 3


class MoviePitchPlanner(Planner):
    name = "movie-pitch"
    description = (
        "Generate N original short-film pitch concepts (logline + one-line "
        "hook each) on a theme into <output> — defaults to an open, "
        "attention-grabbing theme when none is given."
    )

    def required_args(self) -> tuple[str, ...]:
        return ("output",)

    def plan(self, **kwargs: Any) -> PlanResult:
        output_arg = kwargs.get("output")
        if not output_arg:
            raise PlannerError("movie-pitch: 'output' is required")
        output = Path(str(output_arg)).expanduser().resolve()

        theme = (kwargs.get("theme") or "").strip() or DEFAULT_THEME

        count_arg = kwargs.get("count")
        count = int(count_arg) if count_arg is not None else DEFAULT_PITCH_COUNT
        if count < 1:
            raise PlannerError("movie-pitch: count must be at least 1")

        steps: list[Step] = []
        for i in range(1, count + 1):
            steps.append(
                Step(
                    id=i,
                    kind="compose_movie_pitch",
                    args={
                        "theme": theme,
                        "pitch_index": i,
                        "pitch_count": count,
                        "output": str(output),
                    },
                )
            )

        return PlanResult(
            goal=f"{count} movie pitch(es) on theme: {theme} → {output}",
            steps=steps,
            output_path=str(output),
            notes=f"theme: {theme}",
        )

    def render_step(self, step: Step, planner_args: dict) -> str:
        a = step.args
        theme = a.get("theme", DEFAULT_THEME)
        idx = a.get("pitch_index", 1)
        total = a.get("pitch_count", 1)

        return "\n\n".join([
            f"You are pitching an original movie concept — #{idx} of {total} "
            "for a short/local production (not a feature film budget).",
            f"Theme: {theme}.",
            "Write ONE original concept: a one-line logline (≤ 25 words) and "
            "a one-line hook explaining why it would grab attention. Do not "
            "repeat ideas from other pitches in this batch — make this one "
            "genuinely distinct.",
            "Output: well-formed markdown, no preamble, no postamble. Start "
            f"with a level-3 heading '### Pitch {idx}'.",
        ])


__all__ = ["MoviePitchPlanner", "DEFAULT_THEME", "DEFAULT_PITCH_COUNT"]
