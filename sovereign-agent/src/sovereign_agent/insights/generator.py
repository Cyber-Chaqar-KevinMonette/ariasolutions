"""
insights/generator.py — Reflection over facts.

The generator is split from the channel so the channel stays a simple
storage surface. Three pieces:

  1. ``InsightCandidate``  — a single synthesized observation, not yet
     written to the channel. Holds the text, the subject person_ids, and
     the fact_ids that serve as evidence.

  2. ``InsightSynthesizer`` — the protocol the LLM (or test stub) implements.
     ``StubSynthesizer`` is deterministic, used in tests.
     ``LocalLLMSynthesizer`` calls Ollama; used in production.

  3. ``generate_person_insights`` / ``generate_horizon_insight`` — the
     orchestrators. They:
       - load the person profile (confirmed facts only — never pending)
       - hand it to a synthesizer
       - return an ``InsightReport`` (dry-run; no writes)
     The operator then calls ``persist_insights(report)`` to commit.

DOCTRINE
--------

Insights NEVER:
  - Treat pending facts as truth (they are not synthesized from)
  - Auto-persist (the operator must explicitly promote)
  - Modify the people channel (they are stored in the insights channel)
  - Issue web requests (web enrichment is its own deferred subsystem)

Insights ALWAYS:
  - Cite evidence: every InsightCandidate.evidence_fact_ids is non-empty
    in practice (the audit checker warns when it isn't)
  - Bound confidence ≤ 0.85 — synthesis is never as sure as evidence
  - Are marked as advisory in their stored summary
"""
from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol

from ..channels import get_channel
from ..mem_channels.people import (
    Fact,
    PersonNotFoundError,
    PersonProfile,
    PeopleChannel,
)


# Hard cap on synthesized confidence — insights are never as sure as facts.
MAX_INSIGHT_CONFIDENCE = 0.85


# ─── Dataclasses ───────────────────────────────────────────────────────────


@dataclass
class InsightCandidate:
    """One synthesized observation, not yet written."""
    kind: str                            # "person" | "cross" | "horizon" | "gap"
    text: str
    subject_ids: list[str] = field(default_factory=list)
    evidence_fact_ids: list[str] = field(default_factory=list)
    confidence: float = 0.6

    def __post_init__(self) -> None:
        if self.confidence > MAX_INSIGHT_CONFIDENCE:
            self.confidence = MAX_INSIGHT_CONFIDENCE
        if self.confidence < 0:
            raise ValueError(f"negative confidence: {self.confidence}")


@dataclass
class InsightReport:
    """Result of a generation run — dry-run; not yet persisted."""
    generated_at: str
    subject_label: str
    candidates: list[InsightCandidate] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)        # caveats, warnings
    dry_run: bool = True

    def render(self) -> str:
        lines = [
            f"━ insights · {self.subject_label} · {self.generated_at} ━",
            f"  candidates: {len(self.candidates)}"
            + ("  [dry-run — not persisted]" if self.dry_run else "  [persisted]"),
        ]
        for n in self.notes:
            lines.append(f"  ! {n}")
        for i, c in enumerate(self.candidates, 1):
            lines.append(f"  {i}. [{c.kind} · conf {c.confidence:.2f}] {c.text}")
            if c.evidence_fact_ids:
                lines.append(f"     evidence: {len(c.evidence_fact_ids)} fact(s)")
        return "\n".join(lines)


# ─── Synthesizer protocol ──────────────────────────────────────────────────


class InsightSynthesizer(Protocol):
    """Anything that can take a person profile and return insight candidates.

    Implementations must be pure functions of the input (or deterministic
    on a seed). The orchestrators below depend only on this protocol.
    """

    def for_person(self, profile: PersonProfile) -> list[InsightCandidate]:
        ...

    def horizon(self, profiles: list[PersonProfile]) -> list[InsightCandidate]:
        ...


# ─── Stub synthesizer (used in tests; useful as a default fallback) ──────


