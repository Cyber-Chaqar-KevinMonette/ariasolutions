"""small_model_confidence — keep a small model from silently giving up.

Final-sprint Round 1, companion to `small_model_bridge`. The bridge fixes
*how* a small model's tool call is shaped; this fixes *whether it keeps
going*. Small (7B/8B) models, mid-task, tend to:

  - **stop prematurely** — return an empty/whitespace answer with no tool
    call while real work still remains (the "one turn and done" feeling).
  - **hedge into paralysis** — "I'm not sure", "I can't", "I don't have
    access", "as an AI I cannot..." — giving up instead of using a tool
    that is right there in its list.
  - **narrate instead of act** — describe what it *would* do ("I would
    call read_session...") without emitting the call.

None of these are the model being unable — they're the model being
under-equipped and under-confident. This module DETECTS those patterns and
produces a short, concrete **equipping re-prompt**: a reminder of exactly
what it can do next, so it proceeds instead of ending the session.

Pure and dependency-free (same discipline as the bridge). It never forces
progress on a genuinely-finished task (empty work-remaining → accept), and
it caps re-prompts so it can never loop forever. The apply script wires
`assess_turn()` into the `/work` session loop as an advisory before the
loop decides a subtask is done.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

__all__ = [
    "TurnDecision",
    "assess_turn",
    "detect_giving_up",
    "is_empty_answer",
    "equipping_nudge",
    "MAX_REPROMPTS",
]

# Never re-prompt the same stalled subtask more than this many times — past
# it, accept the model's output and move on (no infinite equip loop).
MAX_REPROMPTS = 2

# Hedge / give-up phrasings small models fall into instead of using a tool.
_GIVE_UP_PATTERNS = [
    r"\bi'?m not sure\b",
    r"\bi am not sure\b",
    r"\bi can'?t\b",
    r"\bi cannot\b",
    r"\bi'?m unable\b",
    r"\bi am unable\b",
    r"\bi don'?t have (?:access|the ability|enough)\b",
    r"\bas an ai\b",
    r"\bi'?m just a\b",
    r"\bi would (?:call|use|run|need to)\b",   # narrates instead of acting
    r"\bi'?m sorry,? but\b",
    r"\bunfortunately,? i\b",
]
_GIVE_UP_RE = re.compile("|".join(_GIVE_UP_PATTERNS), re.IGNORECASE)


@dataclass(frozen=True)
class TurnDecision:
    """What the session loop should do with this model turn.

    action:  "accept"   — the turn is fine (or work is done); proceed.
             "reprompt" — re-send with `nudge` appended; the model stalled.
    reason:  short machine tag for the ledger/doctor.
    nudge:   the equipping re-prompt text (empty unless action == reprompt).
    """
    action: str
    reason: str
    nudge: str = ""


def _message(response: dict[str, Any]) -> dict[str, Any]:
    msg = response.get("message") if isinstance(response, dict) else None
    return msg if isinstance(msg, dict) else {}


def _has_tool_call(response: dict[str, Any]) -> bool:
    tcs = _message(response).get("tool_calls")
    return isinstance(tcs, list) and len(tcs) > 0


def is_empty_answer(response: dict[str, Any]) -> bool:
    """True when the model produced neither a tool call nor real content."""
    if _has_tool_call(response):
        return False
    content = _message(response).get("content")
    return not (isinstance(content, str) and content.strip())


def detect_giving_up(response: dict[str, Any]) -> bool:
    """True when the content hedges/gives up AND no tool call was made.

    A hedge that still comes with a tool call is fine — the model is acting.
    """
    if _has_tool_call(response):
        return False
    content = _message(response).get("content")
    if not isinstance(content, str) or not content.strip():
        return False
    return _GIVE_UP_RE.search(content) is not None


def equipping_nudge(reason: str, available_tools: list[str] | None = None) -> str:
    """A short, concrete re-prompt that equips the model to proceed.

    Names the tools it can actually use (small models forget their own
    toolbox), and reframes: it IS capable and should take the next step.
    """
    tools = [t for t in (available_tools or []) if isinstance(t, str)]
    tool_line = ""
    if tools:
        shown = ", ".join(tools[:8])
        more = f" (+{len(tools) - 8} more)" if len(tools) > 8 else ""
        tool_line = f" You have these tools available now: {shown}{more}."
    if reason == "empty":
        return (
            "You didn't take an action. The task isn't finished yet — take "
            "the next concrete step now: call the single most useful tool, "
            f"or state the specific next action in one line.{tool_line}"
        )
    if reason == "giving-up":
        return (
            "You're equipped for this — don't stop here. You can act "
            "directly with the tools you have rather than saying you can't. "
            f"Pick the one tool that moves this forward and call it now.{tool_line}"
        )
    return (
        "Keep going — take the next concrete step toward finishing the "
        f"task.{tool_line}"
    )


def assess_turn(
    response: dict[str, Any],
    *,
    work_remains: bool,
    reprompts_so_far: int = 0,
    available_tools: list[str] | None = None,
) -> TurnDecision:
    """Decide what the `/work` loop should do with this model turn.

    - work done (``work_remains`` False) → always accept.
    - re-prompt budget exhausted → accept (never loop forever).
    - a real tool call → accept (the model is acting).
    - empty answer with work left → re-prompt (equip: "empty").
    - hedge/give-up with work left → re-prompt (equip: "giving-up").
    - otherwise → accept.
    """
    if not work_remains:
        return TurnDecision("accept", "work-complete")
    if reprompts_so_far >= MAX_REPROMPTS:
        return TurnDecision("accept", "reprompt-budget-exhausted")
    if _has_tool_call(response):
        return TurnDecision("accept", "acting")
    if is_empty_answer(response):
        return TurnDecision("reprompt", "empty", equipping_nudge("empty", available_tools))
    if detect_giving_up(response):
        return TurnDecision("reprompt", "giving-up", equipping_nudge("giving-up", available_tools))
    return TurnDecision("accept", "substantive")
