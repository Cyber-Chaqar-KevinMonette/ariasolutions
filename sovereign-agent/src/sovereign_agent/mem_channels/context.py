"""
context.py — Current operational context.

Short-lived (hours-to-days) atoms about what's happening NOW: which
project is active, what the operator's mood is, what blockers are in
play. Aria reads this on every recall to ground responses in the
right frame.

MOS Tier 1 — reversible writes, bounded scope.
"""
from __future__ import annotations

from ..channels import ChannelSpec, MemoryChannel, register_channel


@register_channel
class ContextChannel(MemoryChannel):
    spec = ChannelSpec(
        name="context",
        description=(
            "Short-lived operational context: active project, current "
            "blockers, recent operator state. Hours-to-days lifetime."
        ),
        authority_tier=1,
        default_confidence=0.6,         # context is a guess, not a fact
        introduced_in="0.2.14",
        voice="Present-tense, situational. The here-and-now layer.",
    )

    def note(self, *, observation: str, source: str = "operator-input") -> str:
        return self.write_atom(
            summary=observation,
            content={"source": source},
            actor="context-channel",
        )
