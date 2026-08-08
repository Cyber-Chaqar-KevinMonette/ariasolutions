"""
core/narration.py — values-aware action narration
v0.2.40 wholeness

Every meaningful action gets a structured narration: intent, state basis,
policy basis, risk note, rollback path, human checkpoint. Renders both
operator-readable text and a machine audit record.

Design choice (revised from initial proposal): values check produces
WARNINGS, not hard exceptions, for low-risk actions (C1-C2). Hard blocks
reserved for C3+. This avoids "honest 'risk: none' for read-only ops"
becoming an exception storm. The warnings still surface — they just don't
crash the workflow.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal, Optional


ActionClass = Literal["C1", "C2", "C3", "C4", "C5"]


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


@dataclass
class ActionNarration:
    """Plain-language explanation record for one action."""
    intent_summary: str
    state_basis: str
    policy_basis: str
    risk_note: str
    rollback_path: str
    human_checkpoint: str
    action_class: ActionClass = "C2"
    tone_register: str = "precise"
    narrated_at: str = field(default_factory=_iso_now)

    def values_check(self) -> list[str]:
        """Return list of warnings. Empty list = clean.

        Warnings, not errors. For C3+ actions, calling code should
        treat warnings as blockers. For C1/C2, they get logged and
        execution proceeds.
        """
        warnings: list[str] = []

        if not self.intent_summary.strip():
            warnings.append("intent_summary is empty — narration must state what action is being taken")

        if not self.risk_note.strip():
            warnings.append("risk_note is empty — even low-risk actions have some failure mode worth naming")

        if not self.rollback_path.strip():
            warnings.append("rollback_path is empty — state 'not reversible' or 'no rollback needed' explicitly")

        # Length sanity — narration that's too long is obscuring, not clarifying.
        if len(self.intent_summary.split()) > 40:
            warnings.append("intent_summary exceeds 40 words — consider simplifying")

        return warnings

    def is_block_severity(self, warnings: list[str]) -> bool:
        """True if these warnings should block execution.

        Rule: C3+ actions block on any warning. C1/C2 only block on
        critical absences (intent_summary or rollback_path empty).
        """
        if self.action_class in ("C3", "C4", "C5"):
            return len(warnings) > 0
        # For C1/C2, only block if intent_summary is completely empty.
        critical = [w for w in warnings if "intent_summary is empty" in w]
        return len(critical) > 0

    def render_operator(self) -> str:
        """Render for operator display."""
        return (
            f"What: {self.intent_summary}\n"
            f"Why now: {self.state_basis}\n"
            f"Authority: {self.policy_basis}\n"
            f"Risk: {self.risk_note}\n"
            f"Undo: {self.rollback_path}\n"
            f"Checkpoint: {self.human_checkpoint}\n"
            f"Class: {self.action_class}"
        )

    def render_audit(self) -> dict:
        """Render as structured audit record."""
        return {
            "intent_summary": self.intent_summary,
            "state_basis": self.state_basis,
            "policy_basis": self.policy_basis,
            "risk_note": self.risk_note,
            "rollback_path": self.rollback_path,
            "human_checkpoint": self.human_checkpoint,
            "action_class": self.action_class,
            "tone_register": self.tone_register,
            "narrated_at": self.narrated_at,
        }


__all__ = ["ActionNarration", "ActionClass"]
