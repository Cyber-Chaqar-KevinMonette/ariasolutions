"""
test_backup.py — Tests for the v0.2.14.2 backup module.

Each class covers a doctrine clause or a known failure mode that the
``cp -r`` predecessor could not handle.

  TestSnapshot          — basic capture + manifest contents
  TestIdempotency       — windowed idempotency for unlabeled snapshots
  TestExclusions        — venv/__pycache__ aren't copied
  TestVerify            — manifest hash check + per-file hash check
  TestVerifyCorruption  — corrupted file detected
  TestVerifyAudit       — staged atoms.db audit catches application corruption
  TestPrune             — retention policy keeps the right snapshots
  TestPruneInvariant    — never-zero-backups holds
  TestRestore           — happy path with auto-pre-restore
  TestRestoreRefusal    — refuses on staged-audit failure
  TestRestoreRollback   — restore preserves rollback-of-rollback
  TestStatus            — single-screen view assembled correctly
  TestCrashConsistency  — SQLite online backup is application-consistent
"""
from __future__ import annotations

import os
import shutil
import sqlite3
import threading
import time
from pathlib import Path

import pytest


# ─── Helpers ────────────────────────────────────────────────────────────────


def _make_test_data(data_dir: Path, *, with_ledger: bool = False):
    """Populate a data dir with a minimal sovereign-agent layout."""
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "blobs").mkdir(exist_ok=True)
    (data_dir / "blobs" / "sample.txt").write_text("hello world\n")
    (data_dir / "events").mkdir(exist_ok=True)
    (data_dir / "events" / "events.jsonl").write_text('{"event":"test"}\n')

    # Init atoms.db via the project's open helper so schema is real.
    from sovereign_agent.db import open_atoms_db
    conn = open_atoms_db()
    if with_ledger:
        from sovereign_agent.mem_channels.financial import FinancialChannel
        fc = FinancialChannel(conn)
        fc.record(project="bk-test", kind="invest", amount=100.0,
                  idempotency_id="bk-i1")
        fc.record(project="bk-test", kind="earn", amount=150.0,
                  idempotency_id="bk-e1")
    conn.close()


def _backup_root(tmp_path: Path) -> Path:
    return tmp_path / "backups"


# ─── TestSnapshot ───────────────────────────────────────────────────────────


class TestSnapshot:
    def test_snapshot_captures_files(self, tmp_path):
        from sovereign_agent.config import SETTINGS
        from sovereign_agent import backup as backup_mod

        _make_test_data(SETTINGS.paths.data_dir)
        m = backup_mod.snapshot(backup_root=_backup_root(tmp_path))

        assert m.snapshot_id.startswith("snap-")
        assert m.file_count > 0
        assert m.total_bytes > 0
        # Manifest and hash file exist.
        snap_dir = _backup_root(tmp_path) / m.snapshot_id
        assert (snap_dir / "MANIFEST.json").exists()
        assert (snap_dir / "MANIFEST.sha256").exists()
        # Sample blob round-tripped.
        assert (snap_dir / "data" / "blobs" / "sample.txt").read_text() == \
               "hello world\n"

    def test_snapshot_records_version_and_audit(self, tmp_path):
        from sovereign_agent.config import SETTINGS
        from sovereign_agent import backup as backup_mod
        from sovereign_agent import __version__

        _make_test_data(SETTINGS.paths.data_dir, with_ledger=True)
        m = backup_mod.snapshot(backup_root=_backup_root(tmp_path))

        assert m.source_version == __version__
        assert m.financial_ledger_count == 2
        assert m.audit_at_snapshot["ok"] is True

    def test_snapshot_with_label(self, tmp_path):
        from sovereign_agent.config import SETTINGS
        from sovereign_agent import backup as backup_mod
        _make_test_data(SETTINGS.paths.data_dir)
        m = backup_mod.snapshot(
            backup_root=_backup_root(tmp_path), label="pre-upgrade",
        )
        assert m.label == "pre-upgrade"
        # Label appears in id (sanitised).
        assert "pre-upgrade" in m.snapshot_id

    def test_snapshot_partial_dir_cleaned_on_failure(self, tmp_path,
                                                      monkeypatch):
        from sovereign_agent.config import SETTINGS
        from sovereign_agent import backup as backup_mod
        _make_test_data(SETTINGS.paths.data_dir)

        # Force a failure in the middle of the snapshot.
        original = backup_mod._sha256_file

        def boom(path, **kw):
            raise RuntimeError("simulated mid-snapshot failure")

        monkeypatch.setattr(backup_mod, "_sha256_file", boom)
        with pytest.raises(RuntimeError):
            backup_mod.snapshot(backup_root=_backup_root(tmp_path))

        # No completed snapshot, no leftover .partial dir.
        root = _backup_root(tmp_path)
        assert root.exists()
        leftovers = [p for p in root.iterdir() if p.name.endswith(".partial")]
        assert leftovers == [], f"partial dirs left behind: {leftovers}"


