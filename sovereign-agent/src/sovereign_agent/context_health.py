"""context_health.py — 0-100% context-window and run-budget gauges.

Kevin, 2026-08-02: "give aria a token optimizing system... show the
metrics for 0-100% when i need to compact and the metrics for when i
need to /clear-session." Two real, already-instrumented ceilings exist
in this codebase and just weren't surfaced as percentages:

  1. num_ctx (16,384, config.py) — the local model's actual context
     window. prompt_diet.py's own docstring already diagnosed this as a
     real overflow risk (8K system prompt + up to 40K tool schemas blew
     an 8K-ctx model's window outright). `token-usage-d` events
     (loop.py) already carry `prompt_tokens` — the LAST single request's
     real prompt size — the number to compare against num_ctx.
  2. RunBudget.max_tokens (200,000 default, modes.py) — the cumulative
     per-task spend ceiling. The same `token-usage-d` event's
     `running_total` field is exactly that running spend.

This module is pure and deterministic — no I/O, no model calls — the
same "compute a health verdict from numbers you're handed" shape as
resilience.py's CircuitBreaker. Two callers use it: cockpit/app.py's
status bar (human-facing) and tools/context_status.py (Aria's own
introspection) — one set of thresholds, not two.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Level = Literal["ok", "warn", "critical"]

# Context window (prompt_tokens / num_ctx) — how close the NEXT call is
# to actually truncating.
WINDOW_WARN_PCT = 60.0
WINDOW_CRITICAL_PCT = 85.0

# Run budget (running_total / max_tokens) — how much of this task's
# cumulative allowance has been spent.
BUDGET_WARN_PCT = 70.0
BUDGET_CRITICAL_PCT = 90.0

_WINDOW_MESSAGES: dict[Level, str] = {
    "ok": "context window healthy",
    "warn": "approaching the context window — consider compacting",
    "critical": "compact now — the next call may get truncated",
}
_BUDGET_MESSAGES: dict[Level, str] = {
    "ok": "run budget healthy",
    "warn": "this task is getting expensive",
    "critical": "consider /clear-session and starting fresh",
}


@dataclass(frozen=True)
class ContextHealth:
    window_fill_pct: float
    window_level: Level
    budget_fill_pct: float
    budget_level: Level
    recommendation: str

    def as_dict(self) -> dict:
        return {
            "window_fill_pct": self.window_fill_pct,
            "window_level": self.window_level,
            "budget_fill_pct": self.budget_fill_pct,
            "budget_level": self.budget_level,
            "recommendation": self.recommendation,
        }


def _pct(used: int, ceiling: int) -> float:
    if ceiling <= 0:
        return 0.0
    return round(min(100.0, max(0.0, (used / ceiling) * 100.0)), 1)


def _level(pct: float, *, warn: float, critical: float) -> Level:
    if pct >= critical:
        return "critical"
    if pct >= warn:
        return "warn"
    return "ok"


_LEVEL_RANK: dict[Level, int] = {"ok": 0, "warn": 1, "critical": 2}


def assess(prompt_tokens: int, running_total: int, *,
          num_ctx: int, max_tokens: int) -> ContextHealth:
    """Compute both gauges from raw numbers — no I/O. Callers own where
    those numbers come from (the cockpit's own token-usage-d event
    tracking, or context_status.py's tool-side read of the same event
    log)."""
    window_pct = _pct(max(0, prompt_tokens), num_ctx)
    budget_pct = _pct(max(0, running_total), max_tokens)
    window_level = _level(window_pct, warn=WINDOW_WARN_PCT, critical=WINDOW_CRITICAL_PCT)
    budget_level = _level(budget_pct, warn=BUDGET_WARN_PCT, critical=BUDGET_CRITICAL_PCT)

    # The more urgent signal wins the headline recommendation; window
    # wins ties since an overflowing window is the more immediate risk
    # (truncation happens on the very next call, vs. budget exhaustion
    # which just stops future iterations).
    if _LEVEL_RANK[window_level] >= _LEVEL_RANK[budget_level]:
        recommendation = _WINDOW_MESSAGES[window_level]
    else:
        recommendation = _BUDGET_MESSAGES[budget_level]

    return ContextHealth(
        window_fill_pct=window_pct, window_level=window_level,
        budget_fill_pct=budget_pct, budget_level=budget_level,
        recommendation=recommendation,
    )


__all__ = [
    "ContextHealth", "assess", "Level",
    "WINDOW_WARN_PCT", "WINDOW_CRITICAL_PCT",
    "BUDGET_WARN_PCT", "BUDGET_CRITICAL_PCT",
]
