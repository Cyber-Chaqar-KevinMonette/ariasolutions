"""Patcher tests for aria-vessel-health — verify the patch function itself
against the CURRENT live app.py, before anything is applied."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

STAGING = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(STAGING))
from patcher import MARK, PatchError, patch_app  # noqa: E402

REPO_ROOT = STAGING.parent
APP_PATH = REPO_ROOT / "src" / "sovereign_agent" / "cockpit" / "app.py"
VESSEL_HEALTH_PAYLOAD = STAGING / "payload" / "src" / "sovereign_agent" / "vessel_health.py"


def _live_text() -> str:
    return APP_PATH.read_text(encoding="utf-8")


def test_patch_applies_cleanly_against_live_app_py():
    new_text, _ = patch_app(_live_text())  # changed may be False if already applied
    assert MARK in new_text


def test_patch_is_idempotent():
    once, _ = patch_app(_live_text())
    twice, changed2 = patch_app(once)
    assert changed2 is False
    assert once == twice


def test_patched_app_py_compiles():
    import py_compile
    import tempfile

    new_text, _ = patch_app(_live_text())
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(new_text)
        tmp_path = f.name
    py_compile.compile(tmp_path, doraise=True)


def test_vessel_health_payload_compiles():
    import py_compile

    py_compile.compile(str(VESSEL_HEALTH_PAYLOAD), doraise=True)


def test_vessel_strip_added_to_compose():
    new_text, _ = patch_app(_live_text())
    assert '#vessel-strip' in new_text
    assert 'classes="cockpit-strip"' in new_text


def test_kernel_cache_and_lock_are_module_level_not_instance_attributes():
    """Same regression class this session already hit once with
    _SECURITY_SCAN_CACHE — the vessel-health cache must be a module-level
    global, not `self.something`, so it's shared process-wide."""
    new_text, _ = patch_app(_live_text())
    assert "_VESSEL_KERNEL_CACHE: dict | None = None" in new_text
    assert "_VESSEL_KERNEL_LOCK = threading.Lock()" in new_text
    assert "self._vessel_kernel_cache" not in new_text


def test_no_eager_kernel_scan_kickoff_on_mount():
    """The kernel-coherence scan must ONLY be triggered by the 300s
    periodic timer — never call_after_refresh'd eagerly on mount (the
    exact GIL-contention regression already found and fixed once this
    session in aria-security-strip-wire)."""
    new_text, _ = patch_app(_live_text())
    mount_start = new_text.index("def on_mount(self) -> None:")
    mount_slice = new_text[mount_start : mount_start + 6000]
    assert "self.set_interval(300.0, self._maybe_run_vessel_kernel_scan)" in mount_slice
    assert "call_after_refresh(self._maybe_run_vessel_kernel_scan)" not in mount_slice


def test_refresh_cockpit_strips_calls_all_four_strips():
    new_text, _ = patch_app(_live_text())
    method_start = new_text.index("def _refresh_cockpit_strips(self) -> None:")
    method_slice = new_text[method_start : method_start + 700]
    assert "self._refresh_observability_strip()" in method_slice
    assert "self._refresh_security_strip()" in method_slice
    assert "self._refresh_emotions_strip()" in method_slice
    assert "self._refresh_vessel_strip()" in method_slice


def test_refresh_vessel_strip_calls_gather_vessel_health_with_kernel_coherence_disabled():
    """The fast 8s-cadence refresh must NOT trigger the expensive
    kernel-coherence scan inline — it reads the cache instead."""
    new_text, _ = patch_app(_live_text())
    method_start = new_text.index("def _refresh_vessel_strip(self) -> None:")
    method_slice = new_text[method_start : method_start + 1500]
    assert "include_kernel_coherence=False" in method_slice


def test_missing_anchor_raises_patch_error_not_silent_noop():
    with pytest.raises(PatchError):
        patch_app("this text has none of the expected anchors")


def test_already_patched_text_is_a_noop():
    once, _ = patch_app(_live_text())
    twice, changed = patch_app(once)
    assert changed is False
    assert twice == once
