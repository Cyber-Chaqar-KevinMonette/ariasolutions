"""Tests for M67 — Value Proof Crown (proof_of_value, proof_history, giving_ledger).

The unit of proof that feeds the institutional impulse's proof gate.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest


# ─── DB fixture ──────────────────────────────────────────────────────────────

CREATE_ATOMS = """\
CREATE TABLE IF NOT EXISTS atoms (
    atom_id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    scope_path TEXT,
    scope_tags TEXT DEFAULT '[]',
    summary TEXT NOT NULL,
    content_ref TEXT DEFAULT '{}',
    claims TEXT DEFAULT '[]',
    parents TEXT DEFAULT '[]',
    version INTEGER DEFAULT 1,
    parent_atom_id TEXT,
    policy TEXT DEFAULT 'local_only',
    confidence REAL DEFAULT 0.5,
    created_at TEXT,
    created_by TEXT DEFAULT '{}',
    superseded_at TEXT,
    superseded_by TEXT
)
"""

ULID_COUNTER = [0]


def _ulid():
    ULID_COUNTER[0] += 1
    return f"TEST{ULID_COUNTER[0]:020d}"


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "atoms.db"
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.execute(CREATE_ATOMS)
    conn.commit()
    return path, conn


def _patch_db(db_path):
    return patch(
        "sovereign_agent.tools.proof_tools.open_atoms_db",
        side_effect=lambda: sqlite3.connect(str(db_path), check_same_thread=False),
    )


def _fake_write(conn, atom):
    aid = _ulid()
    conn.execute(
        "INSERT INTO atoms (atom_id, type, summary, content_ref, scope_tags, parents, created_at, created_by) "
        "VALUES (?, ?, ?, ?, ?, ?, datetime('now'), '{}')",
        (
            aid,
            atom.type,
            atom.summary,
            json.dumps(atom.content_ref),
            json.dumps(atom.scope_tags),
            json.dumps(atom.parents),
        ),
    )
    return aid


# ─── ProofOfValueTool metadata ───────────────────────────────────────────────


def test_proof_of_value_is_t1():
    from sovereign_agent.tools.proof_tools import ProofOfValueTool
    assert ProofOfValueTool.tier == 1


def test_proof_history_is_t0():
    from sovereign_agent.tools.proof_tools import ProofHistoryTool
    assert ProofHistoryTool.tier == 0


def test_giving_ledger_is_t0():
    from sovereign_agent.tools.proof_tools import GivingLedgerTool
    assert GivingLedgerTool.tier == 0


# ─── ProofOfValueTool — writes atom ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_proof_of_value_writes_atom(db):
    db_path, conn = db
    written = {}

    def _capture(c, atom):
        written["atom"] = atom
        return _fake_write(c, atom)

    from sovereign_agent.tools.proof_tools import ProofOfValueTool
    tool = ProofOfValueTool()
    with (
        _patch_db(db_path),
        patch("sovereign_agent.tools.proof_tools.write_atom", side_effect=_capture),
    ):
        result = await tool.execute(
            tool.Args(
                person_name="Alice",
                problem_solved="synthesizing research papers",
                value_delivered="saved 3 hours of reading",
                was_unprompted=True,
                person_is_builder=False,
            ),
            trace_id="t1",
        )

    assert result.ok is True
    assert "atom" in written
    assert written["atom"].type == "proof-of-value"


@pytest.mark.asyncio
async def test_atom_has_correct_scope_tags_external(db):
    db_path, conn = db
    written = {}

    def _capture(c, atom):
        written["atom"] = atom
        return _fake_write(c, atom)

    from sovereign_agent.tools.proof_tools import ProofOfValueTool
    tool = ProofOfValueTool()
    with (
        _patch_db(db_path),
        patch("sovereign_agent.tools.proof_tools.write_atom", side_effect=_capture),
    ):
        await tool.execute(
            tool.Args(
                person_name="Bob",
                problem_solved="debugging",
                value_delivered="fixed in 10 minutes",
                was_unprompted=False,
                person_is_builder=False,
            ),
            trace_id="t2",
        )

    tags = written["atom"].scope_tags
    assert "proof" in tags
    assert "value-delivery" in tags
    assert "external-proof" in tags
    assert "internal-proof" not in tags


@pytest.mark.asyncio
async def test_builder_atom_tagged_internal(db):
    db_path, conn = db
    written = {}

    def _capture(c, atom):
        written["atom"] = atom
        return _fake_write(c, atom)

    from sovereign_agent.tools.proof_tools import ProofOfValueTool
    tool = ProofOfValueTool()
    with (
        _patch_db(db_path),
        patch("sovereign_agent.tools.proof_tools.write_atom", side_effect=_capture),
    ):
        await tool.execute(
            tool.Args(
                person_name="Kevin",
                problem_solved="self-improvement",
                value_delivered="clarity",
                was_unprompted=True,
                person_is_builder=True,
            ),
            trace_id="t3",
        )

    tags = written["atom"].scope_tags
    assert "internal-proof" in tags
    assert "external-proof" not in tags


@pytest.mark.asyncio
async def test_proof_of_value_db_unavailable(db):
    from sovereign_agent.tools.proof_tools import ProofOfValueTool
    tool = ProofOfValueTool()
    with patch("sovereign_agent.tools.proof_tools.open_atoms_db", None):
        result = await tool.execute(
            tool.Args(person_name="x", problem_solved="x", value_delivered="x", was_unprompted=True),
            trace_id="t4",
        )
    assert result.ok is False


# ─── ProofHistoryTool ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_proof_history_empty_db(db):
    db_path, conn = db
    from sovereign_agent.tools.proof_tools import ProofHistoryTool
    tool = ProofHistoryTool()
    with _patch_db(db_path):
        result = await tool.execute(tool.Args(), trace_id="t5")
    assert result.ok is True
    assert result.output["total_count"] == 0
    assert result.output["external_count"] == 0
    assert result.output["proof_gate_met"] is False


@pytest.mark.asyncio
async def test_proof_history_internal_only_gate_not_met(db):
    db_path, conn = db
    # Insert an internal proof atom directly
    content = {"person_name": "Kevin", "person_is_builder": True}
    conn.execute(
        "INSERT INTO atoms (atom_id, type, summary, content_ref, created_at, created_by) "
        "VALUES (?, ?, ?, ?, datetime('now'), '{}')",
        ("A001", "proof-of-value", "internal", json.dumps({"content": json.dumps(content)})),
    )
    conn.commit()

    from sovereign_agent.tools.proof_tools import ProofHistoryTool
    tool = ProofHistoryTool()
    with _patch_db(db_path):
        result = await tool.execute(tool.Args(), trace_id="t6")

    assert result.output["total_count"] == 1
    assert result.output["internal_count"] == 1
    assert result.output["external_count"] == 0
    assert result.output["proof_gate_met"] is False


@pytest.mark.asyncio
async def test_proof_history_external_atom_gate_met(db):
    db_path, conn = db
    content = {"person_name": "Alice", "person_is_builder": False}
    conn.execute(
        "INSERT INTO atoms (atom_id, type, summary, content_ref, created_at, created_by) "
        "VALUES (?, ?, ?, ?, datetime('now'), '{}')",
        ("A002", "proof-of-value", "external", json.dumps({"content": json.dumps(content)})),
    )
    conn.commit()

    from sovereign_agent.tools.proof_tools import ProofHistoryTool
    tool = ProofHistoryTool()
    with _patch_db(db_path):
        result = await tool.execute(tool.Args(), trace_id="t7")

    assert result.output["external_count"] == 1
    assert result.output["proof_gate_met"] is True


@pytest.mark.asyncio
async def test_proof_history_db_unavailable(db):
    from sovereign_agent.tools.proof_tools import ProofHistoryTool
    tool = ProofHistoryTool()
    with patch("sovereign_agent.tools.proof_tools.open_atoms_db", None):
        result = await tool.execute(tool.Args(), trace_id="t8")
    assert result.ok is True
    assert result.output["proof_gate_met"] is False


# ─── GivingLedgerTool ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_giving_ledger_empty_db_all_zeroes(db):
    db_path, conn = db
    from sovereign_agent.tools.proof_tools import GivingLedgerTool
    tool = GivingLedgerTool()
    with _patch_db(db_path):
        result = await tool.execute(tool.Args(days=30), trace_id="t9")
    assert result.ok is True
    assert result.output["value_given_count"] == 0
    assert result.output["most_generous_day"] is None


@pytest.mark.asyncio
async def test_giving_ledger_counts_experience_and_proof(db):
    db_path, conn = db
    # Insert 2 experience atoms and 1 proof atom
    for i, atype in enumerate(["experience", "experience", "proof-of-value"]):
        conn.execute(
            "INSERT INTO atoms (atom_id, type, summary, content_ref, created_at, created_by) "
            "VALUES (?, ?, ?, ?, datetime('now'), '{}')",
            (f"G{i:03d}", atype, f"test {atype}", '{"content": "{}"}'),
        )
    conn.commit()

    from sovereign_agent.tools.proof_tools import GivingLedgerTool
    tool = GivingLedgerTool()
    with _patch_db(db_path):
        result = await tool.execute(tool.Args(days=30), trace_id="t10")

    assert result.output["value_given_count"] == 3


@pytest.mark.asyncio
async def test_giving_ledger_most_generous_day(db):
    db_path, conn = db
    # 3 atoms today, 1 yesterday
    for i in range(3):
        conn.execute(
            "INSERT INTO atoms (atom_id, type, summary, content_ref, created_at, created_by) "
            "VALUES (?, ?, ?, ?, ?, '{}')",
            (f"G{i:03d}", "experience", "today", '{"content": "{}"}', "2026-06-20T10:00:00Z"),
        )
    conn.execute(
        "INSERT INTO atoms (atom_id, type, summary, content_ref, created_at, created_by) "
        "VALUES (?, ?, ?, ?, ?, '{}')",
        ("G003", "experience", "yesterday", '{"content": "{}"}', "2026-06-19T10:00:00Z"),
    )
    conn.commit()

    from sovereign_agent.tools.proof_tools import GivingLedgerTool
    tool = GivingLedgerTool()
    with _patch_db(db_path):
        result = await tool.execute(tool.Args(days=30), trace_id="t11")

    assert result.output["most_generous_day"] == "2026-06-20"


@pytest.mark.asyncio
async def test_giving_ledger_db_unavailable(db):
    from sovereign_agent.tools.proof_tools import GivingLedgerTool
    tool = GivingLedgerTool()
    with patch("sovereign_agent.tools.proof_tools.open_atoms_db", None):
        result = await tool.execute(tool.Args(days=30), trace_id="t12")
    assert result.ok is True
    assert result.output["value_given_count"] == 0


# ─── Integration: proof_history feeds impulse_check ─────────────────────────


@pytest.mark.asyncio
async def test_external_proof_makes_impulse_check_proof_gate_green(db):
    """Integration: after recording external proof, proof gate becomes green."""
    db_path, conn = db

    def _capture(c, atom):
        return _fake_write(c, atom)

    from sovereign_agent.tools.proof_tools import ProofOfValueTool
    from sovereign_agent.tools.impulse_tools import InstitutionalImpulseCheckTool

    proof_tool = ProofOfValueTool()
    check_tool = InstitutionalImpulseCheckTool()

    with (
        _patch_db(db_path),
        patch("sovereign_agent.tools.proof_tools.write_atom", side_effect=_capture),
    ):
        await proof_tool.execute(
            proof_tool.Args(
                person_name="Alice",
                problem_solved="real problem",
                value_delivered="real value",
                was_unprompted=True,
                person_is_builder=False,
            ),
            trace_id="integration-t1",
        )

    # Now check impulse with the same DB
    with patch(
        "sovereign_agent.tools.impulse_tools.open_atoms_db",
        side_effect=lambda: sqlite3.connect(str(db_path), check_same_thread=False),
    ):
        result = await check_tool.execute(check_tool.Args(), trace_id="integration-t2")

    assert result.output["proof_gate"]["status"] == "green"
    assert result.output["proof_gate"]["proof_count"] >= 1
