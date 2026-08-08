"""
╔══════════════════════════════════════════════════════════════════════════╗
║  stewardship/memory_garden.py — periodic tending                          ║
║  v0.2.25.0 — "The Garden"                                                 ║
║                                                                           ║
║  When the system has been used for a while, memory naturally sprawls.   ║
║  This module tends the garden — periodically (default: every 1000       ║
║  total memories) it does a safe, non-destructive pass that:             ║
║                                                                           ║
║    1. Marks long-dormant patterns explicitly (status = dormant)         ║
║    2. Identifies likely-duplicate atoms (proposes merges; doesn't       ║
║       execute them — Kevin approves)                                    ║
║    3. Reports memory health (counts, valuable patterns, hot channels) ║
║    4. Suggests reorganization opportunities                            ║
║                                                                           ║
║  Palimpsest discipline strict:                                          ║
║                                                                           ║
║    NOTHING is deleted. NOTHING is silently merged. The garden tender   ║
║    is an observer and a suggester. The operator is the one with       ║
║    authority to merge or supersede.                                    ║
║                                                                           ║
║  The 1000-memory trigger:                                              ║
║                                                                           ║
║    Kevin suggested ~1000 memories as a reorganization cadence. We      ║
║    interpret "memories" as the union of atoms + behavior patterns +     ║
║    honor notes + field notes. The trigger is informational — the      ║
║    operator runs `sov memory reorganize` when they choose.             ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import json
import logging
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from ..config import SETTINGS

logger = logging.getLogger(__name__)


# ─── Health report ─────────────────────────────────────────────────────────


@dataclass
class MemoryHealth:
    """Snapshot of the memory garden's current state."""
    atoms_active: int = 0
    atoms_total: int = 0
    patterns_active: int = 0
    patterns_dormant: int = 0
    patterns_valuable: int = 0
    honor_notes: int = 0
    field_notes: int = 0
    provenance_entries: int = 0
    corrections: int = 0
    total_memories: int = 0
    hot_channels: list[tuple[str, int]] = field(default_factory=list)
    duplicate_atom_suggestions: list[dict] = field(default_factory=list)
    dormancy_candidates: list[str] = field(default_factory=list)

    def needs_reorganization(self, threshold: int = 1000) -> bool:
        return self.total_memories >= threshold


def survey_memory(data_dir: Path | None = None) -> MemoryHealth:
    """Read the various stores and produce a health snapshot.

    Read-only. Side effects: none. Safe to call frequently."""
    if data_dir is None:
        data_dir = SETTINGS.paths.data_dir

    report = MemoryHealth()

    # Atoms — atoms-count-unify-d (Kevin, 2026-07-25): self-report and this
    # pane disagreed (65 vs 88) because each counted a different combination
    # of the two atom stores. Both totals now come from the shared
    # atom_counts.count_all_atoms(), so they can't drift apart again. The
    # ndjson-only atom objects are still read separately here for
    # hot-channel/duplicate detection, which needs the richer records.
    try:
        from .atom_counts import count_all_atoms
        counts = count_all_atoms(data_dir)
        report.atoms_total = counts.total
        report.atoms_active = counts.active
    except Exception as exc:  # noqa: BLE001
        logger.debug("atom count survey failed: %r", exc)

    try:
        from .atoms import AtomStore
        atoms_store = AtomStore(data_dir / "atoms.ndjson")
        all_atoms = list(atoms_store.current_state().values())
        # Hot channels — count atom channel mentions
        channel_counts: Counter[str] = Counter()
        for a in all_atoms:
            for ch in a.channels:
                channel_counts[ch] += 1
        report.hot_channels = channel_counts.most_common(10)
        # Duplicate atom detection — atoms with overlapping evidence_refs
        report.duplicate_atom_suggestions = _find_duplicate_atoms(all_atoms)
    except Exception as exc:  # noqa: BLE001
        logger.debug("atom survey failed: %r", exc)

    # Patterns
    try:
        from .behavior import BehaviorPatternStore, PatternStatus
        pattern_store = BehaviorPatternStore(
            data_dir / "behavior-patterns.ndjson"
        )
        all_patterns = pattern_store.all_patterns()
        report.patterns_active = sum(
            1 for p in all_patterns
            if p.status == PatternStatus.ACTIVE
        )
        report.patterns_dormant = sum(
            1 for p in all_patterns
            if p.status == PatternStatus.DORMANT
        )
        report.patterns_valuable = sum(
            1 for p in all_patterns
            if p.status == PatternStatus.ACTIVE
            and p.outcome.is_valuable
        )
        # Patterns that should probably be marked dormant
        now = datetime.now(timezone.utc)
        report.dormancy_candidates = [
            p.pattern_id[:8]
            for p in all_patterns
            if p.status == PatternStatus.ACTIVE
            and p.is_dormant_now(threshold_days=30, now=now)
        ]
    except Exception as exc:  # noqa: BLE001
        logger.debug("pattern survey failed: %r", exc)

    # Honor notes
    try:
        honor_path = data_dir / "stewardship" / "honor.jsonl"
        if honor_path.exists():
            report.honor_notes = sum(
                1 for ln in honor_path.read_text(encoding="utf-8").splitlines()
                if ln.strip()
            )
    except OSError:
        pass

    # Field notes
    try:
        fn_path = data_dir / "stewardship" / "field-notes.jsonl"
        if fn_path.exists():
            report.field_notes = sum(
                1 for ln in fn_path.read_text(encoding="utf-8").splitlines()
                if ln.strip()
            )
    except OSError:
        pass

    # Provenance entries
    try:
        prov_path = data_dir / "interpretations.ndjson"
        if prov_path.exists():
            report.provenance_entries = sum(
                1 for ln in prov_path.read_text(encoding="utf-8").splitlines()
                if ln.strip()
            )
    except OSError:
        pass

    # Corrections
    try:
        corr_path = data_dir / "corrections.jsonl"
        if corr_path.exists():
            report.corrections = sum(
                1 for ln in corr_path.read_text(encoding="utf-8").splitlines()
                if ln.strip()
            )
    except OSError:
        pass

    # Total memories: atoms + patterns + honor + field + corrections.
    # Provenance is excluded from "memories" — it's the substrate from
    # which memories are distilled, not a memory itself.
    report.total_memories = (
        report.atoms_active
        + report.patterns_active
        + report.patterns_dormant
        + report.honor_notes
        + report.field_notes
        + report.corrections
    )

    return report


