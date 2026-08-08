"""
personalities.py — Persona usage records.

The v0.2.13 persona registry (`personas.py`) holds the static persona
definitions. This channel records the *use* of personas: which one
was active for which task, how it landed.

Reading this lets Aria see "the Master Architect persona has been
active for 12 of the last 15 build sessions" — and adjust if the
ratio drifts unhealthy.

MOS Tier 1.
"""
from __future__ import annotations

from ..channels import ChannelSpec, MemoryChannel, register_channel


@register_channel
class PersonalitiesChannel(MemoryChannel):
    spec = ChannelSpec(
        name="personalities",
        description=(
            "Records of which persona was active for which task. The "
            "static persona registry lives in personas.py; this channel "
            "tracks usage."
        ),
        authority_tier=1,
        default_confidence=0.85,
        introduced_in="0.2.14",
        voice="Observational, light. The chorus, not the soloist.",
    )

    def log_use(
        self, *,
        persona: str, task: str, landed_well: bool = True,
    ) -> str:
        return self.write_atom(
            summary=f"PERSONA USE: {persona} for {task}",
            content={
                "persona": persona, "task": task,
                "landed_well": landed_well,
            },
            actor="personalities-channel",
        )
