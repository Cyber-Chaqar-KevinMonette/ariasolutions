"""Tests for v0.2.13 — personas, FOSS, edge cases, validators, health,
memory namespaces, and the dream-runner enhancements."""
from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path

import pytest


# ════════════════════════════════════════════════════════════════════════════
# Personas
# ════════════════════════════════════════════════════════════════════════════


class TestPersonas:
    def test_registry_has_master_architect(self):
        from sovereign_agent.personas import REGISTRY, MASTER_ARCHITECT
        assert "master-architect" in REGISTRY
        assert REGISTRY["master-architect"] is MASTER_ARCHITECT

    def test_all_canonical_personas_registered(self):
        from sovereign_agent.personas import list_personas
        names = list_personas()
        for required in ("master-architect", "patient-auditor",
                         "friendly-builder", "gentle-advocate"):
            assert required in names

    def test_master_architect_render_includes_principles(self):
        from sovereign_agent.personas import MASTER_ARCHITECT
        r = MASTER_ARCHITECT.render()
        assert "MASTER ARCHITECT" in r
        assert "CLARITY OVER CLEVERNESS" in r
        assert "ANTI-ZOMBIE" in r
        assert "ANTI-GHOST" in r
        assert "RESPECT THE FOSS LINEAGE" in r

    def test_persona_render_is_markdown_shaped(self):
        from sovereign_agent.personas import MASTER_ARCHITECT
        r = MASTER_ARCHITECT.render()
        # Has a header and a numbered list
        assert r.startswith("# YOU ARE")
        assert "**Principles you always follow:**" in r
        assert "  1." in r

    def test_get_persona_unknown_raises(self):
        from sovereign_agent.personas import get_persona
        with pytest.raises(KeyError):
            get_persona("nonexistent")

    def test_compose_two_personas(self):
        from sovereign_agent.personas import compose
        out = compose("master-architect", "patient-auditor")
        assert "MASTER ARCHITECT" in out
        assert "PATIENT AUDITOR" in out
        assert "AND ALSO" in out

    def test_compose_single_returns_unchanged(self):
        from sovereign_agent.personas import compose, MASTER_ARCHITECT
        assert compose("master-architect") == MASTER_ARCHITECT.render()

    def test_compose_empty_returns_empty(self):
        from sovereign_agent.personas import compose
        assert compose() == ""


# ════════════════════════════════════════════════════════════════════════════
# FOSS
# ════════════════════════════════════════════════════════════════════════════


class TestFOSS:
    def test_known_licenses_includes_common_ones(self):
        from sovereign_agent.foss import KNOWN_LICENSES
        for spdx in ("MIT", "Apache-2.0", "GPL-3.0-only", "BSD-3-Clause"):
            assert spdx in KNOWN_LICENSES

    def test_detect_mit(self):
        from sovereign_agent.foss import detect_license_in_text
        text = (
            "MIT License\n\n"
            "Permission is hereby granted, free of charge, to any person "
            "obtaining a copy of this software..."
        )
        assert detect_license_in_text(text) == "MIT"

    def test_detect_apache(self):
        from sovereign_agent.foss import detect_license_in_text
        text = "Apache License, Version 2.0\n\nLicensed under..."
        assert detect_license_in_text(text) == "Apache-2.0"

    def test_detect_spdx_identifier(self):
        from sovereign_agent.foss import detect_license_in_text
        text = "// SPDX-License-Identifier: GPL-3.0-only\nint main() {}"
        assert detect_license_in_text(text) == "GPL-3.0-only"

    def test_detect_unknown_returns_none(self):
        from sovereign_agent.foss import detect_license_in_text
        assert detect_license_in_text("just some random source code") is None

    def test_license_header_for_mit(self):
        from sovereign_agent.foss import license_header
        h = license_header("MIT", project_name="my-project", author="Alice", year=2026)
        assert "MIT" in h
        assert "my-project" in h
        assert "Alice" in h
        assert "2026" in h

    def test_license_header_unknown_falls_back(self):
        from sovereign_agent.foss import license_header
        h = license_header("BSL-1.0", project_name="p", year=2026)
        assert "BSL-1.0" in h
        assert "p" in h

    def test_compatibility_permissive_pair(self):
        from sovereign_agent.foss import is_compatible_for_redistribution
        ok, _ = is_compatible_for_redistribution("MIT", "Apache-2.0")
        assert ok

    def test_compatibility_copyleft_into_permissive_blocked(self):
        from sovereign_agent.foss import is_compatible_for_redistribution
        ok, rationale = is_compatible_for_redistribution("MIT", "GPL-3.0-only")
        assert not ok
        assert "human review" in rationale

    def test_compatibility_unknown_blocked(self):
        from sovereign_agent.foss import is_compatible_for_redistribution
        ok, _ = is_compatible_for_redistribution("MIT", "WTFPL")
        assert not ok

    def test_lineage_block_renders(self):
        from sovereign_agent.foss import render_lineage_block, LineageEntry
        entries = [
            LineageEntry(source="github.com/zed/foo",
                         relation="inspired by",
                         notes="reused the lock pattern"),
        ]
        out = render_lineage_block(entries)
        assert "Prior art" in out
        assert "github.com/zed/foo" in out

    def test_lineage_block_empty(self):
        from sovereign_agent.foss import render_lineage_block
        assert render_lineage_block([]) == ""