def _find_duplicate_atoms(all_atoms: list[Any]) -> list[dict]:
    """Heuristic duplicate detection — atoms with overlapping evidence
    refs (≥ 50% overlap) and matching channel sets.

    Returns a list of suggestions, each with:
      { "atoms": [id1, id2], "overlap_fraction": float, "reason": str }

    Conservative: no automatic merge. The operator reviews and decides.
    """
    suggestions: list[dict] = []
    from .atoms import AtomStatus
    actives = [a for a in all_atoms if a.status == AtomStatus.ACTIVE]
    for i, a in enumerate(actives):
        for b in actives[i+1:]:
            # Same channel set?
            if set(a.channels) != set(b.channels):
                continue
            if not a.evidence_refs or not b.evidence_refs:
                continue
            overlap = set(a.evidence_refs) & set(b.evidence_refs)
            smaller = min(len(a.evidence_refs), len(b.evidence_refs))
            if smaller == 0:
                continue
            frac = len(overlap) / smaller
            if frac >= 0.5:
                suggestions.append({
                    "atoms": [a.atom_id[:8], b.atom_id[:8]],
                    "overlap_fraction": frac,
                    "reason": f"same channels {sorted(a.channels)}, "
                              f"{len(overlap)} shared evidence refs",
                })
    return suggestions[:20]   # cap


# ─── Reorganization pass ───────────────────────────────────────────────────


@dataclass
class ReorganizationResult:
    """Outcome of a single reorganization pass."""
    health_before: MemoryHealth
    patterns_marked_dormant: int = 0
    suggestions_for_operator: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def reorganize(
    data_dir: Path | None = None,
    *,
    dormancy_days: int = 30,
    apply_dormancy: bool = True,
) -> ReorganizationResult:
    """Run one reorganization pass.

    Safe operations performed:
      1. Patterns unobserved for `dormancy_days` get status → dormant
         (with audit-log entry; reversible by next observation)
      2. Statistical survey of memory state
      3. Duplicate atom detection (suggestions only)

    Operations NOT performed (require operator authority):
      - Atom merges
      - Atom deletions (never — palimpsest)
      - Pattern supersession
    """
    if data_dir is None:
        data_dir = SETTINGS.paths.data_dir

    health = survey_memory(data_dir)
    result = ReorganizationResult(health_before=health)

    # Apply dormancy
    if apply_dormancy:
        try:
            from .behavior import (
                BehaviorPatternStore, PatternStatus,
            )
            pattern_store = BehaviorPatternStore(
                data_dir / "behavior-patterns.ndjson"
            )
            now = datetime.now(timezone.utc)
            for p in pattern_store.all_patterns():
                if (
                    p.status == PatternStatus.ACTIVE
                    and p.is_dormant_now(threshold_days=dormancy_days,
                                          now=now)
                ):
                    p.status = PatternStatus.DORMANT
                    pattern_store.append(p)
                    result.patterns_marked_dormant += 1
        except Exception as exc:  # noqa: BLE001
            result.errors.append(f"dormancy: {type(exc).__name__}")

    # Build suggestions for operator review
    if health.duplicate_atom_suggestions:
        for s in health.duplicate_atom_suggestions[:5]:
            result.suggestions_for_operator.append(
                f"consider merging atoms {s['atoms'][0]} and "
                f"{s['atoms'][1]} (overlap {s['overlap_fraction']:.0%}, "
                f"{s['reason']})"
            )

    if health.atoms_total > 0 and health.atoms_active < health.atoms_total * 0.8:
        result.suggestions_for_operator.append(
            f"{health.atoms_total - health.atoms_active} superseded atoms "
            f"in the log (out of {health.atoms_total}) — consider "
            f"running `sov atoms list` to audit"
        )

    if health.patterns_dormant > health.patterns_active:
        result.suggestions_for_operator.append(
            f"more dormant patterns ({health.patterns_dormant}) than "
            f"active ({health.patterns_active}) — consider whether the "
            f"dormancy threshold is right"
        )

    return result


__all__ = ["MemoryHealth", "survey_memory", "reorganize", "ReorganizationResult"]
