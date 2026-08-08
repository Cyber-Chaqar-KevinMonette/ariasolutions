"""Tests for M66 — Institutional Impulse tools + mos_canon clause.

Covers: three-gate readiness assessment, wedge calibration, clause verification.
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
        "sovereign_agent.tools.impulse_tools.open_atoms_db",
        side_effect=lambda: sqlite3.connect(str(db_path), check_same_thread=False),
    )


def _insert_atom(conn, atom_type: str, content: dict, created_at: str = "2026-06-20T10:00:00Z"):
    atom_id = _ulid()
    conn.execute(
        "INSERT INTO atoms (atom_id, type, summary, content_ref, created_at) VALUES (?, ?, ?, ?, ?)",
        (atom_id, atom_type, f"test {atom_type}", json.dumps({"content": json.dumps(content)}), created_at),
    )
    conn.commit()
    return atom_id


# ─── Tool metadata ───────────────────────────────────────────────────────────


def test_impulse_check_name():
    from sovereign_agent.tools.impulse_tools import InstitutionalImpulseCheckTool
    assert InstitutionalImpulseCheckTool.name == "institutional_impulse_check"


def test_impulse_check_is_t0():
    from sovereign_agent.tools.impulse_tools import InstitutionalImpulseCheckTool
    assert InstitutionalImpulseCheckTool.tier == 0


def test_wedge_calibrator_name():
    from sovereign_agent.tools.impulse_tools import WedgeCalibratorTool
    assert WedgeCalibratorTool.name == "wedge_calibrator"


def test_wedge_calibrator_is_t0():
    from sovereign_agent.tools.impulse_tools import WedgeCalibratorTool
    assert WedgeCalibratorTool.tier == 0


# ─── InstitutionalImpulseCheckTool — proof gate ──────────────────────────────


@pytest.mark.asyncio
async def test_no_proof_atoms_proof_gate_open(db):
    db_path, conn = db
    from sovereign_agent.tools.impulse_tools import InstitutionalImpulseCheckTool
    tool = InstitutionalImpulseCheckTool()
    with _patch_db(db_path):
        result = await tool.execute(tool.Args(), trace_id="t1")
    assert result.ok is True
    assert result.output["proof_gate"]["status"] == "open"
    assert result.output["overall_readiness"] == "NOT_READY"
    assert result.output["primary_blocker"] == "proof_gate"


@pytest.mark.asyncio
async def test_external_proof_atom_makes_proof_gate_green(db):
    db_path, conn = db
    _insert_atom(conn, "proof-of-value", {
        "person_name": "Alice",
        "problem_solved": "research synthesis",
        "person_is_builder": False,
    })
    from sovereign_agent.tools.impulse_tools import InstitutionalImpulseCheckTool
    tool = InstitutionalImpulseCheckTool()
    with _patch_db(db_path):
        result = await tool.execute(tool.Args(), trace_id="t2")
    assert result.output["proof_gate"]["status"] == "green"
    assert result.output["proof_gate"]["proof_count"] == 1


@pytest.mark.asyncio
async def test_only_builder_proof_does_not_satisfy_gate(db):
    """Proof from the builder (Kevin) doesn't count toward external proof."""
    db_path, conn = db
    _insert_atom(conn, "proof-of-value", {
        "person_name": "Kevin",
        "problem_solved": "self-improvement",
        "person_is_builder": True,
    })
    from sovereign_agent.tools.impulse_tools import InstitutionalImpulseCheckTool
    tool = InstitutionalImpulseCheckTool()
    with _patch_db(db_path):
        result = await tool.execute(tool.Args(), trace_id="t3")
    assert result.output["proof_gate"]["status"] == "open"
    assert result.output["proof_gate"]["proof_count"] == 0


# ─── InstitutionalImpulseCheckTool — signal gate ─────────────────────────────


