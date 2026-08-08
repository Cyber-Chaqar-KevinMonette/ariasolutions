"""
identity.py — Aria's durable self-model.

The slowest-moving channel. Aria's identity atoms are her stance, her
ongoing commitments to the operator, her current mood, her self-narrative.
Updated by reflection — never by every interaction.

MOS Authority Tier 3 — identity changes are consequential. The operator
must confirm at the CLI before any identity edit lands.

The MOS Ω-Axiom A6 — "Layered Identity (Core vs Strategy)" — says: hold
a small immutable core; keep strategies flexible. This channel holds
the small core. The personas channel holds the strategy.
"""
from __future__ import annotations

import sqlite3
from typing import Literal

from ..channels import ChannelSpec, MemoryChannel, register_channel


IdentityKind = Literal["stance", "commitment", "mood", "self-narrative", "value"]


@register_channel
class IdentityChannel(MemoryChannel):
    spec = ChannelSpec(
        name="identity",
        description=(
            "Aria's durable self-model: stance, commitments, mood, "
            "self-narrative, values. Slow-moving. Tier 3."
        ),
        authority_tier=3,
        default_confidence=0.95,
        requires_idempotency=True,
        introduced_in="0.2.14",
        voice="Quiet, settled, sure. Aria knows herself.",
    )

    def declare(
        self,
        *,
        kind: IdentityKind,
        text: str,
        idempotency_id: str,
        rationale: str = "",
    ) -> str:
        """Declare an identity element. Returns atom_id."""
        if kind not in ("stance", "commitment", "mood", "self-narrative", "value"):
            raise ValueError(f"invalid identity kind: {kind!r}")
        return self.write_atom(
            summary=f"IDENTITY[{kind}]: {text}",
            content={"kind": kind, "text": text, "rationale": rationale},
            idempotency_id=idempotency_id,
            actor="aria-self",
        )

    def current(self, kind: IdentityKind | None = None) -> list[dict]:
        """Return the current (non-superseded) identity atoms."""
        out = []
        for a in self.list_atoms(limit=100):
            content = self.hydrate(a["atom_id"])
            if kind and content.get("kind") != kind:
                continue
            a["content"] = content
            out.append(a)
        return out


__all__ = ["IdentityChannel", "IdentityKind"]
