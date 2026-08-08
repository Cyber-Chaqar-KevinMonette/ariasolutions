"""Tests for v0.2.18.1 — the hardening release.

These tests target the specific failure modes the operator can hit:
  * Doctor reports something sensible on empty / partial / full installs
  * Migration backfill detects pre-existing schemas correctly
  * apply_pending after backfill runs only truly new migrations
  * Info command works regardless of DB state
  * Doctor catches missing channels (regression: previous use of _CHANNELS)
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest


# ════════════════════════════════════════════════════════════════════════════
# Doctor diagnostic
# ════════════════════════════════════════════════════════════════════════════


class TestDoctor:
    def test_runs_on_empty_install(self, tmp_path, monkeypatch):
        from sovereign_agent.config import SETTINGS, Paths
        new_paths = Paths(config_dir=tmp_path / "c", data_dir=tmp_path / "d")
        new_paths.ensure()
        object.__setattr__(SETTINGS, "paths", new_paths)
        from sovereign_agent.doctor import run_diagnostic
        report = run_diagnostic()
        # Should not throw; verdict may be healthy or have info-level only
        assert report is not None
        assert len(report.checks) >= 10

    def test_doctor_finds_all_25_channels(self, tmp_path, monkeypatch):
        from sovereign_agent.config import SETTINGS, Paths
        new_paths = Paths(config_dir=tmp_path / "c", data_dir=tmp_path / "d")
        new_paths.ensure()
        object.__setattr__(SETTINGS, "paths", new_paths)
        from sovereign_agent.doctor import check_channels
        result = check_channels()
        assert result.level == "ok"
        assert "25" in result.summary  # 19 baseline + 5 v0.2.18 additions + people_health

    def test_doctor_constitution_check_all_seven(self):
        from sovereign_agent.doctor import check_seven_commitments
        result = check_seven_commitments()
        assert result.level == "ok"
        assert "7 commitments" in result.summary

    def test_doctor_handles_corrupt_db(self, tmp_path):
        from sovereign_agent.config import SETTINGS, Paths
        new_paths = Paths(config_dir=tmp_path / "c", data_dir=tmp_path / "d")
        new_paths.ensure()
        object.__setattr__(SETTINGS, "paths", new_paths)
        # Write garbage at atoms.db path
        new_paths.atoms_db.write_bytes(b"this is not a sqlite database\x00")
        from sovereign_agent.doctor import check_atoms_db
        result = check_atoms_db()
        # Should not crash; should report error or corruption clearly
        assert result.level == "error"


# ════════════════════════════════════════════════════════════════════════════
# Migration backfill — the key feature for safe upgrades
# ════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def schema_db(tmp_path):
    """A DB with v0.2.16-era schemas but no schema_migrations table."""
    db = tmp_path / "atoms.db"
    conn = sqlite3.connect(str(db), isolation_level=None)
    conn.executescript("""
        CREATE TABLE atoms (atom_id TEXT PRIMARY KEY);
        CREATE TABLE people (person_id TEXT PRIMARY KEY);
        CREATE TABLE people_aliases (alias_id TEXT PRIMARY KEY, person_id TEXT);
        CREATE TABLE people_facts (fact_id TEXT PRIMARY KEY, person_id TEXT);
        CREATE TABLE recalls (recall_id TEXT PRIMARY KEY);
        CREATE TABLE recall_sources (recall_id TEXT, source_id TEXT);
        CREATE TABLE task_records (task_id TEXT PRIMARY KEY);
    """)
    yield conn
    conn.close()


class TestBackfill:
    def test_detect_finds_existing_schemas(self, schema_db):
        from sovereign_agent.migrations import detect_applied
        detected = detect_applied(schema_db)
        # Should detect at least atoms, people, recalls, tasks
        assert "002_atoms" in detected
        assert "003_people" in detected
        assert "004_recalls" in detected
        assert "005_tasks" in detected

    def test_detect_skips_missing(self, schema_db):
        from sovereign_agent.migrations import detect_applied
        detected = detect_applied(schema_db)
        # No reasoning_traces table → not detected
        assert "009_reasoning" not in detected
        assert "013_heartbeat" not in detected

    def test_backfill_inserts_rows(self, schema_db):
        from sovereign_agent.migrations import (
            backfill_applied, applied_migrations, reset_registry
        )
        reset_registry()
        backfilled = backfill_applied(schema_db)
        applied = applied_migrations(schema_db)
        assert set(backfilled) <= applied
        # All detected migrations should now be in schema_migrations
        for name in backfilled:
            row = schema_db.execute(
                "SELECT status FROM schema_migrations WHERE name = ?",
                (name,),
            ).fetchone()
            assert row is not None
            assert row[0] == "applied"

    def test_backfill_idempotent(self, schema_db):
        from sovereign_agent.migrations import (
            backfill_applied, reset_registry
        )
        reset_registry()
        first = backfill_applied(schema_db)
        second = backfill_applied(schema_db)
        assert len(first) > 0
        assert len(second) == 0     # already backfilled

    def test_backfill_does_not_re_run_sql(self, tmp_path):
        """The point of backfill: do NOT execute migration SQL whose schema
        already exists. Otherwise a duplicate CREATE TABLE would fail."""
        from sovereign_agent.migrations import (
            register, Migration, backfill_applied, apply_pending,
            reset_registry,
        )
        reset_registry()
        db = tmp_path / "atoms.db"
        conn = sqlite3.connect(str(db), isolation_level=None)
        # Pre-create the people table (as if from old install)
        conn.execute("CREATE TABLE people (person_id TEXT PRIMARY KEY)")
        conn.execute("CREATE TABLE people_aliases (a TEXT)")
        conn.execute("CREATE TABLE people_facts (f TEXT)")
        # Register a migration whose body would FAIL if re-run
        # (we use a body that would crash on duplicate CREATE)
        register(Migration(
            name="003_people", version="0.2.15",
            body="CREATE TABLE people (oops INTEGER)",  # would fail
        ))
        # Backfill should detect and mark applied WITHOUT running the SQL
        backfilled = backfill_applied(conn)
        assert "003_people" in backfilled
        # apply_pending should then skip it (already marked applied)
        applied = apply_pending(conn)
        assert "003_people" not in applied
        conn.close()


# ════════════════════════════════════════════════════════════════════════════
# Info command (smoke)
# ════════════════════════════════════════════════════════════════════════════


class TestInfo:
    def test_info_runs_without_atoms_db(self, tmp_path, monkeypatch):
        from sovereign_agent.config import SETTINGS, Paths
        new_paths = Paths(config_dir=tmp_path / "c", data_dir=tmp_path / "d")
        new_paths.ensure()
        object.__setattr__(SETTINGS, "paths", new_paths)
        # Import; should not require atoms.db to exist
        from sovereign_agent import __version__
        assert __version__ is not None


# ════════════════════════════════════════════════════════════════════════════
# Constitution — additional edge cases
# ════════════════════════════════════════════════════════════════════════════


class TestConstitutionEdges:
    def test_zero_confidence_with_source_passes(self):
        from sovereign_agent.constitution import check_action
        report = check_action({
            "tier": 0, "confidence": 0.0, "source": "operator",
        })
        # All commitments pass
        assert report.passed

    def test_low_confidence_no_source_passes(self):
        """Low confidence without a source is fine — we're not claiming much."""
        from sovereign_agent.constitution import check_action
        report = check_action({"tier": 0, "confidence": 0.3})
        # calibrated_uncertainty should pass at low confidence
        cu = [v for v in report.verdicts
              if v.commitment_id == "calibrated_uncertainty"]
        assert cu[0].passed

    def test_render_works_on_passing_report(self):
        from sovereign_agent.constitution import check_action
        report = check_action({"tier": 0})
        rendered = report.render()
        assert "✓" in rendered or "all commitments hold" in rendered.lower()


