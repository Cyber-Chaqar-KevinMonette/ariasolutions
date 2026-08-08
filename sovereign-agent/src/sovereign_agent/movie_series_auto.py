"""movie_series_auto.py — the two narrow model-driven writing calls Auto
Series needs: a series concept, and the next shot's beat.

Kevin, 2026-07-28: "It will use intelligent models to create and design
the entire series." The real, callable mechanism for "an intelligent
model writes something" in this repo is `agent_loop()` (`loop.py`) — the
same orchestrator model used for chat, via Ollama, already wired with
budgets/tiers/observability. `continue_runner.py` proves the call shape
for planner "compose_*" steps; this module calls `agent_loop()` directly
with an empty tool set (a pure text completion, not a tool-calling turn)
rather than going through the full `ContinuationStore`/`Step` ceremony,
which is built for persisted, poisonable, resumable EXTERNAL work items —
more indirection than a live, single-process autonomous loop needs.

Every call is logged to a plain per-project markdown file
(`auto_series_log.md`) so Kevin can review afterward exactly what got
written and why — no silent black box, same discipline as this session's
`_emit()` observability wiring.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

__all__ = [
    "SeriesConcept",
    "compose_series_concept",
    "compose_next_beat",
    "classify_command",
    "KNOWN_ACTIONS",
    "DEFAULT_THEME",
]

# Kevin, 2026-07-28: "we want full natural language autonomy." The
# keyword table in movie_pane.py's _dispatch_command handles explicit
# phrasing for free; classify_command is the fallback for everything
# else — real natural-language UNDERSTANDING via the same orchestrator
# model, but execution always routes back through the pane's own tested
# action methods afterward (movie_pane._act_on_classified_command). The
# model never calls a tool directly from this path — that's a
# deliberate, safety-motivated scope call, not an oversight: an
# unattended text box that can trigger arbitrary tool calls is a much
# bigger, harder-to-review surface than one that can only pick from a
# fixed, already-audited list of pane actions.
KNOWN_ACTIONS = (
    "focus", "new_project", "storyboard", "clip", "pitch", "add_shot",
    "start_episode", "advance", "run", "pause", "resume", "assemble", "verify",
    "safety", "auto_series", "stop_auto_series", "unknown",
)

# Mirrors MoviePitchPlanner's own DEFAULT_THEME — an open, attention-grabbing
# default rather than a narrow hardcoded topic, honored the same way here.
DEFAULT_THEME = (
    "a hopeful vision of an AI-and-humanity future, or whatever's most "
    "likely to grab attention — your call"
)

_BUDGET_MAX_ITERATIONS = 3
_BUDGET_MAX_WALL_SECONDS = 120
_BUDGET_MAX_TOKENS = 4000


@dataclass
class SeriesConcept:
    title: str
    logline: str
    genre: str
    style: str
    opening_beat: str
    raw_reply: str = ""


def _log_path(workspace: Path) -> Path:
    return Path(workspace) / "auto_series_log.md"


def _append_log(workspace: Path, heading: str, prompt: str, reply: str) -> None:
    try:
        path = _log_path(workspace)
        path.parent.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(f"\n## {ts} — {heading}\n\n**prompt:**\n\n{prompt}\n\n**reply:**\n\n{reply}\n")
    except Exception:  # noqa: BLE001 — a broken log write must never break Auto Series
        pass


async def _ask_orchestrator(goal: str) -> str:
    """The one real call: agent_loop() with an empty tool set, so the model
    answers directly instead of attempting a tool call. Bounded budget —
    this is "write one short passage," not an open-ended agentic task."""
    from .loop import agent_loop
    from .modes import Mode, RunBudget

    budget = RunBudget(
        max_iterations=_BUDGET_MAX_ITERATIONS,
        max_wall_seconds=_BUDGET_MAX_WALL_SECONDS,
        max_tokens=_BUDGET_MAX_TOKENS,
    )
    result = await agent_loop(goal=goal, mode=Mode.ONESHOT, budget=budget, tools={}, enable_reflector=False)
    return (result.final_message or "").strip()


def _parse_field(reply: str, label: str) -> str:
    m = re.search(rf"^\s*{re.escape(label)}\s*:\s*(.+)$", reply, re.IGNORECASE | re.MULTILINE)
    return m.group(1).strip() if m else ""


async def compose_series_concept(theme: str = "", *, workspace: Optional[Path] = None) -> SeriesConcept:
    """One agent_loop() call asking for a title/logline/genre/style/opening
    beat, on an open theme if none given. Parses a labeled-line reply;
    never raises — a malformed reply degrades to a clearly-labeled
    fallback concept (still usable — Auto Series must never crash because
    the model answered in the wrong shape) rather than blowing up the
    loop."""
    theme = (theme or "").strip() or DEFAULT_THEME
    prompt = (
        "You are designing a brand-new short-film series, entirely on your own — "
        "no human will review this before it's used. Reply in EXACTLY this shape, "
        "one field per line, nothing else:\n\n"
        "TITLE: <a short, evocative series title>\n"
        "LOGLINE: <one-sentence pitch>\n"
        "GENRE: <one of: short-film, comedy, drama, sci-fi, horror, documentary, other>\n"
        "STYLE: <one of: animated, live-action, mixed, other>\n"
        "OPENING BEAT: <one short paragraph describing the very first shot — "
        "what's on screen, what happens, tone>\n\n"
        f"Theme / direction: {theme}"
    )
    reply = ""
    try:
        reply = await _ask_orchestrator(prompt)
        concept = SeriesConcept(
            title=_parse_field(reply, "TITLE") or "Untitled Auto Series",
            logline=_parse_field(reply, "LOGLINE") or theme,
            genre=(_parse_field(reply, "GENRE") or "short-film").lower(),
            style=(_parse_field(reply, "STYLE") or "animated").lower(),
            opening_beat=_parse_field(reply, "OPENING BEAT") or (reply[:400] or theme),
            raw_reply=reply,
        )
    except Exception as exc:  # noqa: BLE001
        concept = SeriesConcept(
            title="Untitled Auto Series",
            logline=theme,
            genre="short-film",
            style="animated",
            opening_beat=f"(model call failed: {type(exc).__name__}: {exc}) — opening shot on theme: {theme}",
            raw_reply=reply,
        )
    if workspace is not None:
        _append_log(workspace, "series concept", prompt, reply or concept.opening_beat)
    return concept


async def compose_next_beat(
    *, series_title: str, prior_beats: list[str], episode_number: int, workspace: Optional[Path] = None,
) -> str:
    """One agent_loop() call: given the series + what's happened so far
    (most recent beat last), write the next shot's beat. Used both for a
    new episode's opening shot and for queuing the next shot in an
    existing one — the caller decides which."""
    history = "\n".join(f"- {b}" for b in prior_beats[-5:]) or "(nothing yet — this is the first shot)"
    prompt = (
        f"You are continuing the short-film series \"{series_title}\", entirely on your "
        "own — no human will review this before it's used. This is episode "
        f"{episode_number}. What's happened in this series so far (most recent last):\n"
        f"{history}\n\n"
        "Write ONE short paragraph describing the NEXT shot: what's on screen, what "
        "happens, tone. Reply with just that paragraph, nothing else."
    )
    try:
        reply = await _ask_orchestrator(prompt)
        beat = reply.strip() or f"{series_title}, episode {episode_number} — the story continues"
    except Exception as exc:  # noqa: BLE001
        reply = ""
        beat = f"{series_title}, episode {episode_number} — the story continues (model call failed: {type(exc).__name__})"
    if workspace is not None:
        _append_log(workspace, f"next beat (episode {episode_number})", prompt, reply or beat)
    return beat


async def classify_command(text: str) -> tuple[str, str]:
    """One agent_loop() call: classify a free-form movie-pane instruction
    into one of KNOWN_ACTIONS + extract its argument (if any). Never
    raises — a malformed reply or a failed model call degrades to
    ("unknown", text) so the caller can show its own honest "didn't
    understand that" message rather than silently doing nothing."""
    prompt = (
        "You control a movie-production command panel with these actions:\n"
        "  focus <project name> — switch focus to an existing project\n"
        "  new_project — create a brand-new project (no argument)\n"
        "  storyboard <scene> — generate a storyboard image\n"
        "  clip <scene> — generate a video clip\n"
        "  pitch <theme> — draft pitch concepts (theme optional)\n"
        "  add_shot <beat> — queue the next shot in the current episode\n"
        "  start_episode <beat> — start a new episode with this opening beat\n"
        "  advance — render one more clip in the current episode (no argument)\n"
        "  run — render up to 5 more clips (no argument)\n"
        "  pause — pause the current episode (no argument)\n"
        "  resume — resume the current episode (no argument)\n"
        "  assemble — cut the finished clips into one file (no argument)\n"
        "  verify — re-check the current episode's clips are real, playable files on disk (no argument)\n"
        "  safety <level> — set the current series' content safety level: strict, moderate, or open\n"
        "  auto_series — design and render a whole series unattended (no argument)\n"
        "  stop_auto_series — stop that unattended run (no argument)\n"
        "  unknown — none of the above fit\n\n"
        "Reply in EXACTLY this shape, nothing else:\n"
        "ACTION: <one action name from the list above>\n"
        "ARGUMENT: <the relevant text for that action, or blank>\n\n"
        f'Instruction: "{text}"'
    )
    try:
        reply = await _ask_orchestrator(prompt)
        action = _parse_field(reply, "ACTION").lower().replace(" ", "_").replace("-", "_")
        argument = _parse_field(reply, "ARGUMENT")
        if action not in KNOWN_ACTIONS:
            action = "unknown"
        return action, argument
    except Exception:  # noqa: BLE001
        return "unknown", text