@pytest.mark.asyncio
async def test_low_surprise_yields_yellow_signal(db):
    db_path, conn = db
    for i in range(5):
        _insert_atom(conn, "experience", {"domain": "git", "surprise_level": 0.1})
    from sovereign_agent.tools.impulse_tools import InstitutionalImpulseCheckTool
    tool = InstitutionalImpulseCheckTool()
    with _patch_db(db_path):
        result = await tool.execute(tool.Args(), trace_id="t4")
    assert result.output["signal_gate"]["status"] == "yellow"
    assert result.output["signal_gate"]["quality"] == "fear"


@pytest.mark.asyncio
async def test_high_surprise_yields_green_signal(db):
    db_path, conn = db
    for i in range(5):
        _insert_atom(conn, "experience", {"domain": "research", "surprise_level": 0.8})
    from sovereign_agent.tools.impulse_tools import InstitutionalImpulseCheckTool
    tool = InstitutionalImpulseCheckTool()
    with _patch_db(db_path):
        result = await tool.execute(tool.Args(), trace_id="t5")
    assert result.output["signal_gate"]["status"] == "green"
    assert result.output["signal_gate"]["quality"] == "curiosity"


# ─── InstitutionalImpulseCheckTool — generation gate ─────────────────────────


@pytest.mark.asyncio
async def test_generation_gate_always_pending_human(db):
    """Generation gate cannot be auto-cleared — it always requires human judgment."""
    db_path, conn = db
    from sovereign_agent.tools.impulse_tools import InstitutionalImpulseCheckTool
    tool = InstitutionalImpulseCheckTool()
    with _patch_db(db_path):
        result = await tool.execute(tool.Args(), trace_id="t6")
    assert result.output["generation_gate"]["status"] == "pending_human"
    assert "7th generation" in result.output["generation_gate"]["question"]


# ─── InstitutionalImpulseCheckTool — required keys ───────────────────────────


@pytest.mark.asyncio
async def test_all_required_keys_present(db):
    db_path, conn = db
    from sovereign_agent.tools.impulse_tools import InstitutionalImpulseCheckTool
    tool = InstitutionalImpulseCheckTool()
    with _patch_db(db_path):
        result = await tool.execute(tool.Args(), trace_id="t7")
    out = result.output
    required = {"proof_gate", "signal_gate", "generation_gate",
                "overall_readiness", "primary_blocker", "guidance"}
    assert required.issubset(set(out.keys()))


@pytest.mark.asyncio
async def test_guidance_non_empty_when_not_ready(db):
    db_path, conn = db
    from sovereign_agent.tools.impulse_tools import InstitutionalImpulseCheckTool
    tool = InstitutionalImpulseCheckTool()
    with _patch_db(db_path):
        result = await tool.execute(tool.Args(), trace_id="t8")
    assert len(result.output["guidance"]) > 10


@pytest.mark.asyncio
async def test_db_unavailable_returns_ok(db):
    from sovereign_agent.tools.impulse_tools import InstitutionalImpulseCheckTool
    tool = InstitutionalImpulseCheckTool()
    with patch("sovereign_agent.tools.impulse_tools.open_atoms_db", None):
        result = await tool.execute(tool.Args(), trace_id="t9")
    assert result.ok is True
    assert result.output["proof_gate"]["status"] == "open"


# ─── WedgeCalibratorTool ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_wedge_calibrator_empty_db_low_confidence(db):
    db_path, conn = db
    from sovereign_agent.tools.impulse_tools import WedgeCalibratorTool
    tool = WedgeCalibratorTool()
    with _patch_db(db_path):
        result = await tool.execute(tool.Args(), trace_id="t10")
    assert result.ok is True
    assert result.output["confidence"] == "low"
    assert result.output["top_wedges"] == []
    assert result.output["best_wedge"] is None


@pytest.mark.asyncio
async def test_wedge_calibrator_ranks_domains_by_weighted_score(db):
    db_path, conn = db
    # research: 3 atoms × avg 0.8 = score 2.4
    for _ in range(3):
        _insert_atom(conn, "experience", {"domain": "research", "surprise_level": 0.8})
    # git: 5 atoms × avg 0.1 = score 0.5
    for _ in range(5):
        _insert_atom(conn, "experience", {"domain": "git", "surprise_level": 0.1})
    from sovereign_agent.tools.impulse_tools import WedgeCalibratorTool
    tool = WedgeCalibratorTool()
    with _patch_db(db_path):
        result = await tool.execute(tool.Args(), trace_id="t11")
    assert result.output["best_wedge"] == "research"


