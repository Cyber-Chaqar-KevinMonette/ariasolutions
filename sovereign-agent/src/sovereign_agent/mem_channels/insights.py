"""
insights.py — Aria's synthesized observations.

A separate channel from people so insights are clearly distinguished from
facts. A fact is what is known about a person. An insight is a synthesis
Aria has produced from facts (and other context) — they are advisory,
never authoritative, and never silently treated as truth.

Insight kinds:
  - 'person'      — synthesis about one person (e.g., "Kevin's recent focus")
  - 'cross'       — synthesis across multiple people (e.g., "researchers
                    interested in topic X")
  - 'horizon'     — long-horizon vision-shaping ("how this research could
                    benefit the future")
  - 'gap'         — something Aria notices is missing or stale

MOS Tier 2 — persistent, references PII but stores no new PII. Insights
reference person_ids; they do not duplicate identity data.

Insights are written via insights/generator.py. This file holds the
channel; the generator holds the policy.
"""
from __future__ import annotations

from typing import Literal

from ..channels import ChannelSpec, MemoryChannel, register_channel


InsightKind = Literal["person", "cross", "horizon", "gap"]


@register_channel
class InsightsChannel(MemoryChannel):
    """Aria's synthesized observations and visions.

    Insights are advisory. They are produced by reflection over facts,
    never written without provenance, and clearly distinguished from
    facts in the people channel.
    """

    spec = ChannelSpec(
        name="insights",
        description=(
            "Synthesized observations and long-horizon visions — advisory, "
            "always provenanced, never confused with facts. Aria's "
            "thinking-out-loud surface for cross-cutting recall."
        ),
        authority_tier=2,
        default_confidence=0.6,           # insights are inferred, not measured
        introduced_in="0.2.16.0",
        voice="Reflective, qualified, never confident beyond evidence.",
    )

    def record(
        self, *,
        kind: InsightKind,
        text: str,
        subject_ids: list[str] | None = None,
        evidence_fact_ids: list[str] | None = None,
        confidence: float | None = None,
        idempotency_id: str | None = None,
    ) -> str:
        """Write one insight atom. Returns the atom_id.

        ``subject_ids`` should list any person_ids the insight references.
        ``evidence_fact_ids`` should list fact_ids whose existence supports
        the insight — this is the audit trail.
        """
        if kind not in ("person", "cross", "horizon", "gap"):
            raise ValueError(f"invalid insight kind: {kind!r}")
        if not text or not text.strip():
            raise ValueError("insight text cannot be empty")
        return self.write_atom(
            summary=f"INSIGHT[{kind}]: {text[:200]}",
            content={
                "kind": kind,
                "text": text,
                "subject_ids": subject_ids or [],
                "evidence_fact_ids": evidence_fact_ids or [],
            },
            idempotency_id=idempotency_id,
            confidence=confidence,
            actor="insights-channel",
        )


__all__ = ["InsightKind", "InsightsChannel"]