# ─── TestIdempotency ────────────────────────────────────────────────────────


class TestIdempotency:
    def test_unlabeled_snapshots_within_window_dedup(self, tmp_path):
        from sovereign_agent.config import SETTINGS
        from sovereign_agent import backup as backup_mod
        _make_test_data(SETTINGS.paths.data_dir)
        m1 = backup_mod.snapshot(backup_root=_backup_root(tmp_path))
        m2 = backup_mod.snapshot(backup_root=_backup_root(tmp_path))
        assert m1.snapshot_id == m2.snapshot_id, (
            "second unlabeled snapshot inside the idempotency window "
            "should return the first"
        )

    def test_labeled_snapshots_always_distinct(self, tmp_path):
        from sovereign_agent.config import SETTINGS
        from sovereign_agent import backup as backup_mod
        _make_test_data(SETTINGS.paths.data_dir)
        m1 = backup_mod.snapshot(backup_root=_backup_root(tmp_path),
                                 label="a")
        m2 = backup_mod.snapshot(backup_root=_backup_root(tmp_path),
                                 label="b")
        assert m1.snapshot_id != m2.snapshot_id


# ─── TestExclusions ─────────────────────────────────────────────────────────


class TestExclusions:
    def test_venv_excluded(self, tmp_path):
        from sovereign_agent.config import SETTINGS
        from sovereign_agent import backup as backup_mod

        _make_test_data(SETTINGS.paths.data_dir)
        # Plant a fake venv inside the data dir.
        venv_dir = SETTINGS.paths.data_dir / "venv" / "lib"
        venv_dir.mkdir(parents=True)
        (venv_dir / "huge_file.bin").write_bytes(b"x" * 10000)

        m = backup_mod.snapshot(backup_root=_backup_root(tmp_path))
        snap_dir = _backup_root(tmp_path) / m.snapshot_id
        # The venv file should not be present in the snapshot.
        venv_in_snap = snap_dir / "data" / "venv"
        assert not venv_in_snap.exists()
        # Manifest should not list it.
        for f in m.files:
            assert "venv" not in f.path.split("/"), \
                f"venv leaked into manifest: {f.path}"

    def test_pycache_excluded(self, tmp_path):
        from sovereign_agent.config import SETTINGS
        from sovereign_agent import backup as backup_mod
        _make_test_data(SETTINGS.paths.data_dir)
        pyc = SETTINGS.paths.data_dir / "__pycache__"
        pyc.mkdir()
        (pyc / "x.cpython-312.pyc").write_bytes(b"compiled\n")
        m = backup_mod.snapshot(backup_root=_backup_root(tmp_path))
        for f in m.files:
            assert "__pycache__" not in f.path


# ─── TestVerify ─────────────────────────────────────────────────────────────


