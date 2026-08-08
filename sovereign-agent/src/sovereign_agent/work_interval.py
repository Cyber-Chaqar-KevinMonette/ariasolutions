"""work_interval.py — safe interval-stop for autonomous work mode (Workstream N).

Composes three primitives that already existed in this codebase, rather than
inventing new architecture:

  - `modes.RunBudget` / `modes.effective_wall_limit` — the safety-margined
    between-iteration wall-clock check (see modes.py's `safety_margin_seconds`
    field). Callers already check budgets only between iterations/subtasks,
    never mid-tool-call (`loop.py::_check_budget`, `agent_session.py::
    _check_session_budget`) — this module just gives that existing check
    room to trip *before* the real deadline instead of exactly at it.
  - `autonomy.session.AutonomySession` — the lease/checkpoint/approval shape:
    `expire_if_due()` pauses with a resumable `{done, next}` checkpoint,
    `resume()` requires explicit `approved=True`.
  - `interrupts.py` — the single human-facing "explicit, separately-
    timestamped approval" gate: `request_resume()` / `consume_resume()`.

Kevin's ask: work mode's autonomous intervals (~1 hour, while a human is
watching) must always stop at a clean, safe boundary — never mid-task — and
must never resume without an explicit human approval action. Every piece
below already existed with the right shape; this module is the composition.
"""
from __future__ import annotations

from dataclasses import dataclass

from .autonomy.session import (
    AutonomySession,
    expire_if_due,
    pause,
    propose_session,
    resume as _autonomy_resume,
    start_block,
    time_remaining,
    within_lease,
)
from .interrupts import consume_resume, request_resume  # noqa: F401 — re-exported
from .modes import RunBudget, effective_wall_limit  # noqa: F401 — re-exported

DEFAULT_WORK_INTERVAL_SECONDS = 3600          # Kevin's "~1 hour at a time"
DEFAULT_SAFETY_MARGIN_SECONDS = 360           # 10% of the default interval
MIN_SAFETY_MARGIN_SECONDS = 60                # floor: always leave at least a minute


@dataclass(frozen=True)
class WorkIntervalConfig:
    """How long an autonomous work-mode block runs before it must pause."""
    interval_seconds: int = DEFAULT_WORK_INTERVAL_SECONDS
    safety_margin_seconds: int = DEFAULT_SAFETY_MARGIN_SECONDS

    def __post_init__(self) -> None:
        margin = max(self.safety_margin_seconds, MIN_SAFETY_MARGIN_SECONDS)
        object.__setattr__(self, "safety_margin_seconds", margin)

    def as_run_budget(self, **overrides) -> RunBudget:
        """A RunBudget shaped for this interval. Wall-clock is what this
        workstream cares about; iteration/token ceilings default to
        RunBudget's own defaults unless overridden by the caller."""
        return RunBudget(
            max_wall_seconds=self.interval_seconds,
            safety_margin_seconds=self.safety_margin_seconds,
            **overrides,
        )


def start_work_interval(
    plan_id: str, *, config: WorkIntervalConfig | None = None, approved: bool
) -> AutonomySession:
    """Begin one bounded, observable work-mode block. Requires explicit
    human approval — mirrors AutonomySession.start_block (Option-1 style),
    consistent with the standing doctrine that autonomy never self-starts."""
    config = config or WorkIntervalConfig()
    proposal = propose_session(plan_id, ttl_seconds=config.interval_seconds)
    session = AutonomySession(**proposal["session"])
    return start_block(session, approved=approved)


def interval_boundary_reached(
    session: AutonomySession, config: WorkIntervalConfig | None = None
) -> bool:
    """True once the SAFETY-MARGINED boundary has passed — earlier than the
    session's own hard `expires_at`, giving the current step room to finish
    cleanly. Callers check this at the SAME safe point they already check
    `_check_budget`/`_check_session_budget`: between iterations or between
    subtasks, never mid-tool-call."""
    config = config or WorkIntervalConfig()
    if session.status != "active":
        return False
    return time_remaining(session) <= config.safety_margin_seconds


def stop_at_safe_point(
    session: AutonomySession, *, done: str, next_up: str, notes: str = ""
) -> AutonomySession:
    """Seal the current, safe stopping point into a resumable checkpoint.
    Only call once the caller's own loop has confirmed it is between
    iterations/subtasks — never from inside a tool call. Reuses
    AutonomySession.pause() verbatim so the checkpoint shape (`{done, next,
    notes, paused_at}`) is identical to the one AutonomySession already
    produces elsewhere in the codebase."""
    return pause(session, done=done, next_up=next_up, notes=notes)


def resume_work_interval(
    session: AutonomySession, *, approved: bool = False
) -> AutonomySession:
    """The single resume gate. Refuses unless EITHER an explicit
    `approved=True` was passed (the direct, in-process approval path — e.g.
    a cockpit button handler that just received an operator click) OR
    `interrupts.consume_resume()` reports the operator separately called
    `request_resume()` (the file-flag approval path already shared with
    `run_session`). No code path may resume a paused interval on elapsed
    time alone — a pause is a pause until a human acts, no matter how long
    it's been since it started."""
    if not approved:
        approved, _ = consume_resume()
    return _autonomy_resume(session, approved=approved)


__all__ = [
    "WorkIntervalConfig",
    "DEFAULT_WORK_INTERVAL_SECONDS",
    "DEFAULT_SAFETY_MARGIN_SECONDS",
    "MIN_SAFETY_MARGIN_SECONDS",
    "start_work_interval",
    "interval_boundary_reached",
    "stop_at_safe_point",
    "resume_work_interval",
    "request_resume",
    "within_lease",
    "expire_if_due",
]
