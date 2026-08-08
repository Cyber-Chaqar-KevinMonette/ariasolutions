"""
ritual.py — Repeated patterns the operator uses.

"When starting a new build, do X first." "After every shipment,
update the changelog." Ritual atoms are recipes Aria can offer when
the trigger fires.

MOS Tier 2 — persistent, but no external side effects.
"""
from __future__ import annotations

from ..channels import ChannelSpec, MemoryChannel, register_channel


@register_channel
class RitualChannel(MemoryChannel):
    spec = ChannelSpec(
        name="ritual",
        description=(
            "Repeated patterns and recipes. 'When trigger T, do steps S.' "
            "Aria offers these when triggers fire."
        ),
        authority_tier=2,
        default_confidence=0.7,
        introduced_in="0.2.14",
        voice="Procedural, pragmatic. Earned by repetition.",
    )

    def recipe(self, *, trigger: str, steps: list[str], note: str = "") -> str:
        return self.write_atom(
            summary=f"RITUAL on {trigger}: {len(steps)} step(s)",
            content={"trigger": trigger, "steps": steps, "note": note},
            actor="ritual-channel",
        )