# ════════════════════════════════════════════════════════════════════════════
# Edge Case Registry
# ════════════════════════════════════════════════════════════════════════════


class TestEdgeCases:
    def test_registry_nonempty(self):
        from sovereign_agent.edge_cases import REGISTRY
        assert len(REGISTRY) > 10

    def test_all_ids_follow_convention(self):
        from sovereign_agent.edge_cases import REGISTRY
        for ec_id in REGISTRY:
            assert ec_id.startswith("EC-"), f"bad id: {ec_id}"
            assert ec_id.count("-") == 2, f"bad shape: {ec_id}"

    def test_each_entry_has_required_fields(self):
        from sovereign_agent.edge_cases import REGISTRY
        for ec_id, ec in REGISTRY.items():
            assert ec.id == ec_id
            assert ec.title
            assert ec.location
            assert ec.description
            assert ec.fires_when
            assert ec.recovery
            assert ec.severity in ("info", "warn", "error", "critical")

    def test_get_known(self):
        from sovereign_agent.edge_cases import get
        ec = get("EC-DREAM-001")
        assert ec.id == "EC-DREAM-001"

    def test_get_unknown_raises(self):
        from sovereign_agent.edge_cases import get
        with pytest.raises(KeyError):
            get("EC-NEVER-999")

    def test_by_subsystem(self):
        from sovereign_agent.edge_cases import by_subsystem
        dream_cases = by_subsystem("EC-DREAM")
        assert len(dream_cases) >= 5
        for ec in dream_cases:
            assert ec.id.startswith("EC-DREAM")

    def test_by_severity(self):
        from sovereign_agent.edge_cases import by_severity, REGISTRY
        warns = by_severity("warn")
        assert len(warns) > 0
        all_severities = {ec.severity for ec in REGISTRY.values()}
        assert "warn" in all_severities

    def test_render_table_includes_header(self):
        from sovereign_agent.edge_cases import render_table
        out = render_table()
        assert "| ID |" in out
        assert "EC-DREAM-001" in out

    def test_track_does_not_raise_on_unknown(self):
        from sovereign_agent.edge_cases import track
        # Observability must never break the caller.
        track("EC-NONEXISTENT-999", payload={"foo": "bar"})

    def test_track_known_emits_event(self):
        from sovereign_agent.edge_cases import track
        # Smoke: must not raise. We don't assert the event schema here
        # since the events plane has its own tests.
        track("EC-DREAM-001", payload={"dream_id": "dream-test-01"})


# ════════════════════════════════════════════════════════════════════════════
# Validators
# ════════════════════════════════════════════════════════════════════════════


