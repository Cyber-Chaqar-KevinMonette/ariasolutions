"""Patcher tests for aria-glyph-sentinel-migration — verify the patch
functions themselves against the CURRENT live files, before anything is
applied."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

STAGING = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(STAGING))
from patcher import MARK, PatchError, patch_glyph_sentinel, patch_stewardship_init  # noqa: E402

REPO_ROOT = STAGING.parent
GLYPH_SENTINEL_PATH = REPO_ROOT / "src" / "sovereign_agent" / "stewardship" / "glyph_sentinel.py"
STEWARDSHIP_INIT_PATH = REPO_ROOT / "src" / "sovereign_agent" / "stewardship" / "__init__.py"


def _glyph_text() -> str:
    return GLYPH_SENTINEL_PATH.read_text(encoding="utf-8")


def _init_text() -> str:
    return STEWARDSHIP_INIT_PATH.read_text(encoding="utf-8")


# ─── patch_glyph_sentinel ────────────────────────────────────────────────


def test_patch_glyph_sentinel_applies_cleanly_against_live_file():
    new_text, _ = patch_glyph_sentinel(_glyph_text())  # changed may be False if already applied
    assert MARK in new_text


def test_patch_glyph_sentinel_is_idempotent():
    once, _ = patch_glyph_sentinel(_glyph_text())
    twice, changed2 = patch_glyph_sentinel(once)
    assert changed2 is False
    assert once == twice


def test_patched_glyph_sentinel_compiles():
    import py_compile
    import tempfile

    new_text, _ = patch_glyph_sentinel(_glyph_text())
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(new_text)
        tmp_path = f.name
    py_compile.compile(tmp_path, doraise=True)


def test_glyph_sentinel_class_and_registration_added():
    new_text, _ = patch_glyph_sentinel(_glyph_text())
    assert "class GlyphSentinel(Sentinel):" in new_text
    assert "@register_sentinel" in new_text
    assert "from .base import HealthStatus, Sentinel, SentinelReport" in new_text
    assert "from .registry import register_sentinel" in new_text


def test_glyph_sentinel_health_status_does_not_call_scan_source_tree():
    """The critical GIL-contention-avoidance design constraint: health_status()
    must read the cache, never re-run the expensive scan_source_tree()."""
    new_text, _ = patch_glyph_sentinel(_glyph_text())
    method_start = new_text.index("def health_status(self) -> HealthStatus:")
    next_def = new_text.index("\n    def ", method_start + 1)
    method_slice = new_text[method_start:next_def]
    assert "scan_source_tree()" not in method_slice
    assert "self.load_catalog(name=" in method_slice


def test_glyph_sentinel_scan_calls_the_real_free_functions():
    new_text, _ = patch_glyph_sentinel(_glyph_text())
    method_start = new_text.index("def scan(self) -> SentinelReport:")
    next_def = new_text.index("\n    def ", method_start + 1)
    method_slice = new_text[method_start:next_def]
    assert "scan_source_tree()" in method_slice
    assert "generate_proposals(catalog)" in method_slice
    assert "detect_coverage_gaps(catalog)" in method_slice
    assert "self.save_catalog(" in method_slice


def test_missing_anchor_raises_patch_error_not_silent_noop():
    with pytest.raises(PatchError):
        patch_glyph_sentinel("this text has none of the expected anchors")


def test_dunder_all_untouched_names_still_present():
    """Purely additive — none of the existing free-function exports are
    removed or renamed."""
    new_text, _ = patch_glyph_sentinel(_glyph_text())
    for name in (
        "scan_source_tree", "find_source_root", "load_catalog", "save_catalog",
        "catalog_path", "generate_proposals", "detect_coverage_gaps",
    ):
        assert f'"{name}"' in new_text


# ─── patch_stewardship_init ──────────────────────────────────────────────


def test_patch_stewardship_init_applies_cleanly():
    new_text, _ = patch_stewardship_init(_init_text())
    assert MARK in new_text
    assert "from . import glyph_sentinel as _glyph_sentinel" in new_text


def test_patch_stewardship_init_is_idempotent():
    once, _ = patch_stewardship_init(_init_text())
    twice, changed2 = patch_stewardship_init(once)
    assert changed2 is False
    assert once == twice


def test_patched_stewardship_init_compiles():
    import py_compile
    import tempfile

    new_text, _ = patch_stewardship_init(_init_text())
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(new_text)
        tmp_path = f.name
    py_compile.compile(tmp_path, doraise=True)


def test_stewardship_init_missing_anchor_raises():
    with pytest.raises(PatchError):
        patch_stewardship_init("this text has none of the expected anchors")