class TestVerify:
    def test_clean_snapshot_verifies_clean(self, tmp_path):
        from sovereign_agent.config import SETTINGS
        from sovereign_agent import backup as backup_mod
        _make_test_data(SETTINGS.paths.data_dir, with_ledger=True)
        m = backup_mod.snapshot(backup_root=_backup_root(tmp_path))
        v = backup_mod.verify(m.snapshot_id, backup_root=_backup_root(tmp_path))
        assert v.ok
        assert v.manifest_hash_ok
        assert not v.mismatched_files
        assert not v.missing_files
        assert v.audit_clean

    def test_prefix_match_works(self, tmp_path):
        from sovereign_agent.config import SETTINGS
        from sovereign_agent import backup as backup_mod
        _make_test_data(SETTINGS.paths.data_dir)
        m = backup_mod.snapshot(backup_root=_backup_root(tmp_path))
        # Use just the prefix.
        prefix = m.snapshot_id[:20]
        v = backup_mod.verify(prefix, backup_root=_backup_root(tmp_path))
        assert v.ok

    def test_label_resolution(self, tmp_path):
        """Operators expect 'sov backup restore my-label' to work."""
        from sovereign_agent.config import SETTINGS
        from sovereign_agent import backup as backup_mod
        _make_test_data(SETTINGS.paths.data_dir)
        backup_mod.snapshot(backup_root=_backup_root(tmp_path),
                             label="ergonomic-test")
        v = backup_mod.verify("ergonomic-test",
                               backup_root=_backup_root(tmp_path))
        assert v.ok


# ─── TestVerifyCorruption ──────────────────────────────────────────────────


class TestVerifyCorruption:
    def test_modified_file_detected(self, tmp_path):
        from sovereign_agent.config import SETTINGS
        from sovereign_agent import backup as backup_mod
        _make_test_data(SETTINGS.paths.data_dir)
        m = backup_mod.snapshot(backup_root=_backup_root(tmp_path))

        # Corrupt a file inside the snapshot.
        target = (_backup_root(tmp_path) / m.snapshot_id /
                  "data" / "blobs" / "sample.txt")
        target.write_text("CORRUPTED\n")

        v = backup_mod.verify(m.snapshot_id, backup_root=_backup_root(tmp_path))
        assert not v.ok
        assert any("sample.txt" in f for f in v.mismatched_files)

    def test_tampered_manifest_detected(self, tmp_path):
        from sovereign_agent.config import SETTINGS
        from sovereign_agent import backup as backup_mod
        _make_test_data(SETTINGS.paths.data_dir)
        m = backup_mod.snapshot(backup_root=_backup_root(tmp_path))

        # Tamper with the manifest itself.
        manifest = (_backup_root(tmp_path) / m.snapshot_id / "MANIFEST.json")
        contents = manifest.read_text()
        manifest.write_text(contents + "  ")  # extra whitespace = different hash

        v = backup_mod.verify(m.snapshot_id, backup_root=_backup_root(tmp_path))
        assert not v.manifest_hash_ok
        assert not v.ok


# ─── TestPrune ──────────────────────────────────────────────────────────────


class TestPrune:
    def test_dry_run_does_not_delete(self, tmp_path):
        from sovereign_agent.config import SETTINGS
        from sovereign_agent import backup as backup_mod
        _make_test_data(SETTINGS.paths.data_dir)
        # Make several snapshots with backdated created_at so prune has
        # something to do.
        snaps = []
        for i in range(3):
            m = backup_mod.snapshot(
                backup_root=_backup_root(tmp_path), label=f"l{i}",
            )
            snaps.append(m)
        before = list(_backup_root(tmp_path).iterdir())
        backup_mod.prune(backup_root=_backup_root(tmp_path), dry_run=True)
        after = list(_backup_root(tmp_path).iterdir())
        assert len(before) == len(after)


class TestPruneInvariant:
    def test_never_zero_backups(self, tmp_path):
        """Even an empty retention policy must keep the most recent."""
        from sovereign_agent.config import SETTINGS
        from sovereign_agent import backup as backup_mod
        _make_test_data(SETTINGS.paths.data_dir)
        m = backup_mod.snapshot(backup_root=_backup_root(tmp_path))
        # Aggressive policy: zero anywhere, but the newest must survive.
        result = backup_mod.prune(
            backup_root=_backup_root(tmp_path),
            policy=backup_mod.RetentionPolicy(
                keep_all_within_hours=0,
                keep_daily_within_days=0,
                keep_weekly_within_days=0,
                keep_monthly_within_days=0,
                keep_labeled_forever=False,
                minimum_to_keep=1,
            ),
            dry_run=False,
        )
        # The minimum_to_keep=1 + "always keep newest" invariants combine.
        snaps = backup_mod.list_snapshots(backup_root=_backup_root(tmp_path))
        assert len(snaps) >= 1


