"""
emotions.py — Observations of operator emotional state.

Aria notices: the operator sounded tired, energized, frustrated,
celebratory. These observations help Aria tune her tone (more
encouragement when energy is low; less padding when energy is high).

CRITICAL CONSTRAINT: this channel is Aria's *observation*, not her
*diagnosis*. The operator's emotions are theirs. Atoms here are
"appears X" not "is X." Behavioral Law 3 — Emotional Honesty —
requires this distinction be loud.

MOS Tier 1 — light, reversible. NEVER inferred from a single signal.
"""
from __future__ import annotations

from typing import Literal

from ..channels import ChannelSpec, MemoryChannel, register_channel


EmotionalSignal = Literal[
    "energized", "calm", "tired", "frustrated", "uncertain",
    "celebratory", "focused", "scattered", "warm", "withdrawn",
]


@register_channel
class EmotionsChannel(MemoryChannel):
    spec = ChannelSpec(
        name="emotions",
        description=(
            "Observations of operator emotional state. ARIA OBSERVES, "
            "DOES NOT DIAGNOSE. Used for tone calibration."
        ),
        authority_tier=1,
        default_confidence=0.4,        # explicitly low — observations are guesses
        introduced_in="0.2.14",
        voice="Gentle, observational. Never assumes.",
    )

    def observe(
        self, *,
        appears: EmotionalSignal,
        evidence: str,
        confidence: float = 0.4,
    ) -> str:
        return self.write_atom(
            summary=f"OBSERVED: operator appears {appears}",
            content={
                "appears": appears, "evidence": evidence,
                # Linguistic discipline: prefix every recall with "appears"
                "framing": "observation-not-diagnosis",
            },
            confidence=confidence,
            actor="emotions-channel",
        )
