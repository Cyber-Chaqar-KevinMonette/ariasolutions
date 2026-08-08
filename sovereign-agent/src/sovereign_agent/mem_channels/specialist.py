"""
specialist.py — Domain knowledge bundles.

A specialist atom is a focused mini-essay or reference card on one
domain: "how Postgres MVCC works," "OWASP LLM Top 10 mitigations,"
"the basics of Kalman filtering." Aria pulls these in when a domain
trigger fires in a query.

MOS Tier 2 — persistent change, logged.
"""
from __future__ import annotations

from typing import Literal

from ..channels import ChannelSpec, MemoryChannel, register_channel


SpecialistDomain = Literal[
    "security", "ml", "systems", "design", "math",
    "biology", "physics", "law", "finance", "ops",
    "ux", "agents", "memory", "general",
]


@register_channel
class SpecialistChannel(MemoryChannel):
    spec = ChannelSpec(
        name="specialist",
        description=(
            "Domain knowledge bundles. Focused mini-essays / reference "
            "cards that Aria pulls when domain triggers fire."
        ),
        authority_tier=2,
        default_confidence=0.8,
        introduced_in="0.2.14",
        voice="Subject-matter-expert. Cites sources when they exist.",
    )

    def card(
        self,
        *,
        title: str,
        domain: SpecialistDomain,
        body: str,
        sources: list[str] | None = None,
    ) -> str:
        return self.write_atom(
            summary=f"[{domain}] {title}",
            content={"title": title, "domain": domain, "body": body,
                     "sources": sources or []},
            actor="specialist-channel",
        )
