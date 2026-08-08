"""goal_modulator.py — turn one big, open-ended goal into a real subtask
queue, BEFORE the session ever starts.

Kevin, 2026-07-21: "Also add a helper or something to turn ingestion into
smaller task. A god tier goal to task modulator."

Root cause this closes: a goal like "stay busy for 2h43m, research ways
to improve your systems" was handed to the engine as ONE subtask (the
`new_session()` default when nothing pre-decomposes it). It never got
broken down organically — she got stuck retrying a failing tool call
instead of ever proposing NEXT_SUBTASK — hit the per-subtask wall-clock
ceiling, and the whole session ended after ~10 minutes, nowhere near the
requested duration.

Design: call the FAST model (cheap, quick — not the slow big
orchestrator) to break the goal into concrete (description, tier) subtask
specs, reusing agent_session.parse_proposals()'s EXACT
`NEXT_SUBTASK[tier=N]: <desc>` format — the same parser that already
handles organic mid-session decomposition, so this is one format, one
parser, two producers. Additive and optional throughout: if modulation
fails or the goal doesn't look like it needs it, the caller falls back to
the single-subtask shape that already existed. Never a required step,
never a silent behavior change for a normal, already-concrete goal.
"""
from __future__ import annotations

import re

_DURATION_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:ish\s*)?(?:hours?|hrs?|h)\b"
    r"|(\d+)\s*(?:ish\s*)?(?:minutes?|mins?|m)\b",
    re.IGNORECASE,
)

# Cheap, transparent heuristics — no model call needed just to decide
# WHETHER a goal looks open-ended. A real duration mention, or phrasing
# that asks for sustained/exploratory work rather than one concrete step.
_OPEN_ENDED_PHRASES = (
    "stay busy", "keep busy", "for a while", "as long as you can",
    "explore", "research ways", "deep thinking", "however far you can",
    "test yourself", "however long",
)


def extract_target_minutes(goal: str) -> int | None:
    """Pull an explicit duration out of the goal text if one is stated
    ("2 hours and 43 minutes", "90 min") — a plain-language number, not a
    real budget parameter, but a useful signal for how many subtasks to
    plan for. Returns None if nothing duration-shaped is found."""
    total = 0.0
    found = False
    for m in _DURATION_RE.finditer(goal):
        if m.group(1):
            total += float(m.group(1)) * 60
            found = True
        elif m.group(2):
            total += float(m.group(2))
            found = True
    return int(total) if found else None


# work-deadline-args-d (Kevin, 2026-07-25): "/work <goal> <min timeframe/
# deadline to complete task> <maximum deadline to complete task>". A
# STRUCTURED trailing-token form, distinct from extract_target_minutes'
# natural-language-embedded-in-the-goal parsing above — extends it rather
# than replacing it: a token here still just yields minutes, fed through
# the exact same envelope.
_TOKEN_RE = re.compile(
    r"^(?:(\d+(?:\.\d+)?)h)?(?:(\d+)m)?$", re.IGNORECASE,
)


def _parse_duration_token(token: str) -> int | None:
    """'2h', '45m', '2h30m' -> minutes. None if it isn't duration-shaped
    at all (so a normal trailing word in the goal is never misread)."""
    m = _TOKEN_RE.match(token.strip())
    if not m or not (m.group(1) or m.group(2)):
        return None
    hours = float(m.group(1) or 0)
    mins = float(m.group(2) or 0)
    return int(hours * 60 + mins)


def parse_work_args(raw: str) -> tuple[str, int | None, int | None]:
    """Split a raw `/work` argument string into (goal, min_minutes,
    max_minutes). Only the trailing one or two whitespace-separated
    tokens are ever checked against the duration shape ('2h', '45m',
    '2h30m') — anything not shaped like a duration is left as part of the
    goal text, so a goal that happens to end in an ordinary word is never
    misparsed. One trailing duration token is read as the MAX (today's
    single-ceiling meaning, unchanged); two are (min, max) in that order.
    """
    parts = raw.strip().split()
    if not parts:
        return "", None, None

    durations: list[int] = []
    while parts and len(durations) < 2:
        candidate = _parse_duration_token(parts[-1])
        if candidate is None:
            break
        durations.insert(0, candidate)
        parts.pop()

    goal = " ".join(parts)
    if len(durations) == 2:
        return goal, durations[0], durations[1]
    if len(durations) == 1:
        return goal, None, durations[0]
    return raw.strip(), None, None


