"""ledger.py — the Epistemic organ: what Aria currently believes, with what
confidence, traceable to evidence, plus an explicit registry of known-unknowns.

Not a new memory system — she already has atoms/palace/calibration-adjacent pieces.
This is a thin ledger that REFERENCES existing evidence (atom ids, ledger rows,
file paths) rather than duplicating storage. Two stores, both append-only NDJSON
with atomic writes, mirroring ApplyQueueStore's (Workstream C) exact idiom:

  - EpistemicLedger      — Belief records. Revision never mutates history
    (palimpsest discipline, per the canon): revise() appends a NEW belief with
    revised_from set to the old belief's id. The old belief stays readable
    forever; current_beliefs() surfaces only the tip of each lineage.
  - UncertaintyRegistry  — {domain, question, why_unknown} entries, opened and
    later closed with a resolution. Nothing is ever deleted.
"""
from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


# ─── beliefs ────────────────────────────────────────────────────────────────


@dataclass
class Belief:
    belief_id: str
    claim: str
    confidence: float                          # 0.0-1.0
    evidence_refs: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=_now)
    revised_from: str | None = None            # id of the belief this supersedes
    revision_reason: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


class EpistemicLedger:
    """Append-only NDJSON store of beliefs. Mirrors ApplyQueueStore's atomic-
    write discipline: write a line, fsync, never rewrite history."""

    def __init__(self, root: Path | None = None) -> None:
        if root is None:
            from sovereign_agent.config import SETTINGS
            root = SETTINGS.paths.data_dir / "epistemic"
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.log = self.root / "beliefs.ndjson"

    def _append(self, belief: Belief) -> None:
        line = json.dumps(belief.as_dict(), separators=(",", ":")) + "\n"
        with open(self.log, "a", encoding="utf-8") as fh:
            fh.write(line)
            fh.flush()
            os.fsync(fh.fileno())

    def record(self, claim: str, confidence: float, *, evidence_refs: list[str] | None = None) -> Belief:
        """Record a new, independent belief (no prior lineage)."""
        belief = Belief(
            belief_id=_new_id("belief"), claim=claim, confidence=confidence,
            evidence_refs=list(evidence_refs or []),
        )
        self._append(belief)
        return belief

    def revise(self, belief_id: str, new_claim: str, reason: str, *,
               confidence: float | None = None, evidence_refs: list[str] | None = None) -> Belief:
        """Append a NEW belief that supersedes `belief_id`. The old belief is
        never touched — it stays readable via all_beliefs(). Raises if
        belief_id doesn't exist, so a revision always has a real target."""
        old = self.get(belief_id)
        if old is None:
            raise ValueError(f"no such belief: {belief_id!r}")
        new = Belief(
            belief_id=_new_id("belief"),
            claim=new_claim,
            confidence=old.confidence if confidence is None else confidence,
            evidence_refs=list(evidence_refs) if evidence_refs is not None else list(old.evidence_refs),
            revised_from=belief_id,
            revision_reason=reason,
        )
        self._append(new)
        return new

    def all_beliefs(self) -> list[Belief]:
        """Every belief ever recorded, oldest first — full lineage, nothing hidden."""
        out: list[Belief] = []
        # read-repair-d — counted skips, never a wedge, never a crash
        from sovereign_agent.read_repair import read_ndjson_tolerant

        for rec in read_ndjson_tolerant(self.log, store="epistemic-beliefs").records:
            try:
                out.append(Belief(**rec))
            except TypeError:
                continue
        return out

    def get(self, belief_id: str) -> Belief | None:
        for b in self.all_beliefs():
            if b.belief_id == belief_id:
                return b
        return None

    def lineage(self, belief_id: str) -> list[Belief]:
        """The full revision chain ending at belief_id, oldest first."""
        by_id = {b.belief_id: b for b in self.all_beliefs()}
        chain: list[Belief] = []
        current = by_id.get(belief_id)
        while current is not None:
            chain.append(current)
            current = by_id.get(current.revised_from) if current.revised_from else None
        return list(reversed(chain))

    def current_beliefs(self) -> list[Belief]:
        """Only the tip of each lineage — beliefs nothing else revises."""
        all_b = self.all_beliefs()
        superseded = {b.revised_from for b in all_b if b.revised_from}
        return [b for b in all_b if b.belief_id not in superseded]

    # grounding-wing-d — extension seam: `lineage()` already exposes the full
    # revision chain for any belief; a future belief-revision-quality
    # metric (how often a revision genuinely corrects vs. merely compounds
    # an earlier error — e.g. confidence trending up vs. down across a
    # lineage) could be built entirely by reading that chain, no new
    # storage or schema change required.


# ─── uncertainty registry ────────────────────────────────────────────────────


@dataclass
class Uncertainty:
    uncertainty_id: str
    domain: str
    question: str
    why_unknown: str
    opened_at: str = field(default_factory=_now)
    closed_at: str | None = None
    resolution: str = ""

    @property
    def is_open(self) -> bool:
        return self.closed_at is None

    def as_dict(self) -> dict:
        return asdict(self)


class UncertaintyRegistry:
    """Append-only NDJSON store of known-unknowns. open() records a new
    question; close() appends an updated record (never mutates the original
    open event) marking it resolved."""

    def __init__(self, root: Path | None = None) -> None:
        if root is None:
            from sovereign_agent.config import SETTINGS
            root = SETTINGS.paths.data_dir / "epistemic"
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.log = self.root / "uncertainties.ndjson"

    def _append(self, u: Uncertainty) -> None:
        line = json.dumps(u.as_dict(), separators=(",", ":")) + "\n"
        with open(self.log, "a", encoding="utf-8") as fh:
            fh.write(line)
            fh.flush()
            os.fsync(fh.fileno())

    def open(self, domain: str, question: str, why_unknown: str) -> Uncertainty:
        u = Uncertainty(
            uncertainty_id=_new_id("unc"), domain=domain, question=question,
            why_unknown=why_unknown,
        )
        self._append(u)
        return u

    def close(self, uncertainty_id: str, resolution: str) -> Uncertainty:
        existing = self._state().get(uncertainty_id)
        if existing is None:
            raise ValueError(f"no such uncertainty: {uncertainty_id!r}")
        closed = Uncertainty(
            uncertainty_id=existing.uncertainty_id, domain=existing.domain,
            question=existing.question, why_unknown=existing.why_unknown,
            opened_at=existing.opened_at, closed_at=_now(), resolution=resolution,
        )
        self._append(closed)
        return closed

    def _state(self) -> dict[str, Uncertainty]:
        """Reduce the append-only log: last record per id wins (so a close()
        event overrides the original open() record for that id)."""
        state: dict[str, Uncertainty] = {}
        # read-repair-d — counted skips, never a wedge, never a crash
        from sovereign_agent.read_repair import read_ndjson_tolerant

        for rec in read_ndjson_tolerant(self.log, store="uncertainties").records:
            try:
                u = Uncertainty(**rec)
            except TypeError:
                continue
            state[u.uncertainty_id] = u
        return state

    def list_open(self) -> list[Uncertainty]:
        return [u for u in self._state().values() if u.is_open]

    def list_all(self) -> list[Uncertainty]:
        return list(self._state().values())
