"""Pre-apply structural checks for aria-grounding-gate's patcher (staged-only)."""
from __future__ import annotations

import py_compile
import sys
import tempfile
from pathlib import Path

MODULE_ROOT = Path(__file__).parent.parent
REPO_ROOT = MODULE_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))

from patcher import ALL_PATCHES, MARK, PatchError, SCRIPT_PATCHES  # noqa: E402

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


def test_every_py_patch_applies_compiles_and_is_idempotent():
    for rel, fn in ALL_PATCHES.items():
        text = (SRC / rel).read_text(encoding="utf-8")
        new, changed = fn(text)
        assert changed, rel
        assert MARK in new and _compiles(new), rel
        again, changed2 = fn(new)
        assert not changed2 and again == new, rel


def test_script_patch_applies_and_is_idempotent():
    rel = "pre_apply_gate.sh"
    text = (REPO_ROOT / "scripts" / rel).read_text(encoding="utf-8")
    new, changed = SCRIPT_PATCHES[rel](text)
    assert changed
    assert MARK in new
    assert "grounding_gate.py" in new
    again, changed2 = SCRIPT_PATCHES[rel](new)
    assert not changed2 and again == new


def test_curiosity_patch_preserves_the_low_confidence_branch():
    new, _ = ALL_PATCHES["curiosity.py"](
        (SRC / "curiosity.py").read_text(encoding="utf-8"))
    assert "if rec.confidence < LOW_CONFIDENCE:" in new
    assert "calibration_mismatch" in new


def test_moved_anchor_is_loud():
    import pytest

    for rel, fn in ALL_PATCHES.items():
        with pytest.raises(PatchError):
            fn("nothing anchors here\n")
    for rel, fn in SCRIPT_PATCHES.items():
        with pytest.raises(PatchError):
            fn("nothing anchors here\n")
