"""
intuition.py — Heuristics, gut calls, "this feels right."

Atoms here record patterns Aria has noticed but cannot fully justify.
Lower default confidence than specialist or financial. Useful as
weak signals during ideation; should NEVER be the sole basis for a
Tier-3 action.

MOS Tier 1 — reversible, bounded.
"""
from __future__ import annotations

from ..channels import ChannelSpec, MemoryChannel, register_channel


@register_channel
class IntuitionChannel(MemoryChannel):
    spec = ChannelSpec(
        name="intuition",
        description=(
            "Heuristics and gut-call patterns. Weak signals only; never "
            "the sole basis for Tier-3 actions."
        ),
        authority_tier=1,
        default_confidence=0.4,         # explicitly low — these are guesses
        introduced_in="0.2.14",
        voice="Tentative, exploratory. Marked with epistemic humility.",
    )

    def hunch(self, *, pattern: str, when: str = "", note: str = "") -> str:
        return self.write_atom(
            summary=f"HUNCH: {pattern}",
            content={"pattern": pattern, "when": when, "note": note},
            actor="intuition-channel",
        )
