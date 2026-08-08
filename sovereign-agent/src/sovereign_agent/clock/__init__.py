"""Clock package — Aria's time grounding.

The ErebloClock polls a SQLite-backed timer table and dispatches due
timers to registered handlers. Kill switch: SOV_NO_TIMERS=1.
"""
from sovereign_agent.clock.timers import (
    ErebloClock, Timer, TimerKind, TimerStatus, TimerHandler,
    KILL_SWITCH_ENV,
)

__all__ = [
    "ErebloClock",
    "Timer", "TimerKind", "TimerStatus", "TimerHandler",
    "KILL_SWITCH_ENV",
]
