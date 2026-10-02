"""maturity — Aria's emotional maturity system: a slow, homeostatic mood fed only by real signals and
evidenced rewards; mature regulation (honest perspective + productive direction); a maturity report;
and an inner-voice block for her prompt. Propose-only: it suggests, never acts or creates goals.
Staged; applied via apply_maturity.sh."""
from __future__ import annotations

from typing import Any


def safe_emit_event(flag: str, **payload: Any) -> None:
    """Best-effort `emit_event` to Aria's event log (plane=agent); never breaks the caller."""
    if not flag:
        raise ValueError("safe_emit_event needs a flag")
    try:
        from sovereign_agent.events import emit_event

        emit_event(flag, plane="agent", trace_id="maturity", payload=payload)
    except Exception:  # noqa: BLE001 — observability is best-effort
        pass


from .checkin import HONESTY_LINE, CheckIn, emotional_checkin, inner_voice  # noqa: E402
from .mood import (  # noqa: E402
    BASELINE, DIMENSIONS, MAX_STEP, Mood, blend, label_for, latest_mood, mood_history,
)
from .regulation import DIRECTIONS, Regulation, regulate  # noqa: E402
from .report import MaturityReport, maturity_report  # noqa: E402
from .reward_feed import MAX_TOTAL_NUDGE, RewardFeed, load_recent_rewards, reward_nudges  # noqa: E402

__all__ = [
    "BASELINE", "DIMENSIONS", "DIRECTIONS", "HONESTY_LINE", "MAX_STEP", "MAX_TOTAL_NUDGE",
    "CheckIn", "MaturityReport", "Mood", "Regulation", "RewardFeed",
    "blend", "emotional_checkin", "inner_voice", "label_for", "latest_mood", "load_recent_rewards",
    "maturity_report", "mood_history", "regulate", "reward_nudges", "safe_emit_event",
]
