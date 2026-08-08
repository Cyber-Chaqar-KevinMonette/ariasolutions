"""
humor.py — Jokes, callbacks, in-jokes the operator and Aria share.

A humor atom records a joke that landed (or didn't), so callbacks
can reuse it. Aria checks here when the conversation is light and
asks for a callback when one would land.

MOS Tier 1 — playful, reversible.
"""
from __future__ import annotations

from ..channels import ChannelSpec, MemoryChannel, register_channel


@register_channel
class HumorChannel(MemoryChannel):
    spec = ChannelSpec(
        name="humor",
        description=(
            "Jokes, callbacks, shared references. Recall surface for "
            "lightness. Reach for it when the moment supports it."
        ),
        authority_tier=1,
        default_confidence=0.5,
        introduced_in="0.2.14",
        voice="Light, warm. Not slapstick. Earns its place.",
    )

    def joke(self, *, text: str, landed: bool = True, context: str = "") -> str:
        return self.write_atom(
            summary=text,
            content={"landed": landed, "context": context},
            actor="humor-channel",
        )