# ─── TestRestore ────────────────────────────────────────────────────────────


class TestRestore:
    def test_restore_swaps_data_and_creates_pre_snapshot(self, tmp_path):
        from sovereign_agent.config import SETTINGS
        from sovereign_agent import backup as backup_mod

        _make_test_data(SETTINGS.paths.data_dir, with_ledger=True)
        m = backup_mod.snapshot(backup_root=_backup_root(tmp_path),
                                 label="t1")

        # Mutate live state — write something the snapshot DOESN'T have.
        (SETTINGS.paths.data_dir / "blobs" / "after_snapshot.txt").write_text(
            "this is post-snapshot live state\n"
        )

        result = backup_mod.restore(
            m.snapshot_id, backup_root=_backup_root(tmp_path),
            confirmed=True,
        )
        assert result.snapshot_id == m.snapshot_id
        assert result.pre_restore_snapshot_id.startswith("snap-")
        assert result.pre_restore_snapshot_id != m.snapshot_id

        # Live data now matches the snapshot — the post-snapshot file is gone.
        assert not (SETTINGS.paths.data_dir / "blobs" /
                    "after_snapshot.txt").exists()

        # Pre-restore snapshot exists and has the post-snapshot file.
        pre_snap_dir = (_backup_root(tmp_path) /
                        result.pre_restore_snapshot_id)
        assert (pre_snap_dir / "data" / "blobs" /
                "after_snapshot.txt").exists()

    def test_restore_requires_confirmed(self, tmp_path):
        from sovereign_agent.config import SETTINGS
        from sovereign_agent import backup as backup_mod
        _make_test_data(SETTINGS.paths.data_dir)
        m = backup_mod.snapshot(backup_root=_backup_root(tmp_path),
                                 label="t1")
        with pytest.raises(ValueError):
            backup_mod.restore(m.snapshot_id,
                                backup_root=_backup_root(tmp_path))


class TestRestoreRefusal:
    def test_refuses_on_corrupted_target(self, tmp_path):
        """If the target snapshot's hashes don't match, restore must abort
        before touching live data."""
        from sovereign_agent.config import SETTINGS
        from sovereign_agent import backup as backup_mod
        _make_test_data(SETTINGS.paths.data_dir)
        m = backup_mod.snapshot(backup_root=_backup_root(tmp_path),
                                 label="t1")

        # Corrupt a file in the target snapshot.
        target = (_backup_root(tmp_path) / m.snapshot_id /
                  "data" / "blobs" / "sample.txt")
        target.write_text("CORRUPTED\n")

        # Add live state — must remain after the failed restore.
        (SETTINGS.paths.data_dir / "blobs" / "live.txt").write_text("live\n")

        with pytest.raises(backup_mod.SnapshotCorruptError):
            backup_mod.restore(m.snapshot_id,
                                backup_root=_backup_root(tmp_path),
                                confirmed=True)

        # Live state untouched.
        assert (SETTINGS.paths.data_dir / "blobs" / "live.txt").exists()


class TestCircularDependency:
    """A backup_root inside data_dir is a landmine: snapshot recurses
    into its own partial; restore destroys all snapshots when it
    replaces the data dir. The system refuses the configuration."""

    def test_nested_backup_root_refused(self, tmp_path):
        from sovereign_agent.config import SETTINGS
        from sovereign_agent import backup as backup_mod
        _make_test_data(SETTINGS.paths.data_dir)
        nested_root = SETTINGS.paths.data_dir / "backups"
        with pytest.raises(backup_mod.BackupError) as info:
            backup_mod.snapshot(backup_root=nested_root)
        assert "inside" in str(info.value)

    def test_default_root_is_outside_data_dir(self, tmp_path):
        from sovereign_agent.config import SETTINGS
        from sovereign_agent import backup as backup_mod
        # When AA-Erebo doesn't exist (it doesn't in tests), default falls
        # back to data_dir.parent / sovereign-agent-backups — outside the
        # data tree.
        root = backup_mod.default_backup_root()
        try:
            root.resolve().relative_to(SETTINGS.paths.data_dir.resolve())
        except ValueError:
            return  # good — not inside
        pytest.fail(f"default backup root {root} is INSIDE data_dir")


