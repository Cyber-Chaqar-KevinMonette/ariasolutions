"""Text-transform tests for aria-security-strip-wire's patcher.py — proves
the app.py patch applies cleanly against the CURRENT live file, is
idempotent, and the patched result compiles."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from patcher import MARK, patch_app  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
APP_PY = REPO_ROOT / "src" / "sovereign_agent" / "cockpit" / "app.py"


def test_patch_app_applies_and_is_idempotent():
    text = APP_PY.read_text(encoding="utf-8")
    once, _ = patch_app(text)  # changed may be False if already applied
    assert MARK in once
    assert "_SECURITY_SCAN_CACHE" in once
    assert "_SECURITY_SCAN_LOCK" in once
    assert "_maybe_run_security_scan" in once
    assert "_run_security_scan_worker" in once
    assert "scan_tree" in once
    assert "\nimport threading\n" in once
    twice, changed_again = patch_app(once)
    assert not changed_again
    assert twice == once


def test_cache_and_lock_are_module_level_not_instance_attributes():
    """Regression test for a real bug found live: the cache/running-flag
    were originally per-CockpitApp-instance attributes, so every separate
    cockpit boot in the same process spawned its own competing scan thread
    (CPU-bound, GIL-contending) — confirmed via bisection to break unrelated,
    timing-sensitive tests elsewhere in the suite when many cockpit-booting
    tests ran in the same pytest process. Module-level state means every
    instance shares one scan result and, critically, only one scan thread
    ever runs process-wide, no matter how many CockpitApp() instances exist."""
    text = APP_PY.read_text(encoding="utf-8")
    patched, _ = patch_app(text)
    assert "self._security_scan_cache" not in patched
    assert "self._security_scan_running" not in patched
    assert "_SECURITY_SCAN_CACHE: dict | None = None" in patched
    assert "_SECURITY_SCAN_LOCK = threading.Lock()" in patched


def test_patched_app_compiles():
    import py_compile
    import tempfile

    text = APP_PY.read_text(encoding="utf-8")
    patched, _ = patch_app(text)
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as fh:
        fh.write(patched)
        tmp_name = fh.name
    py_compile.compile(tmp_name, doraise=True)


def test_worker_decorator_is_thread_and_exclusive():
    text = APP_PY.read_text(encoding="utf-8")
    patched, _ = patch_app(text)
    assert '@work(exclusive=True, group="security-scan", thread=True)' in patched


def test_no_eager_scan_kickoff_on_mount():
    """Regression test for the ACTUAL root cause of the live GIL-contention
    bug: an earlier version of this fix called
    `self.call_after_refresh(self._maybe_run_security_scan)` on every mount,
    which — combined with Textual's `thread=True` workers being
    uncancellable once dispatched (they run via `loop.run_in_executor`, a
    real ThreadPoolExecutor thread that completes regardless of any
    `.cancel()` call) — meant every CockpitApp booted in a test process
    spawned a real, run-to-completion background thread. A module-level
    lock alone did NOT fix this (confirmed by bisection); only removing the
    eager on-mount trigger did. The scan must be reachable ONLY via the
    300s periodic timer."""
    text = APP_PY.read_text(encoding="utf-8")
    patched, _ = patch_app(text)
    assert "self.call_after_refresh(self._maybe_run_security_scan)" not in patched
    assert "self.set_interval(300.0, self._maybe_run_security_scan)" in patched
