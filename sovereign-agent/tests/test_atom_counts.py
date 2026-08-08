"""Tests for stewardship/atom_counts.py — the shared count so self-report
and the memory pane can't disagree on how many atoms exist.

Kevin, 2026-07-25: self-report said 65 atoms, the memory pane said 88 --
traced to two independent counts over two different stores.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict


def _write_ndjson_atoms(data_dir, n, *, active=True):
    from sovereign_agent.stewardship.atoms import Atom, AtomKind, AtomStatus

    atoms_path = data_dir / "atoms.ndjson"
    status = AtomStatus.ACTIVE if active else AtomStatus.SUPERSEDED
    for i in range(n):
        atom = Atom(
            title=f"atom {i}", claim=f"claim {i}", kind=AtomKind.FACT,
            confidence=0.5, status=status,
        )
        with atoms_path.open("a") as f:
            f.write(json.dumps(asdict(atom), default=str) + "\n")


def _write_db_atoms(data_dir, n_active, n_superseded):
    conn = sqlite3.connect(data_dir / "atoms.db")
    conn.execute(
        "CREATE TABLE atoms (id INTEGER PRIMARY KEY, superseded_at TEXT)"
    )
    for _ in range(n_active):
        conn.execute("INSERT INTO atoms (superseded_at) VALUES (NULL)")
    for _ in range(n_superseded):
        conn.execute("INSERT INTO atoms (superseded_at) VALUES ('2026-01-01')")
    conn.commit()
    conn.close()


def test_empty_data_dir_counts_zero(tmp_path):
    from sovereign_agent.stewardship.atom_counts import count_all_atoms

    counts = count_all_atoms(tmp_path)
    assert counts.total == 0
    assert counts.active == 0


def test_counts_ndjson_only(tmp_path):
    from sovereign_agent.stewardship.atom_counts import count_all_atoms

    _write_ndjson_atoms(tmp_path, 5)
    counts = count_all_atoms(tmp_path)
    assert counts.ndjson_active == 5
    assert counts.db_active == 0
    assert counts.active == 5


def test_counts_db_only(tmp_path):
    from sovereign_agent.stewardship.atom_counts import count_all_atoms

    _write_db_atoms(tmp_path, n_active=4, n_superseded=2)
    counts = count_all_atoms(tmp_path)
    assert counts.db_active == 4
    assert counts.db_total == 6
    assert counts.ndjson_active == 0
    assert counts.active == 4


def test_combines_both_stores(tmp_path):
    """The exact bug: 65 (ndjson) + 23 (db) should read as 88 everywhere,
    not 65 in one place and 88 in another."""
    from sovereign_agent.stewardship.atom_counts import count_all_atoms

    _write_ndjson_atoms(tmp_path, 65)
    _write_db_atoms(tmp_path, n_active=23, n_superseded=0)
    counts = count_all_atoms(tmp_path)
    assert counts.active == 88


def test_self_report_and_memory_pane_agree(tmp_path):
    """Regression for the exact Kevin-reported bug: aria_metrics._atom_metrics
    (self-report's data source) and memory_garden.survey_memory (the pane's
    data source) must report the same active-atom count."""
    _write_ndjson_atoms(tmp_path, 10)
    _write_db_atoms(tmp_path, n_active=7, n_superseded=1)

    from sovereign_agent.tools import aria_metrics
    from sovereign_agent.stewardship import memory_garden

    report_count = aria_metrics._atom_metrics(tmp_path)["atom_count"]
    pane_count = memory_garden.survey_memory(tmp_path).atoms_active

    assert report_count == pane_count == 17
