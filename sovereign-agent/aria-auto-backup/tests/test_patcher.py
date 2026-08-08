"""Patcher tests for aria-auto-backup — verify the patch functions
themselves against the CURRENT live files, before anything is applied."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

STAGING = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(STAGING))
from patcher import MARK, PatchError, patch_app, patch_backup_py, patch_stewardship_init  # noqa: E402

REPO_ROOT = STAGING.parent
BACKUP_PY = REPO_ROOT / "src" / "sovereign_agent" / "backup.py"
APP_PY = REPO_ROOT / "src" / "sovereign_agent" / "cockpit" / "app.py"
STEW_INIT = REPO_ROOT / "src" / "sovereign_agent" / "stewardship" / "__init__.py"
SENTINEL_PAYLOAD = STAGING / "payload" / "src" / "sovereign_agent" / "stewardship" / "backup_sentinel.py"


def _compiles(text: str) -> None:
    import py_compile
    import tempfile

    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(text)
        tmp = f.name
    py_compile.compile(tmp, doraise=True)


# ─── backup.py ───────────────────────────────────────────────────────────


def test_backup_py_applies_and_compiles():
    new, _ = patch_backup_py(BACKUP_PY.read_text(encoding="utf-8"))
    assert MARK in new
    _compiles(new)


def test_backup_py_idempotent():
    once, _ = patch_backup_py(BACKUP_PY.read_text(encoding="utf-8"))
    twice, changed2 = patch_backup_py(once)
    assert changed2 is False and twice == once


def test_backup_py_online_backup_covers_every_db_not_just_atoms_events():
    new, _ = patch_backup_py(BACKUP_PY.read_text(encoding="utf-8"))
    assert "for _db_path in _walk_files(data_dir):" in new
    assert 'if _db_path.suffix != ".db":' in new
    # The hardcoded events-only call is gone
    assert 'events_db, partial_dir / "data" / "events.db"' not in new


def test_backup_py_copy_tree_skips_wal_and_shm_sidecars():
    new, _ = patch_backup_py(BACKUP_PY.read_text(encoding="utf-8"))
    assert '.db-wal' in new
    assert '.db-shm' in new


def test_backup_py_missing_anchor_raises():
    with pytest.raises(PatchError):
        patch_backup_py("no anchors here")


# ─── app.py ──────────────────────────────────────────────────────────────


def test_app_applies_and_compiles():
    new, _ = patch_app(APP_PY.read_text(encoding="utf-8"))
    assert MARK in new
    _compiles(new)


def test_app_idempotent():
    once, _ = patch_app(APP_PY.read_text(encoding="utf-8"))
    twice, changed2 = patch_app(once)
    assert changed2 is False and twice == once


def test_app_backup_flags_are_module_level_not_instance():
    new, _ = patch_app(APP_PY.read_text(encoding="utf-8"))
    assert "_AUTO_BACKUP_LOCK = threading.Lock()" in new
    assert "_AUTO_BACKUP_RUNNING = False" in new
    assert "self._auto_backup_running" not in new


def test_app_timer_only_never_eager_on_mount():
    """The auto-backup check must ONLY come from the hourly timer — never
    call_after_refresh'd on mount. Doubly critical here: an eager kickoff in
    a short-lived test cockpit boot would WRITE A REAL SNAPSHOT."""
    new, _ = patch_app(APP_PY.read_text(encoding="utf-8"))
    assert "self.set_interval(3600.0, self._maybe_run_auto_backup)" in new
    assert "call_after_refresh(self._maybe_run_auto_backup)" not in new


def test_app_worker_checks_is_enabled_and_overdue():
    new, _ = patch_app(APP_PY.read_text(encoding="utf-8"))
    idx = new.index("def _run_auto_backup_worker")
    body = new[idx:idx + 1200]
    assert "sentinel.is_enabled() and sentinel.overdue()" in body


def test_app_missing_anchor_raises():
    with pytest.raises(PatchError):
        patch_app("no anchors here")


# ─── stewardship/__init__.py ─────────────────────────────────────────────


def test_stewardship_init_applies_idempotent_compiles():
    text = STEW_INIT.read_text(encoding="utf-8")
    once, changed = patch_stewardship_init(text)
    assert MARK in once
    twice, changed2 = patch_stewardship_init(once)
    assert changed2 is False and twice == once
    _compiles(once)


# ─── payload ─────────────────────────────────────────────────────────────


def test_sentinel_payload_compiles():
    _compiles(SENTINEL_PAYLOAD.read_text(encoding="utf-8"))


def test_sentinel_payload_documents_kill_switch():
    """Conformance rule kill-switch-documented: the docstring must name
    SOV_NO_BACKUP_SENTINEL (also proves this module won't ADD a violation
    to the 27 aria-bloodwork is about to clear)."""
    assert "SOV_NO_BACKUP_SENTINEL" in SENTINEL_PAYLOAD.read_text(encoding="utf-8")