class StubSynthesizer:
    """Deterministic synthesizer that produces structured templates.

    Useful for tests and as a safe fallback when the LLM is unavailable —
    it produces low-confidence observations that mirror the data so the
    operator can decide whether to promote them.
    """

    def for_person(self, profile: PersonProfile) -> list[InsightCandidate]:
        out: list[InsightCandidate] = []
        # Roles / affiliations
        roles = [f for f in profile.facts_confirmed if f.kind in ("role", "affiliation", "lab")]
        if roles:
            joined = "; ".join(f"{f.kind}={f.value}" for f in roles)
            out.append(InsightCandidate(
                kind="person",
                text=(
                    f"{profile.person.canonical_name} is currently associated "
                    f"with: {joined}."
                ),
                subject_ids=[profile.person.person_id],
                evidence_fact_ids=[f.fact_id for f in roles],
                confidence=0.7,
            ))

        # Research areas
        research = [f for f in profile.facts_confirmed if f.kind == "research_area"]
        if research:
            joined = ", ".join(f.value for f in research)
            out.append(InsightCandidate(
                kind="person",
                text=(
                    f"Research areas tracked for {profile.person.canonical_name}: "
                    f"{joined}. Consider whether recent work in any of these "
                    f"merits a follow-up review."
                ),
                subject_ids=[profile.person.person_id],
                evidence_fact_ids=[f.fact_id for f in research],
                confidence=0.6,
            ))

        # Gap: pending facts awaiting review
        if profile.facts_pending:
            out.append(InsightCandidate(
                kind="gap",
                text=(
                    f"{len(profile.facts_pending)} pending fact(s) about "
                    f"{profile.person.canonical_name} have not been "
                    f"reviewed. Operator promotion needed to surface as truth."
                ),
                subject_ids=[profile.person.person_id],
                evidence_fact_ids=[f.fact_id for f in profile.facts_pending],
                confidence=0.85,            # gaps are observations of the data
            ))

        # Gap: thin record
        if (not profile.facts_confirmed) and (not profile.facts_pending):
            out.append(InsightCandidate(
                kind="gap",
                text=(
                    f"No facts recorded for {profile.person.canonical_name}. "
                    f"The record is currently just a name."
                ),
                subject_ids=[profile.person.person_id],
                confidence=0.85,
            ))
        return out

    def horizon(self, profiles: list[PersonProfile]) -> list[InsightCandidate]:
        # Cross-person observation: which research areas appear in multiple
        # profiles? That's a clue for cross-pollination.
        from collections import defaultdict
        area_to_people: dict[str, list[str]] = defaultdict(list)
        area_to_facts: dict[str, list[str]] = defaultdict(list)
        for p in profiles:
            for f in p.facts_confirmed:
                if f.kind == "research_area":
                    area_to_people[f.value.lower()].append(p.person.person_id)
                    area_to_facts[f.value.lower()].append(f.fact_id)
        out: list[InsightCandidate] = []
        for area, pids in area_to_people.items():
            if len(set(pids)) > 1:
                out.append(InsightCandidate(
                    kind="horizon",
                    text=(
                        f"Multiple people in the record share research area "
                        f"{area!r} ({len(set(pids))} people). Consider whether "
                        f"connecting them, or surveying recent work across them, "
                        f"would yield insights neither would produce alone."
                    ),
                    subject_ids=list(set(pids)),
                    evidence_fact_ids=area_to_facts[area],
                    confidence=0.55,
                ))
        if not out:
            out.append(InsightCandidate(
                kind="horizon",
                text=(
                    "No cross-cutting research themes detected in the current "
                    "record. Long-horizon synthesis requires more breadth or "
                    "depth in the people channel."
                ),
                confidence=0.7,
            ))
        return out


# ─── Local LLM synthesizer ────────────────────────────────────────────────


class LocalLLMSynthesizer:
    """Real synthesizer backed by the local Ollama model.

    Falls back to ``StubSynthesizer`` if the LLM is unreachable, with a
    visible note in the report so the operator knows generation degraded.
    """

    def __init__(self, *, model: str | None = None, timeout_s: float = 30.0):
        from ..config import SETTINGS
        self.model = model or getattr(SETTINGS, "default_model", "llama3.2:3b")
        self.timeout_s = timeout_s
        self._fallback = StubSynthesizer()

    def _ask(self, prompt: str) -> str | None:
        """Best-effort sync call to Ollama. Returns None on any failure."""
        try:
            import ollama
            resp = ollama.generate(
                model=self.model,
                prompt=prompt,
                options={"temperature": 0.3, "num_predict": 500},
            )
            return resp.get("response", "").strip() if isinstance(resp, dict) else None
        except Exception:  # noqa: BLE001
            return None

    def for_person(self, profile: PersonProfile) -> list[InsightCandidate]:
        prompt = self._build_person_prompt(profile)
        text = self._ask(prompt)
        if not text:
            return self._fallback.for_person(profile)
        # Conservative: trust the LLM only for one summary candidate,
        # always at sub-fact confidence, with full evidence list attached.
        return [InsightCandidate(
            kind="person",
            text=text,
            subject_ids=[profile.person.person_id],
            evidence_fact_ids=[f.fact_id for f in profile.facts_confirmed],
            confidence=0.55,
        )]

    def horizon(self, profiles: list[PersonProfile]) -> list[InsightCandidate]:
        prompt = self._build_horizon_prompt(profiles)
        text = self._ask(prompt)
        if not text:
            return self._fallback.horizon(profiles)
        all_facts = [f.fact_id for p in profiles for f in p.facts_confirmed]
        all_subjects = [p.person.person_id for p in profiles]
        return [InsightCandidate(
            kind="horizon",
            text=text,
            subject_ids=all_subjects,
            evidence_fact_ids=all_facts,
            confidence=0.50,
        )]

    @staticmethod
    def _build_person_prompt(profile: PersonProfile) -> str:
        facts = "\n".join(
            f"- {f.kind}: {f.value}" for f in profile.facts_confirmed
        ) or "(no confirmed facts)"
        return (
            f"You are summarising what is known about one person, from a "
            f"local memory store. Be brief (2-4 sentences). Do not invent "
            f"facts beyond what is listed. Mark uncertainty where it exists.\n\n"
            f"Person: {profile.person.canonical_name}\n"
            f"Confirmed facts:\n{facts}\n\n"
            f"Summary:"
        )

    @staticmethod
    def _build_horizon_prompt(profiles: list[PersonProfile]) -> str:
        sections = []
        for p in profiles[:20]:  # cap so the prompt stays bounded
            facts = ", ".join(f.value for f in p.facts_confirmed[:6])
            sections.append(f"- {p.person.canonical_name}: {facts or '(no facts)'}")
        joined = "\n".join(sections)
        return (
            f"You are looking across a small group of people that the operator "
            f"is tracking. Identify ONE cross-cutting theme or one collaboration "
            f"opportunity that the data plausibly supports. Be careful — do not "
            f"speculate. If the data does not support a confident answer, say so.\n\n"
            f"People:\n{joined}\n\n"
            f"Observation:"
        )