class TestSandboxArtifacts:
    """v0.2.14.3 regression: the agent's sandbox dir can contain broken
    symlinks (sandbox-escape test artifacts), and os.walk yields those
    even though they can't be stat()'d. The walker must tolerate them,
    and generic sandbox scratch belongs in EXCLUDED_PATTERNS because
    restoring it would re-introduce stale test state.

    Carve-out added live 2026-08-03 (Kevin, "make sure her key files and
    systems have recovery methods"): sandbox/games/<slug> is NOT
    ephemeral scratch — game_workspace_dir() puts every real game
    project there, so a blanket sandbox exclusion silently meant zero
    backup coverage for Aria's actual creative work. The crash-safety
    concern (broken symlinks) is independently handled by _walk_files'
    defensive is_file()/OSError guard, so narrowing the exclusion is
    safe."""

    def test_broken_symlink_in_sandbox_does_not_crash_snapshot(self, tmp_path):
        from sovereign_agent.config import SETTINGS
        from sovereign_agent import backup as backup_mod
        _make_test_data(SETTINGS.paths.data_dir)

        # Plant exactly the artifact the operator hit:
        # ~/.local/share/sovereign-agent/sandbox/escape (broken symlink).
        sandbox = SETTINGS.paths.data_dir / "sandbox"
        sandbox.mkdir(exist_ok=True)
        (sandbox / "escape").symlink_to("/nonexistent/target")

        # Snapshot must succeed.
        m = backup_mod.snapshot(backup_root=_backup_root(tmp_path))
        assert m.file_count > 0

        # Generic sandbox scratch is still excluded — no non-games sandbox
        # entries in the manifest.
        for f in m.files:
            parts = f.path.split("/")
            if "sandbox" not in parts:
                continue
            idx = parts.index("sandbox")
            assert parts[idx + 1 : idx + 2] == ["games"], (
                f"non-games sandbox scratch leaked into manifest: {f.path} "
                f"(sandbox is ephemeral scratch and must stay excluded, "
                f"except sandbox/games/ — real game-project work)"
            )

    def test_game_project_under_sandbox_is_backed_up(self, tmp_path):
        """The actual gap: sandbox/games/<slug>/*.gd must survive a
        snapshot — it's real creative work, not test scratch."""
        from sovereign_agent.config import SETTINGS
        from sovereign_agent import backup as backup_mod
        _make_test_data(SETTINGS.paths.data_dir)

        game_dir = SETTINGS.paths.data_dir / "sandbox" / "games" / "ember-keep"
        game_dir.mkdir(parents=True, exist_ok=True)
        (game_dir / "fire.gd").write_text("extends Node2D\n", encoding="utf-8")

        m = backup_mod.snapshot(backup_root=_backup_root(tmp_path))

        assert any(f.path.endswith("sandbox/games/ember-keep/fire.gd") for f in m.files), (
            "game project file did not survive the sandbox exclusion — "
            f"manifest paths: {[f.path for f in m.files]}"
        )

    def test_generic_sandbox_scratch_still_excluded(self, tmp_path):
        """Non-games sandbox content (the original ephemeral-scratch
        case) must remain excluded — only games/ is carved out."""
        from sovereign_agent.config import SETTINGS
        from sovereign_agent import backup as backup_mod
        _make_test_data(SETTINGS.paths.data_dir)

        scratch = SETTINGS.paths.data_dir / "sandbox" / "some_tool_scratch"
        scratch.mkdir(parents=True, exist_ok=True)
        (scratch / "temp.txt").write_text("ephemeral", encoding="utf-8")

        m = backup_mod.snapshot(backup_root=_backup_root(tmp_path))

        assert not any("some_tool_scratch" in f.path for f in m.files), (
            "generic sandbox scratch leaked into manifest — only "
            "sandbox/games/ should be carved out of the exclusion"
        )

    def test_broken_symlink_outside_excluded_dirs_also_tolerated(self,
                                                                  tmp_path):
        """Defence-in-depth: even if a future scratch dir misses the
        EXCLUDED_PATTERNS list, a broken symlink anywhere in the data
        dir must not crash the snapshot."""
        from sovereign_agent.config import SETTINGS
        from sovereign_agent import backup as backup_mod
        _make_test_data(SETTINGS.paths.data_dir)

        # Plant a broken symlink in a non-excluded subdirectory.
        weird = SETTINGS.paths.data_dir / "blobs" / "dangling"
        weird.symlink_to("/this/does/not/exist")

        # Must not raise.
        m = backup_mod.snapshot(backup_root=_backup_root(tmp_path))
        assert m.file_count > 0
        # The broken symlink itself is correctly omitted (it's not a file).
        for f in m.files:
            assert not f.path.endswith("dangling"), (
                "broken symlink leaked into manifest"
            )


