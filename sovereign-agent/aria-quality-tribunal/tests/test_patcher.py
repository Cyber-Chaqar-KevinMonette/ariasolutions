"""Pre-apply structural checks for aria-quality-tribunal's patcher (staged-only)."""
from __future__ import annotations

import py_compile
import sys
import tempfile
from pathlib import Path

MODULE_ROOT = Path(__file__).parent.parent
REPO_ROOT = MODULE_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))

from patcher import ALL_PATCHES, MARK, PatchError  # noqa: E402

SRC = REPO_ROOT / "src/sovereign_agent"


def _compiles(source: str) -> bool:
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as fh:
        fh.write(source)
        tmp = fh.name
    try:
        py_compile.compile(tmp, doraise=True)
        return True
    finally:
        Path(tmp).unlink(missing_ok=True)


def test_every_patch_applies_compiles_and_is_idempotent():
    for rel, fn in ALL_PATCHES.items():
        text = (SRC / rel).read_text(encoding="utf-8")
        new, changed = fn(text)
        assert changed, rel
        assert MARK in new and _compiles(new), rel
        again, changed2 = fn(new)
        assert not changed2 and again == new, rel


def test_tribunal_patch_uses_a_valid_conflict_type_and_the_prefix_param():
    new, _ = ALL_PATCHES["tribunal/tribunal.py"](
        (SRC / "tribunal/tribunal.py").read_text(encoding="utf-8"))
    assert 'type="ambiguity"' in new
    assert 'prefix="TRIB"' in new
    assert 'type="tribunal-review"' not in new


def test_artisan_patch_adds_the_measured_data_branch():
    new, _ = ALL_PATCHES["spectrum/lenses.py"](
        (SRC / "spectrum/lenses.py").read_text(encoding="utf-8"))
    assert "quality_score" in new and "hardening_critical_ok" in new
    # the original prose heuristic must still be present (fallback path)
    assert 'r"\\b(test|tests|doc|readme|clean|polish|verified|honest)\\w*"' in new


def test_sentinel_patch_wires_tribunal_and_spectrum():
    new, _ = ALL_PATCHES["stewardship/quality_sentinel.py"](
        (SRC / "stewardship/quality_sentinel.py").read_text(encoding="utf-8"))
    assert "build_review_proposal" in new
    assert "log_to_diagnosis" in new
    assert "convene_spectrum" in new


def test_moved_anchor_is_loud():
    import pytest

    for rel, fn in ALL_PATCHES.items():
        with pytest.raises(PatchError):
            fn("nothing anchors here\n")