class TestValidators:
    def test_validate_valid_python(self):
        from sovereign_agent.validators import validate_python_source
        text = "def foo():\n    return 42\n"
        r = validate_python_source(text)
        assert r.ok
        assert not r.errors

    def test_validate_python_syntax_error(self):
        from sovereign_agent.validators import validate_python_source
        text = "def foo(:\n    return 42\n"
        r = validate_python_source(text)
        assert not r.ok
        assert any("SyntaxError" in e for e in r.errors)

    def test_validate_python_mixed_indentation(self):
        from sovereign_agent.validators import validate_python_source
        text = "def foo():\n\treturn 42\n\ndef bar():\n    return 1\n"
        r = validate_python_source(text)
        assert not r.ok
        assert any("mixed tabs and spaces" in e for e in r.errors)

    def test_validate_empty_python_fails(self):
        from sovereign_agent.validators import validate_python_source
        r = validate_python_source("")
        assert not r.ok

    def test_validate_python_with_null_bytes(self):
        from sovereign_agent.validators import validate_python_source
        r = validate_python_source("def foo():\x00\n    return 1\n")
        assert not r.ok
        assert any("null bytes" in e for e in r.errors)

    def test_validate_valid_json(self):
        from sovereign_agent.validators import validate_json
        r = validate_json('{"a": 1, "b": [2, 3]}')
        assert r.ok

    def test_validate_invalid_json(self):
        from sovereign_agent.validators import validate_json
        r = validate_json('{"a": 1, "b": ')
        assert not r.ok
        assert any("JSONDecodeError" in e for e in r.errors)

    def test_validate_valid_yaml(self):
        from sovereign_agent.validators import validate_yaml
        r = validate_yaml("foo: bar\nbaz: 1\n")
        assert r.ok

    def test_validate_markdown_simple(self):
        from sovereign_agent.validators import validate_markdown
        r = validate_markdown("# title\n\nsome text\n")
        assert r.ok

    def test_validate_text_empty_fails(self):
        from sovereign_agent.validators import validate_text
        assert not validate_text("").ok

    def test_validate_file_dispatches_by_extension(self, tmp_path):
        from sovereign_agent.validators import validate_file
        p = tmp_path / "test.py"
        p.write_text("def foo():\n    return 1\n")
        r = validate_file(p)
        assert r.kind == "python"
        assert r.ok

    def test_validate_file_binary_skipped(self, tmp_path):
        from sovereign_agent.validators import validate_file
        p = tmp_path / "test.png"
        p.write_bytes(b"\x89PNG\r\n\x1a\n")
        r = validate_file(p)
        assert r.kind == "binary"
        assert r.ok  # binary files are skipped, not failed

    def test_validate_tree_skips_quarantine(self, tmp_path):
        from sovereign_agent.validators import validate_tree
        (tmp_path / "good.py").write_text("x = 1\n")
        q = tmp_path / "quarantine"
        q.mkdir()
        (q / "bad.py").write_text("def foo(:\n  pass\n")
        results = validate_tree(tmp_path)
        # Should only see good.py — quarantine is excluded.
        assert len(results) == 1
        assert "good.py" in results[0].path

    def test_quarantine_file_moves_and_writes_companion(self, tmp_path):
        from sovereign_agent.validators import (
            quarantine_file, validate_python_source,
        )
        p = tmp_path / "bad.py"
        p.write_text("def foo(:\n    pass\n")
        result = validate_python_source(p.read_text(), path="bad.py")
        new_path = quarantine_file(p, cycle_dir=tmp_path, result=result)
        assert not p.exists()
        assert new_path.exists()
        assert new_path.parent.name == "quarantine"
        # Companion exists
        companion = new_path.with_suffix(new_path.suffix + ".errors.json")
        assert companion.exists()
        data = json.loads(companion.read_text())
        assert data["ok"] is False

    def test_quarantine_failures_idempotent(self, tmp_path):
        from sovereign_agent.validators import (
            quarantine_failures, validate_tree,
        )
        (tmp_path / "bad1.py").write_text("def foo(:\n    pass\n")
        (tmp_path / "good.py").write_text("x = 1\n")
        results = validate_tree(tmp_path)
        q, s = quarantine_failures(results, cycle_dir=tmp_path)
        assert q == 1  # one bad file moved
        assert s == 0


# ════════════════════════════════════════════════════════════════════════════
# Memory Namespaces
# ════════════════════════════════════════════════════════════════════════════


