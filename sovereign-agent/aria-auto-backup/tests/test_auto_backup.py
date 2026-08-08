"""Behavior tests for aria-auto-backup — prove BackupSentinel + the patched
backup.py actually work, using a shadow copy of the whole package (never
touches real src/). STAGED ONLY: never promoted — see
test_auto_backup_live.py for the promoted copy."""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest


def _find_repo_root(start: Path) -> Path:
    for candidate in (start, *start.parents):
        if (candidate / "src" / "sovereign_agent" / "backup.py").is_file():
            return candidate
    raise RuntimeError("could not locate repo root from " + str(start))


def _find_staging_root(start: Path) -> Path:
    for candidate in (start, *start.parents):
        if (candidate / "aria-auto-backup" / "patcher.py").is_file():
            return candidate / "aria-auto-backup"
    raise RuntimeError("could not locate aria-auto-backup/ from " + str(start))


REPO_ROOT = _find_repo_root(Path(__file__).resolve())
STAGING = _find_staging_root(Path(__file__).resolve())


def _build_shadow(tmp_path) -> Path:
    import shutil

    sys.path.insert(0, str(STAGING))
    from patcher import patch_backup_py, patch_stewardship_init

    shadow = tmp_path / "shadow"
    shutil.copytree(REPO_ROOT / "src" / "sovereign_agent", shadow / "src" / "sovereign_agent")
    shutil.copytree(REPO_ROOT / "sql", shadow / "sql")
    for pyc in shadow.rglob("__pycache__"):
        shutil.rmtree(pyc)

    backup_py = shadow / "src" / "sovereign_agent" / "backup.py"
    patched, _ = patch_backup_py(backup_py.read_text(encoding="utf-8"))
    backup_py.write_text(patched, encoding="utf-8")

    init_py = shadow / "src" / "sovereign_agent" / "stewardship" / "__init__.py"
    patched, _ = patch_stewardship_init(init_py.read_text(encoding="utf-8"))
    init_py.write_text(patched, encoding="utf-8")

    (shadow / "src" / "sovereign_agent" / "stewardship" / "backup_sentinel.py").write_text(
        (STAGING / "payload" / "src" / "sovereign_agent" / "stewardship" / "backup_sentinel.py")
        .read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    return shadow / "src"


@pytest.fixture
def shadow_pkg(tmp_path, monkeypatch):
    shadow_src = _build_shadow(tmp_path)
    saved = {
        name: mod for name, mod in sys.modules.items()
        if name == "sovereign_agent" or name.startswith("sovereign_agent.")
    }
    for name in saved:
        del sys.modules[name]

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    sys.path.insert(0, str(shadow_src))
    try:
        import sovereign_agent
        yield sovereign_agent
    finally:
        sys.path.remove(str(shadow_src))
        for name in list(sys.modules):
            if name == "sovereign_agent" or name.startswith("sovereign_agent."):
                del sys.modules[name]
        sys.modules.update(saved)


def _make_data_dir(tmp_path) -> Path:
    """A small fake data_dir with a non-atoms SQLite DB in a subdir —
    the exact case the online-backup generalization exists for."""
    data_dir = tmp_path / "gym-data"
    (data_dir / "shards").mkdir(parents=True)
    (data_dir / "notes.txt").write_text("hello", encoding="utf-8")
    for db_rel in ("palace.db", "shards/emotions.db"):
        conn = sqlite3.connect(data_dir / db_rel)
        conn.execute("CREATE TABLE t (x TEXT)")
        conn.execute("INSERT INTO t VALUES ('alive')")
        conn.commit()
        conn.close()
    return data_dir


# ── registration ──────────────────────────────────────────────────────────


def test_backup_sentinel_registered(shadow_pkg):
    from sovereign_agent.stewardship import registry

    assert "backup" in registry.registered_ids()


# ── backup root safety ────────────────────────────────────────────────────


def test_foreign_data_dir_never_uses_production_backup_root(shadow_pkg, tmp_path):
    """THE pollution guard: a sentinel constructed on a test/foreign data_dir
    must resolve its backup root to a SIBLING of that dir, never the real
    production root."""
    from sovereign_agent.stewardship.backup_sentinel import BackupSentinel

    data_dir = _make_data_dir(tmp_path)
    s = BackupSentinel(data_dir=data_dir)
    root = s._backup_root()
    assert root == data_dir.parent / "sovereign-agent-backups"
    assert str(Path.home() / "AA-Erebo" / "sov-backups") not in str(root)


def test_env_override_wins(shadow_pkg, tmp_path, monkeypatch):
    from sovereign_agent.stewardship.backup_sentinel import BackupSentinel

    monkeypatch.setenv("SOV_BACKUP_ROOT", str(tmp_path / "custom-root"))
    s = BackupSentinel(data_dir=_make_data_dir(tmp_path))
    assert s._backup_root() == tmp_path / "custom-root"


# ── cadence / overdue ─────────────────────────────────────────────────────


def test_overdue_true_with_no_snapshots(shadow_pkg, tmp_path):
    from sovereign_agent.stewardship.backup_sentinel import BackupSentinel

    s = BackupSentinel(data_dir=_make_data_dir(tmp_path))
    assert s.overdue() is True


def test_scan_takes_and_verifies_a_snapshot_when_overdue(shadow_pkg, tmp_path):
    from sovereign_agent.stewardship.backup_sentinel import BackupSentinel

    data_dir = _make_data_dir(tmp_path)
    s = BackupSentinel(data_dir=data_dir)
    report = s.scan()
    assert report.details["took_snapshot"] is True
    assert report.details["verify_ok"] is True
    assert report.findings_count == 0
    assert s.overdue() is False


def test_scan_noops_when_fresh(shadow_pkg, tmp_path):
    from sovereign_agent.stewardship.backup_sentinel import BackupSentinel

    data_dir = _make_data_dir(tmp_path)
    s = BackupSentinel(data_dir=data_dir)
    s.scan()  # takes the first snapshot
    report2 = s.scan()  # fresh now — must not take another
    assert report2.details["took_snapshot"] is False
    assert "fresh" in report2.summary


def test_every_db_in_snapshot_is_openable_not_torn(shadow_pkg, tmp_path):
    """The GAP-4 proof: every .db in the snapshot (including a NON-atoms DB
    in a subdirectory) came through the online-backup API and opens as a
    valid SQLite database with its data intact."""
    from sovereign_agent.stewardship.backup_sentinel import BackupSentinel

    data_dir = _make_data_dir(tmp_path)
    s = BackupSentinel(data_dir=data_dir)
    report = s.scan()
    snap_dir = Path(report.details["backup_root"]) / report.details["snapshot_id"]
    dbs = sorted(p.relative_to(snap_dir / "data") for p in (snap_dir / "data").rglob("*.db"))
    assert Path("palace.db") in dbs
    assert Path("shards/emotions.db") in dbs
    for rel in dbs:
        conn = sqlite3.connect(snap_dir / "data" / rel)
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        conn.close()
    # And no stray WAL/SHM sidecars snuck in via the copy path.
    assert list((snap_dir / "data").rglob("*.db-wal")) == []
    assert list((snap_dir / "data").rglob("*.db-shm")) == []


# ── health_status ─────────────────────────────────────────────────────────


def test_health_warning_when_no_snapshots(shadow_pkg, tmp_path):
    from sovereign_agent.stewardship.backup_sentinel import BackupSentinel

    s = BackupSentinel(data_dir=_make_data_dir(tmp_path))
    hs = s.health_status()
    assert hs.level == "warning"
    assert "no snapshots yet" in hs.summary


def test_health_ok_after_scan(shadow_pkg, tmp_path):
    from sovereign_agent.stewardship.backup_sentinel import BackupSentinel

    s = BackupSentinel(data_dir=_make_data_dir(tmp_path))
    s.scan()
    hs = s.health_status()
    assert hs.level == "ok"


def test_health_status_never_snapshots(shadow_pkg, tmp_path, monkeypatch):
    """gather_health() runs on an 8s cockpit cadence — health_status() must
    never take a snapshot, no matter how overdue."""
    from sovereign_agent import backup as _bk
    from sovereign_agent.stewardship.backup_sentinel import BackupSentinel

    def _boom(**kw):
        raise AssertionError("health_status() must never call backup.snapshot()")

    monkeypatch.setattr(_bk, "snapshot", _boom)
    s = BackupSentinel(data_dir=_make_data_dir(tmp_path))
    hs = s.health_status()  # overdue (no snapshots) — still must not snapshot
    assert hs.level in ("ok", "warning", "error")


def test_health_error_when_last_verify_failed(shadow_pkg, tmp_path):
    from sovereign_agent.stewardship.backup_sentinel import BackupSentinel

    data_dir = _make_data_dir(tmp_path)
    s = BackupSentinel(data_dir=data_dir)
    s.scan()
    # Poison the cached catalog to simulate a failed verify.
    blob = s.load_catalog(name="auto_backup")
    blob["verify_ok"] = False
    blob["error"] = "simulated hash mismatch"
    s.save_catalog(blob, name="auto_backup")
    hs = s.health_status()
    assert hs.level == "error"
    assert "FAILED" in hs.summary


def test_cadence_env_var_respected(shadow_pkg, tmp_path, monkeypatch):
    from sovereign_agent.stewardship.backup_sentinel import BackupSentinel

    data_dir = _make_data_dir(tmp_path)
    s = BackupSentinel(data_dir=data_dir)
    s.scan()
    assert s.overdue() is False
    # An absurdly tiny cadence makes the just-taken snapshot instantly stale.
    monkeypatch.setenv("SOV_BACKUP_CADENCE_HOURS", "0.000001")
    assert s.overdue() is True
