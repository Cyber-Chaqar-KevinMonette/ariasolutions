"""Behavior tests for aria-auto-backup, promoted to live tests/ — tests
the REAL, already-patched `sovereign_agent.backup` /
`sovereign_agent.stewardship.backup_sentinel` directly, no shadow copy, no
`sys.modules` manipulation. See test_auto_backup.py (staged only) for the
shadow-copy pre-apply verification version.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest


def _make_data_dir(tmp_path) -> Path:
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


def test_backup_sentinel_registered():
    from sovereign_agent.stewardship import registry

    assert "backup" in registry.registered_ids()


def test_foreign_data_dir_never_uses_production_backup_root(tmp_path):
    from sovereign_agent.stewardship.backup_sentinel import BackupSentinel

    data_dir = _make_data_dir(tmp_path)
    s = BackupSentinel(data_dir=data_dir)
    root = s._backup_root()
    assert root == data_dir.parent / "sovereign-agent-backups"
    assert str(Path.home() / "AA-Erebo" / "sov-backups") not in str(root)


def test_scan_takes_and_verifies_a_snapshot_when_overdue(tmp_path):
    from sovereign_agent.stewardship.backup_sentinel import BackupSentinel

    s = BackupSentinel(data_dir=_make_data_dir(tmp_path))
    assert s.overdue() is True
    report = s.scan()
    assert report.details["took_snapshot"] is True
    assert report.details["verify_ok"] is True
    assert s.overdue() is False
    # A second scan while fresh must not take another snapshot.
    report2 = s.scan()
    assert report2.details["took_snapshot"] is False


def test_every_db_in_snapshot_is_openable_not_torn(tmp_path):
    from sovereign_agent.stewardship.backup_sentinel import BackupSentinel

    s = BackupSentinel(data_dir=_make_data_dir(tmp_path))
    report = s.scan()
    snap_dir = Path(report.details["backup_root"]) / report.details["snapshot_id"]
    dbs = sorted(p.relative_to(snap_dir / "data") for p in (snap_dir / "data").rglob("*.db"))
    assert Path("palace.db") in dbs
    assert Path("shards/emotions.db") in dbs
    for rel in dbs:
        conn = sqlite3.connect(snap_dir / "data" / rel)
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        conn.close()
    assert list((snap_dir / "data").rglob("*.db-wal")) == []
    assert list((snap_dir / "data").rglob("*.db-shm")) == []


def test_health_status_never_snapshots(tmp_path, monkeypatch):
    from sovereign_agent import backup as _bk
    from sovereign_agent.stewardship.backup_sentinel import BackupSentinel

    def _boom(**kw):
        raise AssertionError("health_status() must never call backup.snapshot()")

    monkeypatch.setattr(_bk, "snapshot", _boom)
    s = BackupSentinel(data_dir=_make_data_dir(tmp_path))
    hs = s.health_status()
    assert hs.level in ("ok", "warning", "error")


def test_health_levels(tmp_path):
    from sovereign_agent.stewardship.backup_sentinel import BackupSentinel

    s = BackupSentinel(data_dir=_make_data_dir(tmp_path))
    assert s.health_status().level == "warning"  # no snapshots yet
    s.scan()
    assert s.health_status().level == "ok"


@pytest.mark.asyncio
async def test_cockpit_auto_backup_not_triggered_on_mount():
    """Timer-only discipline: a fresh cockpit boot must NOT kick the backup
    worker (a test boot writing a real snapshot would be pollution)."""
    from sovereign_agent.cockpit import CockpitApp
    import sovereign_agent.cockpit.app as app_module

    async with CockpitApp().run_test() as pilot:
        await pilot.pause()
        assert app_module._AUTO_BACKUP_RUNNING is False