# ─── TestStatus ─────────────────────────────────────────────────────────────


class TestStatus:
    def test_empty_status(self, tmp_path):
        from sovereign_agent import backup as backup_mod
        s = backup_mod.status(backup_root=_backup_root(tmp_path))
        assert s.snapshot_count == 0
        assert s.most_recent_snapshot_id is None
        assert s.last_verify_ok is None

    def test_populated_status(self, tmp_path):
        from sovereign_agent.config import SETTINGS
        from sovereign_agent import backup as backup_mod
        _make_test_data(SETTINGS.paths.data_dir)
        backup_mod.snapshot(backup_root=_backup_root(tmp_path),
                             label="status-test")
        s = backup_mod.status(backup_root=_backup_root(tmp_path))
        assert s.snapshot_count == 1
        assert s.most_recent_snapshot_id is not None
        assert s.last_verify_ok is True
        assert s.most_recent_age_seconds is not None
        assert s.most_recent_age_seconds < 60


# ─── TestCrashConsistency ──────────────────────────────────────────────────


class TestCrashConsistency:
    """The whole point of using SQLite online backup vs cp -r: the
    snapshot must capture a coherent atoms.db even if writes are
    happening concurrently. cp -r could not promise this."""

    def test_concurrent_writes_during_snapshot(self, tmp_path):
        from sovereign_agent.config import SETTINGS
        from sovereign_agent import backup as backup_mod
        from sovereign_agent.db import open_atoms_db
        from sovereign_agent.mem_channels.lessons import LessonsChannel

        # Initialize atoms.db with a baseline of rows.
        conn = open_atoms_db()
        ch = LessonsChannel(conn)
        for i in range(50):
            ch.write_atom(summary=f"baseline-{i}",
                          idempotency_id=f"baseline-{i}")
        conn.close()

        # Background writer that hammers the DB during the snapshot.
        stop = threading.Event()

        def writer():
            w_conn = open_atoms_db()
            w_ch = LessonsChannel(w_conn)
            i = 0
            while not stop.is_set():
                try:
                    w_ch.write_atom(summary=f"concurrent-{i}",
                                    idempotency_id=f"concurrent-{i}")
                except sqlite3.OperationalError:
                    # Concurrent writers may transiently fail; that's fine.
                    pass
                i += 1
                time.sleep(0.001)
            w_conn.close()

        t = threading.Thread(target=writer)
        t.start()
        try:
            time.sleep(0.05)  # let some writes accumulate
            m = backup_mod.snapshot(backup_root=_backup_root(tmp_path))
        finally:
            stop.set()
            t.join(timeout=2)

        # The snapshot's atoms.db must open cleanly.
        snap_atoms = (_backup_root(tmp_path) / m.snapshot_id /
                      "data" / "atoms.db")
        assert snap_atoms.exists()
        snap_conn = sqlite3.connect(f"file:{snap_atoms}?mode=ro", uri=True)
        try:
            n = snap_conn.execute(
                "SELECT COUNT(*) FROM atoms WHERE type='lessons'"
            ).fetchone()[0]
            # At least the baseline rows must be present.
            assert n >= 50, f"snapshot has only {n} rows; baseline was 50"
            # No PRAGMA integrity_check failures.
            ic = snap_conn.execute("PRAGMA integrity_check").fetchall()
            assert ic == [("ok",)], f"snapshot integrity check failed: {ic}"
        finally:
            snap_conn.close()