# ════════════════════════════════════════════════════════════════════════════
# Archive — extended scenarios
# ════════════════════════════════════════════════════════════════════════════


class TestArchiveExtended:
    def test_put_binary(self, tmp_path):
        db = tmp_path / "atoms.db"
        conn = sqlite3.connect(str(db), isolation_level=None)
        from sovereign_agent.archive import ContentArchive
        arc = ContentArchive(conn)
        h = arc.put(b"\x00\x01\x02\x03\xff\xfe")
        retrieved = arc.get(h)
        assert retrieved == b"\x00\x01\x02\x03\xff\xfe"
        conn.close()

    def test_get_missing_returns_none(self, tmp_path):
        db = tmp_path / "atoms.db"
        conn = sqlite3.connect(str(db), isolation_level=None)
        from sovereign_agent.archive import ContentArchive
        arc = ContentArchive(conn)
        assert arc.get("0" * 64) is None
        assert arc.info("0" * 64) is None
        conn.close()

    def test_seal_is_irreversible(self, tmp_path):
        db = tmp_path / "atoms.db"
        conn = sqlite3.connect(str(db), isolation_level=None)
        from sovereign_agent.archive import ContentArchive
        arc = ContentArchive(conn)
        h = arc.put("important")
        arc.seal(h)
        assert arc.info(h).sealed is True
        # No public API to unseal — confirmed by the spec
        # gc on a sealed blob is a no-op
        removed = arc.gc()
        assert h not in removed
        conn.close()


# ════════════════════════════════════════════════════════════════════════════
# Provenance — additional walks
# ════════════════════════════════════════════════════════════════════════════


class TestProvenanceExtended:
    def test_node_with_no_upstream(self, tmp_path):
        """An orphan atom (no parent, no claims) walks back to just itself."""
        db = tmp_path / "atoms.db"
        conn = sqlite3.connect(str(db), isolation_level=None)
        conn.executescript("""
            CREATE TABLE atoms (
                atom_id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                summary TEXT, content_ref TEXT,
                claims TEXT NOT NULL DEFAULT '[]',
                parents TEXT NOT NULL DEFAULT '[]',
                confidence REAL, created_at TEXT, created_by TEXT,
                parent_atom_id TEXT
            )
        """)
        conn.execute(
            "INSERT INTO atoms (atom_id, type, claims, parents) "
            "VALUES ('at-orphan', 'event', '[]', '[]')"
        )
        conn.commit()
        from sovereign_agent.provenance import walk_backward
        g = walk_backward(conn, "at-orphan")
        # The orphan itself is the only node; no edges
        assert g.nodes == {"at-orphan"}
        assert len(g.edges) == 0
        conn.close()

    def test_render_handles_empty_graph(self, tmp_path):
        db = tmp_path / "atoms.db"
        conn = sqlite3.connect(str(db), isolation_level=None)
        from sovereign_agent.provenance import walk_backward
        g = walk_backward(conn, "at-nonexistent")
        rendered = g.render()
        # Should not crash; should produce some output
        assert isinstance(rendered, str)
        assert len(rendered) > 0
        conn.close()
