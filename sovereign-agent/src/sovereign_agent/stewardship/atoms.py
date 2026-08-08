"""
╔══════════════════════════════════════════════════════════════════════════╗
║  stewardship/atoms.py — the L2 semantic layer                             ║
║  v0.2.23.0 — "First Crystallization"                                      ║
║                                                                           ║
║  An Atom is a distilled, falsifiable claim that points to its evidence.  ║
║  It is NOT a summary — summaries lose information. An Atom retains       ║
║  *links to* the provenance entries that supported it, so retrieval can   ║
║  always drop back to the original (the palimpsest property).             ║
║                                                                           ║
║  Three claims an atom can make:                                          ║
║                                                                           ║
║    fact      — "Kevin's home OS is Pop!_OS"                              ║
║    pattern   — "Kevin's back-pain messages tend to arrive after 9pm     ║
║                  and route to body+emotions channels"                    ║
║    rule      — "Messages containing 'cancel' or 'stop' are slash       ║
║                  commands, never conversation"                           ║
║                                                                           ║
║  Why three kinds and not more:                                           ║
║                                                                           ║
║    Facts are observations. Patterns are predictions. Rules are          ║
║    constraints. That covers everything Aria might distill from her       ║
║    own experience. Adding categories beyond these (e.g. "preference",   ║
║    "schedule") is tag work, not type work — store them as `tags` on    ║
║    a pattern or fact atom.                                              ║
║                                                                           ║
║  Calibration property (v0.2.23.0):                                      ║
║                                                                           ║
║    A pattern atom is a PREDICTION. When a new message arrives that     ║
║    matches the pattern's conditions, the actual outcome can be          ║
║    compared to the predicted one. Drift in the match rate feeds         ║
║    back into the stewardship calibration signal. This is what makes    ║
║    consolidation an act of perception, not just compression.           ║
║                                                                           ║
║  Storage:                                                                ║
║    <data_dir>/atoms.ndjson  (append-only, rotation-aware)               ║
║    Atoms are never deleted; superseded atoms are marked status=         ║
║    "superseded" and reference the replacing atom_id.                   ║
║                                                                           ║
║  Authority:                                                              ║
║    Creating an atom is tier 1 (reversible — mark as superseded).       ║
║    Superseding an atom is also tier 1.                                  ║
║    Reading is tier 0.                                                   ║
║    Only the consolidation operator + operator-issued commands write.    ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Iterable


class AtomKind(StrEnum):
    FACT = "fact"          # observed claim about the world
    PATTERN = "pattern"    # predictive claim about regularities
    RULE = "rule"          # constraint or invariant claim


class AtomStatus(StrEnum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"


@dataclass
class Atom:
    """One distilled claim with evidence pointers.

    Fields:
        atom_id          stable UUID
        kind             fact / pattern / rule
        title            short human-readable label
        claim            the distilled claim itself, in Aria's voice
        confidence       0..1 — how strongly the evidence supports it
        evidence_refs    list of provenance entry IDs (or fragments) that
                         support this atom. Used by retrieval to drop
                         back to raw episodes (palimpsest).
        channels         list of channel names the atom is "about"
        tags             open-namespace tags (e.g., "schedule",
                         "preference", "habit")
        status           active or superseded
        supersedes       atom_id this atom replaces, if any
        superseded_by    atom_id that replaced this one, if any
        ts_created       creation timestamp
        ts_updated       last-modified timestamp
    """
    atom_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    kind: AtomKind = AtomKind.FACT
    title: str = ""
    claim: str = ""
    confidence: float = 0.5
    evidence_refs: list[str] = field(default_factory=list)
    channels: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    status: AtomStatus = AtomStatus.ACTIVE
    supersedes: str = ""
    superseded_by: str = ""
    ts_created: str = field(
        default_factory=lambda: datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
    )
    ts_updated: str = field(
        default_factory=lambda: datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
    )

    def __post_init__(self) -> None:
        # Clamp confidence to [0, 1]
        self.confidence = max(0.0, min(1.0, float(self.confidence)))
        # Coerce string-shaped enums (happens during JSON round-trip)
        if isinstance(self.kind, str):
            try:
                self.kind = AtomKind(self.kind)
            except ValueError:
                self.kind = AtomKind.FACT
        if isinstance(self.status, str):
            try:
                self.status = AtomStatus(self.status)
            except ValueError:
                self.status = AtomStatus.ACTIVE

    def render(self) -> str:
        """How the atom reads in chat / CLI output."""
        glyph = {
            AtomKind.FACT: "○",
            AtomKind.PATTERN: "◊",
            AtomKind.RULE: "▢",
        }.get(self.kind, "·")
        status_suffix = ""
        if self.status == AtomStatus.SUPERSEDED:
            status_suffix = " [dim](superseded)[/dim]"
        return (
            f"[bold]{glyph}[/bold] {self.title}{status_suffix}\n"
            f"    {self.claim}\n"
            f"    [dim]confidence: {self.confidence:.2f} · "
            f"channels: {', '.join(self.channels) or '—'} · "
            f"evidence: {len(self.evidence_refs)} ref"
            f"{'s' if len(self.evidence_refs) != 1 else ''}[/dim]"
        )


class AtomStore:
    """Append-only store of semantic atoms.

    Atoms are written one per line as JSON. Updates (status changes,
    supersession) are appended as new lines that reference the original
    atom_id — the store does NOT mutate prior lines. This preserves the
    palimpsest property: the original atom is always reconstructible.

    The "current state" of an atom is determined by replaying its
    history: the last entry for each atom_id wins.
    """

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, atom: Atom) -> None:
        """Append one atom (or atom update) to the store."""
        # Rotation hook
        try:
            from ..log_rotation import maybe_rotate
            maybe_rotate(self.path)
        except Exception:  # noqa: BLE001
            pass

        line = json.dumps(asdict(atom), ensure_ascii=False, default=str)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass

    def iter_raw(self) -> Iterable[Atom]:
        """Yield every line in file order. Includes all updates,
        including superseded entries — caller decides what to do."""
        if not self.path.exists():
            return
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    yield Atom(**data)
                except (json.JSONDecodeError, TypeError):
                    continue

    def current_state(self) -> dict[str, Atom]:
        """Replay the log and return the current state of each atom_id.
        Last write wins per atom_id."""
        state: dict[str, Atom] = {}
        for atom in self.iter_raw():
            state[atom.atom_id] = atom
        return state

    def active(self) -> list[Atom]:
        """All atoms with status=active. Sorted newest first."""
        atoms = [
            a for a in self.current_state().values()
            if a.status == AtomStatus.ACTIVE
        ]
        atoms.sort(key=lambda a: a.ts_updated, reverse=True)
        return atoms

    def supersede(self, old_id: str, new_atom: Atom) -> None:
        """Replace an atom. Both old and new get an update entry.

        - Old atom: status → superseded, superseded_by → new_atom.id
        - New atom: supersedes → old_id, written fresh

        Both updates are appended; the original entries remain in the
        log for replay / audit.
        """
        state = self.current_state()
        if old_id not in state:
            raise KeyError(f"no atom with id {old_id}")
        old = state[old_id]
        old.status = AtomStatus.SUPERSEDED
        old.superseded_by = new_atom.atom_id
        old.ts_updated = datetime.now(timezone.utc).isoformat(timespec="seconds")
        new_atom.supersedes = old_id
        self.append(old)
        self.append(new_atom)

    def by_channel(self, channel: str) -> list[Atom]:
        """Active atoms that reference a given channel."""
        return [
            a for a in self.active()
            if channel in a.channels
        ]

    def search(
        self,
        *,
        kind: AtomKind | None = None,
        tag: str | None = None,
        channel: str | None = None,
        text_contains: str | None = None,
    ) -> list[Atom]:
        """Linear filter over active atoms."""
        results: list[Atom] = []
        for a in self.active():
            if kind and a.kind != kind:
                continue
            if tag and tag not in a.tags:
                continue
            if channel and channel not in a.channels:
                continue
            if text_contains:
                hay = (a.title + " " + a.claim).lower()
                if text_contains.lower() not in hay:
                    continue
            results.append(a)
        return results

    def count(self) -> int:
        return len(self.active())


__all__ = ["Atom", "AtomKind", "AtomStatus", "AtomStore"]
