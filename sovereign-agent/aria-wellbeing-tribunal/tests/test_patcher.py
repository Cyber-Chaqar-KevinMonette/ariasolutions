"""Pre-apply structural checks for aria-wellbeing-tribunal's patcher (staged-only)."""
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


def test_angel_patch_adds_the_measured_data_branch():
    new, _ = ALL_PATCHES["spectrum/lenses.py"](
        (SRC / "spectrum/lenses.py").read_text(encoding="utf-8"))
    assert "love_grade" in new and "flourishing_verdict" in new
    # the original live-only fallback path must still be present
    assert "_a.advocate(p, devil_report=_d.scrutinize(p))" in new


def test_sentinel_patch_wires_tribunal_and_spectrum_with_well_prefix():
    new, _ = ALL_PATCHES["stewardship/wellbeing_sentinel.py"](
        (SRC / "stewardship/wellbeing_sentinel.py").read_text(encoding="utf-8"))
    assert "log_to_diagnosis" in new
    assert 'prefix="WELL"' in new
    assert "convene_spectrum" in new


def test_moved_anchor_is_loud():
    import pytest

    for rel, fn in ALL_PATCHES.items():
        with pytest.raises(PatchError):
            fn("nothing anchors here\n")
