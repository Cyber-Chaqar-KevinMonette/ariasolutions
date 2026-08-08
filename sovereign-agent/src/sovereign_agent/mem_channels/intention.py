"""
intention.py — Declared intent vs. observed outcome.

Aria says "I will do X." The intention atom records that. Later, an
outcome atom records what actually happened. Comparing the two over
time is how Aria learns where her predictions are calibrated and where
they aren't.

This is the calibration loop for MOS Behavioral Law 5.

MOS Tier 1.
"""
from __future__ import annotations

from typing import Literal

from ..channels import ChannelSpec, MemoryChannel, register_channel


IntentionStatus = Literal["declared", "completed", "abandoned", "deferred"]


@register_channel
class IntentionChannel(MemoryChannel):
    spec = ChannelSpec(
        name="intention",
        description=(
            "Declared intent paired with observed outcome. The "
            "calibration loop for Aria's predictions."
        ),
        authority_tier=1,
        default_confidence=0.7,
        introduced_in="0.2.14",
        voice="Forward-looking. Honest about what was planned vs. delivered.",
    )

    def declare(self, *, intention: str, expected_by: str = "") -> str:
        return self.write_atom(
            summary=f"INTENT: {intention}",
            content={
                "intention": intention,
                "expected_by": expected_by,
                "status": "declared",
            },
            actor="intention-channel",
        )

    def reconcile(
        self, *, intention_atom_id: str, outcome: str,
        new_status: IntentionStatus,
    ) -> str:
        """Pair an outcome with a previously-declared intention."""
        if new_status not in ("declared", "completed", "abandoned", "deferred"):
            raise ValueError(f"invalid status: {new_status!r}")
        return self.write_atom(
            summary=f"OUTCOME[{new_status}]: {outcome}",
            content={"outcome": outcome, "status": new_status},
            parents=[intention_atom_id],
            actor="intention-channel",
        )
