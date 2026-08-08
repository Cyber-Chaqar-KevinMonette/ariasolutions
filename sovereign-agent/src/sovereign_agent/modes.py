"""Run modes and budgets. Architecture §5."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Mode(StrEnum):
    ONESHOT = "oneshot"  # run task; halt on completion, failure, or budget
    TIMED = "timed"      # run from t1 to t2, picking from backlog
    UNTIL = "until"      # run until is_complete() or budget
    BUSY = "busy"        # always-busy: drain backlog forever, with budgets


# Tier ceiling per mode. The dispatcher rejects any tool above the ceiling.
MODE_TIER_CEILING: dict[Mode, int] = {
    Mode.ONESHOT: 3,  # all tiers, but T3 still requires approval token
    Mode.TIMED: 3,
    Mode.UNTIL: 3,
    Mode.BUSY: 1,     # the load-bearing safety design
}


@dataclass(frozen=True)
class RunBudget:
    max_iterations: int = 25
    max_wall_seconds: int = 1800           # 30 min default per task
    max_tokens: int = 200_000
    max_daily_tokens: int = 2_000_000
    consecutive_fail_limit: int = 3
    reflector_max_tokens_per_task: int = 5_000  # carved out from max_tokens; see audit
    # safe-interval-stop-d: reserved seconds subtracted from max_wall_seconds
    # before a loop's between-iteration check trips. Default 0 preserves every
    # existing caller's behavior exactly (hard limit == effective limit).
    # A caller that wants headroom for its final iteration to finish cleanly
    # before the real deadline sets this explicitly (see effective_wall_limit).
    safety_margin_seconds: int = 0


def effective_wall_limit(budget: RunBudget) -> int:  # safe-interval-stop-d
    """Wall-time ceiling a between-iteration check should trip at.

    `max_wall_seconds` minus `safety_margin_seconds`, floored at 0. Callers
    that never set a margin get back `max_wall_seconds` unchanged. Giving a
    loop's final iteration room to finish before the *real* deadline is what
    makes "stop at the nearest safe point, never mid-task" possible — the
    check that would otherwise fire exactly at the hard limit now fires
    `safety_margin_seconds` earlier instead.
    """
    return max(0, budget.max_wall_seconds - budget.safety_margin_seconds)


class BudgetExceeded(Exception):
    """Raised when any RunBudget bound is hit. Caller should poison-d the task."""

    def __init__(self, kind: str, *, used: int | float, limit: int | float):
        self.kind = kind
        self.used = used
        self.limit = limit
        super().__init__(f"budget '{kind}' exceeded: {used} >= {limit}")
