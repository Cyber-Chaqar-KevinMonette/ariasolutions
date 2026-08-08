"""
trust.py — Relational trust ledger.

Who/what does Aria trust, in what domain, how much? An entry says:
"trust source X for domain Y at level Z." Aria reads this when
weighting evidence in research synthesis.

This is NOT a social ranking. It is a calibrated weighting system:
"the textbook is more reliable than the forum thread, for this
specific question."

MOS Tier 2.
"""
from __future__ import annotations

from typing import Literal

from ..channels import ChannelSpec, MemoryChannel, register_channel


TrustLevel = Literal["high", "medium", "low", "skeptical"]


@register_channel
class TrustChannel(MemoryChannel):
    spec = ChannelSpec(
        name="trust",
        description=(
            "Source-trust ledger for evidence weighting. Per-source, "
            "per-domain calibration."
        ),
        authority_tier=2,
        default_confidence=0.7,
        introduced_in="0.2.14",
        voice="Calibrated. No tribal markers.",
    )

    def assess(
        self, *,
        source: str, domain: str, level: TrustLevel,
        rationale: str = "",
    ) -> str:
        if level not in ("high", "medium", "low", "skeptical"):
            raise ValueError(f"invalid trust level: {level!r}")
        return self.write_atom(
            summary=f"TRUST[{level}]: {source} for {domain}",
            content={
                "source": source, "domain": domain,
                "level": level, "rationale": rationale,
            },
            actor="trust-channel",
        )
