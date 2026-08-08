"""
lessons.py — Distilled lessons.

The existing v0.2.x reflector writes to a separate `lessons` table.
This channel surfaces those lessons as searchable atoms so they
participate in universal_recall. NEW lessons may also be written
through here directly (they go into atoms with type='lessons').

MOS Tier 2.
"""
from __future__ import annotations

from ..channels import ChannelSpec, MemoryChannel, register_channel


@register_channel
class LessonsChannel(MemoryChannel):
    spec = ChannelSpec(
        name="lessons",
        description=(
            "Distilled lessons. Surfaces reflector output to "
            "universal_recall. New lessons can also be added directly."
        ),
        authority_tier=2,
        default_confidence=0.85,
        introduced_in="0.2.14",
        voice="Earned. Each one bought with at least one mistake.",
    )

    def write_lesson(
        self, *,
        rule: str, evidence: str, trigger: str = "",
        confidence: float = 0.85,
    ) -> str:
        return self.write_atom(
            summary=f"LESSON: {rule}",
            content={"rule": rule, "evidence": evidence, "trigger": trigger},
            confidence=confidence,
            actor="lessons-channel",
        )