class TestMemoryNamespaces:
    def _make_atoms_db(self, tmp_path: Path) -> sqlite3.Connection:
        """Build a minimal atoms.db with just enough schema for tag tests."""
        db_path = tmp_path / "atoms.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("""
            CREATE TABLE atoms (
                atom_id TEXT PRIMARY KEY,
                summary TEXT,
                scope_tags TEXT,
                created_by TEXT
            )
        """)
        conn.execute(
            "INSERT INTO atoms VALUES (?, ?, ?, ?)",
            ("atom-1", "first atom", None,
             json.dumps({"actor": "dream_atomize"})),
        )
        conn.execute(
            "INSERT INTO atoms VALUES (?, ?, ?, ?)",
            ("atom-2", "second atom", json.dumps({"projects": ["other"]}),
             json.dumps({"actor": "dream_atomize"})),
        )
        conn.commit()
        return conn

    def test_is_valid_project_name(self):
        from sovereign_agent.memory_namespaces import is_valid_project_name
        assert is_valid_project_name("genesis-seeds")
        assert is_valid_project_name("project_v2.1")
        assert not is_valid_project_name("")
        assert not is_valid_project_name("with space")
        assert not is_valid_project_name("with/slash")
        assert not is_valid_project_name("a" * 65)

    def test_normalize_project_name(self):
        from sovereign_agent.memory_namespaces import normalize_project_name
        assert normalize_project_name("  good-name  ") == "good-name"
        with pytest.raises(ValueError):
            normalize_project_name("bad name")

    def test_tag_atom_idempotent(self, tmp_path):
        from sovereign_agent.memory_namespaces import (
            tag_atom, projects_for_atom,
        )
        conn = self._make_atoms_db(tmp_path)
        try:
            assert tag_atom(conn, "atom-1", "genesis") is True
            assert tag_atom(conn, "atom-1", "genesis") is False  # already
            assert "genesis" in projects_for_atom(conn, "atom-1")
        finally:
            conn.close()

    def test_tag_atom_extends_existing_projects(self, tmp_path):
        from sovereign_agent.memory_namespaces import (
            tag_atom, projects_for_atom,
        )
        conn = self._make_atoms_db(tmp_path)
        try:
            tag_atom(conn, "atom-2", "genesis")
            tags = projects_for_atom(conn, "atom-2")
            assert "other" in tags
            assert "genesis" in tags
        finally:
            conn.close()

    def test_tag_atom_missing_returns_false(self, tmp_path):
        from sovereign_agent.memory_namespaces import tag_atom
        conn = self._make_atoms_db(tmp_path)
        try:
            assert tag_atom(conn, "atom-9999", "genesis") is False
        finally:
            conn.close()

    def test_untag_atom(self, tmp_path):
        from sovereign_agent.memory_namespaces import (
            tag_atom, untag_atom, projects_for_atom,
        )
        conn = self._make_atoms_db(tmp_path)
        try:
            tag_atom(conn, "atom-1", "genesis")
            assert untag_atom(conn, "atom-1", "genesis") is True
            assert "genesis" not in projects_for_atom(conn, "atom-1")
            # Untagging again is a no-op
            assert untag_atom(conn, "atom-1", "genesis") is False
        finally:
            conn.close()

    def test_tag_atoms_by_creator(self, tmp_path):
        from sovereign_agent.memory_namespaces import (
            tag_atoms_by_creator, projects_for_atom,
        )
        conn = self._make_atoms_db(tmp_path)
        try:
            n = tag_atoms_by_creator(
                conn, actor_pattern="dream_atomize", project="bulk",
            )
            assert n == 2
            assert "bulk" in projects_for_atom(conn, "atom-1")
            assert "bulk" in projects_for_atom(conn, "atom-2")
            # Idempotent on second call
            n2 = tag_atoms_by_creator(
                conn, actor_pattern="dream_atomize", project="bulk",
            )
            assert n2 == 0
        finally:
            conn.close()


# ════════════════════════════════════════════════════════════════════════════
# Health
# ════════════════════════════════════════════════════════════════════════════


class TestHealth:
    def test_thresholds_are_sane(self):
        from sovereign_agent.health import (
            ZOMBIE_THRESHOLD_SECONDS, STALE_LOCK_THRESHOLD_SECONDS,
            GHOST_DREAM_THRESHOLD_SECONDS, IDLE_CYCLE_WINDOW,
            IDLE_ATOM_THRESHOLD,
        )
        assert ZOMBIE_THRESHOLD_SECONDS >= 3600  # at least 1 hour
        assert STALE_LOCK_THRESHOLD_SECONDS >= 60
        assert GHOST_DREAM_THRESHOLD_SECONDS >= 60
        assert IDLE_CYCLE_WINDOW >= 2
        assert IDLE_ATOM_THRESHOLD >= 0

    def test_health_report_ok_when_empty(self):
        from sovereign_agent.health import HealthReport
        r = HealthReport()
        assert r.ok
        assert "no issues" in r.summary_line()

    def test_health_report_summary_with_findings(self):
        from sovereign_agent.health import HealthReport, HealthFinding
        r = HealthReport(findings=[
            HealthFinding(
                edge_case_id="EC-HEALTH-001", severity="warn",
                target="cont-x", target_kind="continuation", summary="t",
            ),
            HealthFinding(
                edge_case_id="EC-HEALTH-002", severity="warn",
                target="dream-y", target_kind="dream", summary="t",
            ),
        ])
        assert r.ok  # warn is not error
        line = r.summary_line()
        assert "2" in line
        assert "warn" in line

    def test_process_alive_self(self):
        from sovereign_agent.health import _process_alive
        assert _process_alive(os.getpid())

    def test_process_alive_dead(self):
        from sovereign_agent.health import _process_alive
        # PID 1 is init/systemd — alive on Linux. Use a high unlikely PID.
        assert _process_alive(99999999) is False

    def test_scan_zombies_finds_stalled_in_progress(self, tmp_path):
        from sovereign_agent.health import scan_zombies

        class FakeCont:
            def __init__(self, task_id, status, updated_at):
                self.task_id = task_id
                self.planner = "test"
                self.status = status
                self.updated_at = updated_at

        class FakeContStore:
            root = str(tmp_path)
            def list_all(self):
                return [
                    FakeCont("cont-old", "in_progress",
                             "2020-01-01T00:00:00.000000Z"),
                    FakeCont("cont-fresh", "in_progress",
                             "2099-01-01T00:00:00.000000Z"),
                    FakeCont("cont-done", "done",
                             "2020-01-01T00:00:00.000000Z"),
                ]
            def _lock_path(self, task_id):
                return tmp_path / f"{task_id}.lock"

        findings = scan_zombies(FakeContStore())
        assert len(findings) == 1
        assert findings[0].target == "cont-old"

    def test_scan_idle_cycles(self, tmp_path):
        from sovereign_agent.health import scan_idle_cycles

        class FakeCycle:
            def __init__(self, n, files):
                self.cycle_number = n
                self.atoms_written = files
                self.files_written = files

        class FakeDream:
            def __init__(self, did, cycles):
                self.dream_id = did
                self.status = "active"
                self.cycles = cycles
                self.updated_at = "2099-01-01T00:00:00.000000Z"

        class FakeStore:
            def list_all(self, *, status=None):
                return [
                    FakeDream("dream-idle", [
                        FakeCycle(1, 0), FakeCycle(2, 1),
                        FakeCycle(3, 0),
                    ]),
                    FakeDream("dream-busy", [
                        FakeCycle(1, 50), FakeCycle(2, 60),
                        FakeCycle(3, 40),
                    ]),
                ]

        findings = scan_idle_cycles(FakeStore())
        idle_targets = [f.target for f in findings]
        assert "dream-idle" in idle_targets
        assert "dream-busy" not in idle_targets

    def test_plan_repairs_for_stale_lock(self):
        from sovereign_agent.health import HealthFinding, plan_repairs, HealthReport
        report = HealthReport(findings=[
            HealthFinding(
                edge_case_id="EC-CONT-002", severity="warn",
                target="cont-zombie", target_kind="lock",
                summary="stale lock",
                details={"lock_path": "/tmp/cont-zombie.lock"},
            ),
        ])
        actions = plan_repairs(report)
        assert len(actions) == 1
        assert actions[0].kind == "remove_lock"

    def test_apply_repairs_dry_run(self):
        from sovereign_agent.health import RepairAction, apply_repairs
        actions = [
            RepairAction(
                finding_id="x", kind="remove_lock",
                target="/nonexistent.lock",
                description="test",
            ),
        ]
        out = apply_repairs(actions, dry_run=True)
        assert out[0].applied is False  # dry-run never applies
        assert out[0].error == ""


# ════════════════════════════════════════════════════════════════════════════
# Dream — fcntl lock + atoms_written field
# ════════════════════════════════════════════════════════════════════════════


class TestDreamHardening:
    def test_cycle_entry_has_v0213_fields(self):
        from sovereign_agent.dream import CycleEntry
        c = CycleEntry(
            cycle_number=1, task_id="t", started_at="2099-01-01T00:00:00Z",
        )
        # v0.2.13 fields default to 0
        assert c.atoms_written == 0
        assert c.quarantined_count == 0

    def test_cycle_entry_roundtrips_atoms_written(self, tmp_path):
        from sovereign_agent.dream import (
            DreamStore, DreamCaps, CycleEntry,
        )
        store = DreamStore(root=tmp_path / "dreams", work_root=tmp_path / "work")
        d = store.create(goal="test", caps=DreamCaps(max_files=10))
        d.cycles.append(CycleEntry(
            cycle_number=1, task_id="cycle-x-001",
            started_at="2099-01-01T00:00:00Z",
            files_written=5, atoms_written=3, quarantined_count=2,
        ))
        store.save(d)
        d2 = store.get(d.dream_id)
        assert d2.cycles[0].atoms_written == 3
        assert d2.cycles[0].quarantined_count == 2

    def test_count_files_under_skips_quarantine(self, tmp_path):
        from sovereign_agent.dream import count_files_under
        (tmp_path / "good.py").write_text("x = 1\n")
        (tmp_path / "good2.py").write_text("y = 2\n")
        q = tmp_path / "quarantine"
        q.mkdir()
        (q / "bad.py").write_text("broken\n")
        # Only counts the 2 good files — quarantine is skipped
        assert count_files_under(tmp_path) == 2

    def test_dream_lock_is_exclusive(self, tmp_path):
        from sovereign_agent.dream import DreamStore, DreamLocked
        store = DreamStore(root=tmp_path / "dreams", work_root=tmp_path / "work")
        d = store.create(goal="test")
        with store.lock(d.dream_id) as held:
            held.notes = "locked-edit"
            # While held, a non-blocking lock attempt must fail
            with pytest.raises(DreamLocked):
                with store.lock(d.dream_id, blocking=False):
                    pass
        # After release, lock works
        with store.lock(d.dream_id) as d2:
            assert d2.notes == "locked-edit"

    def test_dream_lock_persists_changes_on_clean_exit(self, tmp_path):
        from sovereign_agent.dream import DreamStore
        store = DreamStore(root=tmp_path / "dreams", work_root=tmp_path / "work")
        d = store.create(goal="test")
        with store.lock(d.dream_id) as held:
            held.notes = "via lock context"
        loaded = store.get(d.dream_id)
        assert loaded.notes == "via lock context"

    def test_dream_lock_does_not_persist_on_exception(self, tmp_path):
        from sovereign_agent.dream import DreamStore
        store = DreamStore(root=tmp_path / "dreams", work_root=tmp_path / "work")
        d = store.create(goal="test")
        d.notes = "before"
        store.save(d)
        with pytest.raises(RuntimeError):
            with store.lock(d.dream_id) as held:
                held.notes = "should not persist"
                raise RuntimeError("oops")
        loaded = store.get(d.dream_id)
        assert loaded.notes == "before"

    def test_dream_lock_timeout(self, tmp_path):
        """Holding the lock should make a second short-timeout lock fail."""
        from sovereign_agent.dream import DreamStore, DreamLocked
        store = DreamStore(root=tmp_path / "dreams", work_root=tmp_path / "work")
        d = store.create(goal="test")
        with store.lock(d.dream_id):
            t0 = time.monotonic()
            with pytest.raises(DreamLocked):
                with store.lock(d.dream_id, blocking=True,
                                timeout_seconds=0.5):
                    pass
            elapsed = time.monotonic() - t0
            # Allow some slack — should be under 1.5s
            assert elapsed < 1.5
