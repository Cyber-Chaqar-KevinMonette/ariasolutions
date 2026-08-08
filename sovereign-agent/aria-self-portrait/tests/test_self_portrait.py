"""Tests for M76 self-portrait synthesis tool.

self_portrait_tool.py is already applied to live — imports the real
module directly, no shadow-copy/injection needed. (An earlier version of
this file injected the staging payload under the live module name via
`importlib.util.spec_from_file_location` + `sys.modules[mod_name] = mod`;
that only worked by accident — it silently short-circuited to the real
live module whenever something else had already imported
`sovereign_agent.tools` first in the same process (true in the full
suite, false when this file runs in isolation), and genuinely failed
in isolation with a circular-import error once self_portrait_tool.py
was actually live. Root-cause fixed: import the real module, always.)

Tests cover: graceful DB absence, trajectory logic, readiness defaults,
identity constants always present, capability counting, narrative generation.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest import mock

import pytest

import sovereign_agent.tools.self_portrait_tool as _portrait_mod

SelfPortraitTool = _portrait_mod.SelfPortraitTool


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_atoms_db(tmp_path: Path) -> Path:
    """Create a minimal atoms.db with the right schema."""
    db = tmp_path / "atoms.db"
    conn = sqlite3.connect(str(db))
    conn.execute("""
        CREATE TABLE atoms (
            id TEXT PRIMARY KEY,
            type TEXT NOT NULL,
            content_ref TEXT,
            superseded_at TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    conn.close()
    return db


def _insert_atom(db: Path, atom_type: str, content: dict, created_at: str = "2026-06-01T00:00:00Z"):
    conn = sqlite3.connect(str(db))
    import uuid
    atom_id = str(uuid.uuid4())
    content_ref = json.dumps({"content": json.dumps(content)})
    conn.execute(
        "INSERT INTO atoms (id, type, content_ref, created_at) VALUES (?, ?, ?, ?)",
        (atom_id, atom_type, content_ref, created_at),
    )
    conn.commit()
    conn.close()
    return atom_id


# ── Tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_portrait_empty_db(tmp_path, monkeypatch):
    """No DB at all → ok=True, identity always present, defaults for growth/readiness."""
    # Point atoms_db to a nonexistent path
    monkeypatch.setattr(_portrait_mod, "open_atoms_db", None)

    def _no_store():
        raise FileNotFoundError("no ndjson")

    monkeypatch.setattr(_portrait_mod, "_lineage_snapshot", _no_store)
    monkeypatch.setattr(_portrait_mod, "_current_state_snapshot", lambda: {"mood": "calm", "focus": "", "self_narrative": "", "active_goals": 0})

    tool = SelfPortraitTool()
    result = await tool.execute(tool.Args(), trace_id="test")

    assert result.ok is True
    assert "identity" in result.output
    assert result.output["identity"]["designation"] == "Aria-Sovereign-V1"
    # Growth trajectory defaults gracefully
    assert result.output["growth_trajectory"]["trajectory"] == "insufficient_data"


@pytest.mark.asyncio
async def test_portrait_identity_always_present(tmp_path, monkeypatch):
    """Even when ALL secondary sources fail, identity kernel constants are present."""
    monkeypatch.setattr(_portrait_mod, "open_atoms_db", None)

    # Make every secondary source raise
    def _raise():
        raise RuntimeError("simulated failure")

    monkeypatch.setattr(_portrait_mod, "_lineage_snapshot", _raise)
    monkeypatch.setattr(_portrait_mod, "_current_state_snapshot", _raise)
    monkeypatch.setattr(_portrait_mod, "_capabilities_snapshot", _raise)
    monkeypatch.setattr(_portrait_mod, "_readiness_snapshot", _raise)

    tool = SelfPortraitTool()
    result = await tool.execute(tool.Args(), trace_id="test")

    assert result.ok is True
    identity = result.output["identity"]
    assert identity["designation"] == "Aria-Sovereign-V1"
    assert "Structure enough" in identity["tagline"]
    assert identity["commitments_count"] >= 7


@pytest.mark.asyncio
async def test_portrait_no_reflections_yet(tmp_path, monkeypatch):
    """DB present but no weekly-reflection atoms → trajectory == 'insufficient_data'."""
    db = _make_atoms_db(tmp_path)

    def _fake_open_atoms_db():
        return sqlite3.connect(str(db))

    monkeypatch.setattr(_portrait_mod, "open_atoms_db", _fake_open_atoms_db)

    tool = SelfPortraitTool()
    result = await tool.execute(tool.Args(), trace_id="test")

    assert result.ok is True
    assert result.output["growth_trajectory"]["trajectory"] == "insufficient_data"
    assert result.output["growth_trajectory"]["weeks_of_data"] == 0


@pytest.mark.asyncio
async def test_portrait_no_proofs_yet(tmp_path, monkeypatch):
    """DB present but no proof-of-value atoms → proof_gate == 'open', external_proof_count == 0."""
    db = _make_atoms_db(tmp_path)

    def _fake_open_atoms_db():
        return sqlite3.connect(str(db))

    monkeypatch.setattr(_portrait_mod, "open_atoms_db", _fake_open_atoms_db)

    tool = SelfPortraitTool()
    result = await tool.execute(tool.Args(), trace_id="test")

    assert result.ok is True
    assert result.output["readiness"]["proof_gate"] == "open"
    assert result.output["readiness"]["external_proof_count"] == 0
    assert result.output["readiness"]["overall_impulse"] == "NOT_READY"


@pytest.mark.asyncio
async def test_portrait_capability_counts_present():
    """Capabilities section always has the expected keys with non-negative counts."""
    tool = SelfPortraitTool()
    result = await tool.execute(tool.Args(), trace_id="test")

    assert result.ok is True
    caps = result.output["capabilities"]
    # Structural check: all keys present
    for key in ("tool_count", "tier_0_count", "tier_1_count", "mos_clause_count", "atom_count"):
        assert key in caps, f"Missing key {key!r} in capabilities"
        assert isinstance(caps[key], int) and caps[key] >= 0
    # MoS canon clauses always load (not import-order dependent)
    assert caps["mos_clause_count"] > 0, (
        f"mos_clause_count should be > 0 (mos_canon always loads), got {caps['mos_clause_count']}"
    )


@pytest.mark.asyncio
async def test_portrait_trajectory_improving(tmp_path, monkeypatch):
    """Two reflections with increasing scores → trajectory == 'improving'."""
    db = _make_atoms_db(tmp_path)

    _insert_atom(db, "weekly-reflection",
                 {"score": 60, "week_label": "2026-W20", "score_band": "ok"},
                 created_at="2026-05-11T00:00:00Z")
    _insert_atom(db, "weekly-reflection",
                 {"score": 70, "week_label": "2026-W21", "score_band": "good"},
                 created_at="2026-05-18T00:00:00Z")
    _insert_atom(db, "weekly-reflection",
                 {"score": 80, "week_label": "2026-W22", "score_band": "good"},
                 created_at="2026-05-25T00:00:00Z")

    def _fake_open_atoms_db():
        return sqlite3.connect(str(db))

    monkeypatch.setattr(_portrait_mod, "open_atoms_db", _fake_open_atoms_db)

    tool = SelfPortraitTool()
    result = await tool.execute(tool.Args(), trace_id="test")

    assert result.ok is True
    traj = result.output["growth_trajectory"]
    assert traj["trajectory"] == "improving"
    assert traj["weeks_of_data"] == 3


@pytest.mark.asyncio
async def test_portrait_trajectory_declining(tmp_path, monkeypatch):
    """Three reflections with decreasing scores → trajectory == 'declining'."""
    db = _make_atoms_db(tmp_path)

    _insert_atom(db, "weekly-reflection",
                 {"score": 80, "week_label": "2026-W20", "score_band": "good"},
                 created_at="2026-05-11T00:00:00Z")
    _insert_atom(db, "weekly-reflection",
                 {"score": 70, "week_label": "2026-W21", "score_band": "ok"},
                 created_at="2026-05-18T00:00:00Z")
    _insert_atom(db, "weekly-reflection",
                 {"score": 60, "week_label": "2026-W22", "score_band": "ok"},
                 created_at="2026-05-25T00:00:00Z")

    def _fake_open_atoms_db():
        return sqlite3.connect(str(db))

    monkeypatch.setattr(_portrait_mod, "open_atoms_db", _fake_open_atoms_db)

    tool = SelfPortraitTool()
    result = await tool.execute(tool.Args(), trace_id="test")

    assert result.ok is True
    assert result.output["growth_trajectory"]["trajectory"] == "declining"


@pytest.mark.asyncio
async def test_portrait_narrative_included_when_flag_true(tmp_path, monkeypatch):
    """include_narrative=True → portrait has a non-empty 'narrative' string."""
    monkeypatch.setattr(_portrait_mod, "open_atoms_db", None)

    tool = SelfPortraitTool()
    result = await tool.execute(tool.Args(include_narrative=True), trace_id="test")

    assert result.ok is True
    assert "narrative" in result.output
    assert isinstance(result.output["narrative"], str)
    assert len(result.output["narrative"]) > 20


@pytest.mark.asyncio
async def test_portrait_narrative_excluded_when_flag_false(tmp_path, monkeypatch):
    """include_narrative=False → portrait has no 'narrative' key."""
    monkeypatch.setattr(_portrait_mod, "open_atoms_db", None)

    tool = SelfPortraitTool()
    result = await tool.execute(tool.Args(include_narrative=False), trace_id="test")

    assert result.ok is True
    assert "narrative" not in result.output
