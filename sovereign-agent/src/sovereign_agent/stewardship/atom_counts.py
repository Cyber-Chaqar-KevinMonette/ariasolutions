"""stewardship/atom_counts.py — single source of truth for "how many atoms
does Aria have," across both atom stores.

Kevin, 2026-07-25: self-report said 65 atoms, the memory pane said 88.
Root cause: two independent counts of two different stores. memory_garden.py's
survey_memory() already combines atoms.ndjson (via AtomStore) with atoms.db
(the SQLite store memory_write() actually writes to — see its
atoms-db-visibility-d note). aria_metrics.py's _atom_metrics() never picked
up that fix and still counts atoms.ndjson alone. One function, used by both
call sites, so the two numbers can't drift apart again.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass
class AtomCounts:
    ndjson_total: int = 0
    ndjson_active: int = 0
    db_total: int = 0
    db_active: int = 0

    @property
    def total(self) -> int:
        return self.ndjson_total + self.db_total

    @property
    def active(self) -> int:
        return self.ndjson_active + self.db_active


def count_all_atoms(data_dir: Path) -> AtomCounts:
    """Read-only, graceful on missing/corrupt stores. Combines the ndjson
    lineage store (AtomStore) with the atoms.db SQLite store."""
    counts = AtomCounts()

    try:
        from .atoms import AtomStatus, AtomStore
        store = AtomStore(data_dir / "atoms.ndjson")
        all_atoms = list(store.current_state().values())
        counts.ndjson_total = len(all_atoms)
        counts.ndjson_active = sum(1 for a in all_atoms if a.status == AtomStatus.ACTIVE)
    except Exception:  # noqa: BLE001 — a missing/corrupt store degrades to 0, not a crash
        pass

    try:
        atoms_db_path = data_dir / "atoms.db"
        if atoms_db_path.exists():
            conn = sqlite3.connect(f"file:{atoms_db_path}?mode=ro", uri=True)
            try:
                counts.db_total = conn.execute("SELECT COUNT(*) FROM atoms").fetchone()[0]
                counts.db_active = conn.execute(
                    "SELECT COUNT(*) FROM atoms WHERE superseded_at IS NULL"
                ).fetchone()[0]
            finally:
                conn.close()
    except Exception:  # noqa: BLE001
        pass

    return counts


__all__ = ["AtomCounts", "count_all_atoms"]
