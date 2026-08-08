"""
╔══════════════════════════════════════════════════════════════════════════╗
║  aegis/defcon.py — the system's incident-response state machine          ║
║                                                                           ║
║  Five named states. Transitions are explicit, audited, and asymmetric:  ║
║  you drop into BLACK automatically; you only climb out manually.        ║
║                                                                           ║
║    GREEN   — normal. All sentinels scan on cadence. Aegis idle.         ║
║    YELLOW  — anomaly, unconfirmed. Affected sentinel scans faster.      ║
║              No operator notification yet.                              ║
║    ORANGE  — confirmed degradation, scope ≤ R1. Aegis authorizes        ║
║              scoped repair via lease. Operator notified async.          ║
║    RED     — confirmed compromise OR scope R2+. Conductor pauses        ║
║              non-essential sentinels, operator alerted synchronously.   ║
║    BLACK   — system integrity in question. All sentinels quiesce.       ║
║              All writes blocked except Aegis Ledger.                    ║
║              Aria's loop halts. Only operator returns to GREEN.         ║
║                                                                           ║
║  Transition rules:                                                       ║
║                                                                           ║
║    Upward transitions (any → higher) are made by the Conductor based   ║
║    on incident classification. They never require operator approval —  ║
║    raising the alert level is always safe.                              ║
║                                                                           ║
║    Downward transitions require explicit operator action, except for   ║
║    YELLOW→GREEN which the Conductor may make autonomously after a      ║
║    quiet period (no new evidence for the YELLOW-triggering incident   ║
║    over a configurable window).                                        ║
║                                                                           ║
║    The asymmetry is the engineering equivalent of "we'd rather be      ║
║    wrong toward safety."                                                ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import IntEnum
from typing import Literal


class Defcon(IntEnum):
    """The five operational states. Lower number = more relaxed."""
    GREEN = 0
    YELLOW = 1
    ORANGE = 2
    RED = 3
    BLACK = 4

    @property
    def label(self) -> str:
        return self.name

    @property
    def writes_blocked(self) -> bool:
        """True if non-Aegis-Ledger writes are blocked in this state."""
        return self == Defcon.BLACK

    @property
    def aria_loop_should_pause(self) -> bool:
        """True if Aria's main loop should yield and wait for Aegis."""
        return self >= Defcon.RED

    @property
    def operator_notification_required(self) -> bool:
        """True if state entry must produce an operator-visible notification."""
        return self >= Defcon.ORANGE

    @property
    def synchronous_notification(self) -> bool:
        """True if the operator must be interrupted (modal-class), False if
        the notification can be async (inbox-class)."""
        return self >= Defcon.RED


def transition_allowed(
    *,
    current: Defcon,
    target: Defcon,
    operator_authorized: bool,
    quiet_period_satisfied: bool = False,
) -> bool:
    """The single source of truth for whether a state change is permitted.

    Upward (current < target): always allowed.
    Downward (current > target):
      - YELLOW → GREEN: allowed if quiet_period_satisfied OR operator_authorized
      - All other downward: operator_authorized required
    No-op (current == target): allowed (idempotent).
    """
    if target == current:
        return True
    if target > current:
        return True
    # Downward transition.
    if current == Defcon.YELLOW and target == Defcon.GREEN:
        return quiet_period_satisfied or operator_authorized
    return operator_authorized


@dataclass(frozen=True)
class DefconTransition:
    """A recorded state change. Goes into the Aegis Ledger."""
    from_state: Defcon
    to_state: Defcon
    reason: str
    triggered_by: str                          # 'conductor', operator id, etc.
    incident_id: str = ""
    transitioned_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%S.%fZ"
        )
    )


__all__ = [
    "Defcon",
    "DefconTransition",
    "transition_allowed",
]