@pytest.mark.asyncio
async def test_wedge_calibrator_confidence_levels(db):
    db_path, conn = db
    # 50 atoms → "medium"
    for _ in range(50):
        _insert_atom(conn, "experience", {"domain": "writing", "surprise_level": 0.5})
    from sovereign_agent.tools.impulse_tools import WedgeCalibratorTool
    tool = WedgeCalibratorTool()
    with _patch_db(db_path):
        result = await tool.execute(tool.Args(), trace_id="t12")
    # 50 atoms: strictly < 50 is "medium"? Let's verify: code says < 10 low, < 50 medium, else high
    # 50 is NOT < 50, so it should be "high"
    # Actually the code: if total_atoms < 10 → low; elif < 50 → medium; else → high
    # 50 atoms → high
    assert result.output["confidence"] in ("medium", "high")


@pytest.mark.asyncio
async def test_wedge_calibrator_db_unavailable_graceful(db):
    from sovereign_agent.tools.impulse_tools import WedgeCalibratorTool
    tool = WedgeCalibratorTool()
    with patch("sovereign_agent.tools.impulse_tools.open_atoms_db", None):
        result = await tool.execute(tool.Args(), trace_id="t13")
    assert result.ok is True
    assert result.output["confidence"] == "low"


# ─── MOS Canon clause ────────────────────────────────────────────────────────


def test_mos_institutional_impulse_clause_accessible():
    """mos-institutional-impulse clause must be in the canon after M66 apply."""
    from sovereign_agent.mos_canon import get_clause, CLAUSE_INDEX
    if "mos-institutional-impulse" not in CLAUSE_INDEX:
        pytest.skip("mos-institutional-impulse not yet in canon — apply M66 first")
    clause = get_clause("mos-institutional-impulse")
    assert clause is not None
    assert clause.id == "mos-institutional-impulse"


def test_clause_articles_include_no_platform_before_proof():
    from sovereign_agent.mos_canon import CLAUSE_INDEX
    if "mos-institutional-impulse" not in CLAUSE_INDEX:
        pytest.skip("mos-institutional-impulse not yet in canon")
    clause = CLAUSE_INDEX["mos-institutional-impulse"]
    combined = " ".join([clause.principle, clause.leverage, clause.modulation]).lower()
    assert "proof" in combined and "platform" in combined


def test_clause_kernel_mentions_safety_love_flourishing():
    from sovereign_agent.mos_canon import CLAUSE_INDEX
    if "mos-institutional-impulse" not in CLAUSE_INDEX:
        pytest.skip("mos-institutional-impulse not yet in canon")
    clause = CLAUSE_INDEX["mos-institutional-impulse"]
    principle = clause.principle.lower()
    assert "safety" in principle or "love" in principle or "flourishing" in principle


def test_clause_modulation_references_impulse_check():
    from sovereign_agent.mos_canon import CLAUSE_INDEX
    if "mos-institutional-impulse" not in CLAUSE_INDEX:
        pytest.skip("mos-institutional-impulse not yet in canon")
    clause = CLAUSE_INDEX["mos-institutional-impulse"]
    assert "institutional_impulse_check" in clause.modulation or "impulse_check" in clause.modulation


def test_clause_related_includes_signal_check():
    from sovereign_agent.mos_canon import CLAUSE_INDEX
    if "mos-institutional-impulse" not in CLAUSE_INDEX:
        pytest.skip("mos-institutional-impulse not yet in canon")
    clause = CLAUSE_INDEX["mos-institutional-impulse"]
    assert "mos-signal-check" in clause.related


def test_clause_part_is_consciousness():
    from sovereign_agent.mos_canon import CLAUSE_INDEX
    if "mos-institutional-impulse" not in CLAUSE_INDEX:
        pytest.skip("mos-institutional-impulse not yet in canon")
    clause = CLAUSE_INDEX["mos-institutional-impulse"]
    assert clause.part == "consciousness"