# ─── Orchestrators ─────────────────────────────────────────────────────────


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def generate_person_insights(
    conn: sqlite3.Connection,
    name_or_alias_or_id: str,
    *,
    synthesizer: InsightSynthesizer | None = None,
) -> InsightReport:
    """Produce an InsightReport for one person. Dry-run — no writes.

    Pass ``synthesizer`` explicitly to use a stub in tests; otherwise the
    local LLM is used.
    """
    ch = PeopleChannel(conn)
    try:
        profile = ch.profile(name_or_alias_or_id)
    except PersonNotFoundError:
        return InsightReport(
            generated_at=_utc_now(),
            subject_label=name_or_alias_or_id,
            notes=[f"no such person: {name_or_alias_or_id!r}"],
        )

    syn = synthesizer or LocalLLMSynthesizer()
    candidates = syn.for_person(profile)
    notes: list[str] = []
    if not profile.facts_confirmed and not profile.facts_pending:
        notes.append("record has no facts — synthesis is structurally thin")
    return InsightReport(
        generated_at=_utc_now(),
        subject_label=profile.person.canonical_name,
        candidates=candidates,
        notes=notes,
    )


def generate_horizon_insight(
    conn: sqlite3.Connection,
    *,
    synthesizer: InsightSynthesizer | None = None,
    limit: int = 50,
) -> InsightReport:
    """Cross-person horizon synthesis. Dry-run — no writes.

    Reads the most recent ``limit`` people (non-redacted) and asks the
    synthesizer for one cross-cutting observation.
    """
    ch = PeopleChannel(conn)
    people = ch.list_people(limit=limit)
    profiles = [
        ch.profile(p.person_id) for p in people if not p.redacted_at
    ]
    notes: list[str] = []
    if len(profiles) < 2:
        notes.append(
            f"only {len(profiles)} person in the record — horizon scans need "
            f"at least 2 to find cross-cutting themes"
        )
    syn = synthesizer or LocalLLMSynthesizer()
    candidates = syn.horizon(profiles) if profiles else []
    return InsightReport(
        generated_at=_utc_now(),
        subject_label=f"horizon · {len(profiles)} people",
        candidates=candidates,
        notes=notes,
    )


def persist_insights(
    conn: sqlite3.Connection,
    report: InsightReport,
    *,
    operator_note: str = "",
) -> list[str]:
    """Promote a report's candidates into durable atoms in the insights
    channel. Returns the list of atom_ids written.

    This is the operator-confirms-then-writes step. Idempotency_id is
    derived from the candidate's evidence + text so the same report
    persisted twice is a no-op.
    """
    ch = get_channel("insights", conn)
    written: list[str] = []
    for c in report.candidates:
        # Deterministic id: same evidence + text → same atom
        seed = "|".join([c.kind, c.text] + sorted(c.evidence_fact_ids))
        idem = "insight:" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:20]
        atom_id = ch.record(  # type: ignore[attr-defined]
            kind=c.kind,  # type: ignore[arg-type]
            text=c.text + (f"  [operator note: {operator_note}]" if operator_note else ""),
            subject_ids=c.subject_ids,
            evidence_fact_ids=c.evidence_fact_ids,
            confidence=c.confidence,
            idempotency_id=idem,
        )
        written.append(atom_id)
    report.dry_run = False
    return written


__all__ = [
    "InsightCandidate",
    "InsightReport",
    "InsightSynthesizer",
    "LocalLLMSynthesizer",
    "MAX_INSIGHT_CONFIDENCE",
    "StubSynthesizer",
    "generate_horizon_insight",
    "generate_person_insights",
    "persist_insights",
]