def suggests_decomposition(goal: str) -> bool:
    """True if this goal looks like it wants a long, open-ended stretch
    of autonomous work rather than one concrete step — a real duration
    mention, or open-ended phrasing. Cheap and transparent; never calls a
    model just to decide whether to call a model."""
    if extract_target_minutes(goal) is not None:
        return True
    low = goal.lower()
    return any(phrase in low for phrase in _OPEN_ENDED_PHRASES)


# goal-modulator-d (Kevin, 2026-07-21): "Every ingestion should be broken
# down into timeframes and end goals, basically." Every subtask this
# produces must carry BOTH an explicit time allocation and a concrete
# "done when" criterion, embedded in its own description text — not just
# a bare description. A genuinely simple, already-concrete goal doesn't
# need to be artificially split; it should come back as ONE subtask with
# its own honest timeframe + done-criterion, not forced into many.
_MODULATE_PROMPT_TEMPLATE = """\
You are turning ONE goal into a queue of concrete, individually completable
subtasks for an autonomous work session — every subtask needs its OWN
timeframe and end goal, not just a description.

GOAL: {goal}

TARGET DURATION: about {target_minutes} minutes total, across all subtasks.

Each subtask must be:
  - Concrete and checkable — someone could tell when it's actually done.
  - Completable well within 25 minutes on its own, even on a slower model.
  - A real, honest step toward the goal — never invented busywork just to
    fill time. If the goal is ALREADY simple and concrete, one subtask is
    correct — do not invent extra steps just to fill the target duration.

Respond with ONLY a list of lines in this exact format, one per subtask,
oldest/first-step first, roughly {suggested_count} subtasks (fewer if the
goal is genuinely simple):
NEXT_SUBTASK[tier=1]: <concrete subtask> (target: ~N min; done when: <clear, checkable criterion>)
NEXT_SUBTASK[tier=1]: <the next concrete subtask> (target: ~N min; done when: <clear, checkable criterion>)

No other text. Tier 1 unless a subtask genuinely needs real writes/shell
access (tier 2) — most research/reading/thinking subtasks are tier 1.
"""


async def modulate_goal(
    goal: str,
    *,
    target_minutes: int | None = None,
    client=None,
    model: str | None = None,
) -> list[tuple[str, int]]:
    """Call the fast model to break `goal` into concrete (description,
    tier) subtask specs. Returns [] on ANY failure (unreachable model,
    empty response, malformed output) — the caller always has a safe,
    already-existing single-subtask fallback; this never raises and never
    blocks a session from starting.
    """
    import asyncio

    from .agent_session import SessionError, parse_proposals
    from .config import SETTINGS
    from .ollama_client import CallKind, OllamaClient

    if target_minutes is None:
        target_minutes = extract_target_minutes(goal) or 60
    # roughly one subtask per 20 minutes of target duration, bounded to a
    # sane range — a plan for 3 hours shouldn't become 200 tiny subtasks,
    # and a plan for 10 minutes doesn't need to be forced into 3.
    suggested_count = max(2, min(12, round(target_minutes / 20)))

    client = client or OllamaClient()
    model = model or SETTINGS.fast_model
    prompt = _MODULATE_PROMPT_TEMPLATE.format(
        goal=goal, target_minutes=target_minutes, suggested_count=suggested_count,
    )

    # modulator-timeout-d (found 2026-07-25, diagnosing a real test hang):
    # this docstring already promised "never blocks a session from
    # starting" -- but OllamaClient.chat() itself has no wall-clock
    # timeout (unlike its own supports_thinking()/list(), which use
    # asyncio.wait_for(..., timeout_seconds=3.0)), so a slow model call
    # could hang indefinitely, silently breaking that exact promise.
    # 45s is generous for a genuinely fast-model planning call, and still
    # bounded -- degrading to the single-subtask fallback beats blocking
    # session start for minutes on this hardware.
    try:
        response = await asyncio.wait_for(
            client.chat(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                tools=None,
                call_kind=CallKind.PLAN,
            ),
            timeout=45.0,
        )
    except Exception:  # noqa: BLE001 — a modulation failure is never fatal
        return []

    text = response.get("message", {}).get("content", "")
    if not text:
        return []

    try:
        specs = parse_proposals(text)
    except SessionError:
        return []  # malformed tier — degrade to the single-subtask fallback
    return specs


__all__ = ["extract_target_minutes", "suggests_decomposition", "modulate_goal"]
