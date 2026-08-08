"""Pre-apply structural checks for aria-wellbeing-modes's patcher (staged-only)."""
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


def test_stances_patch_adds_reflecting_and_the_side_effect():
    new, _ = ALL_PATCHES["modes_crown/stances.py"](
        (SRC / "modes_crown/stances.py").read_text(encoding="utf-8"))
    assert '"reflecting"' in new
    assert "def wellbeing_gate_clear" in new
    assert "_run_wellbeing_pass_for_stance" in new
    # every original stance still present, unchanged
    assert '"grounded"' in new and '"quality-pass"' in new and '"cool-down"' in new


def test_crown_gate_patch_anchors_after_the_grounded_block():
    new, _ = ALL_PATCHES["session_bridge.py"](
        (SRC / "session_bridge.py").read_text(encoding="utf-8"))
    gr_idx = new.index('_current_stance_g() == "grounded"')
    wb_idx = new.index('wellbeing_gate_clear')
    assert wb_idx > gr_idx


def test_observatory_patch_adds_the_wellbeing_field():
    new, _ = ALL_PATCHES["modes_crown/observatory.py"](
        (SRC / "modes_crown/observatory.py").read_text(encoding="utf-8"))
    assert 'out["wellbeing"]' in new
    assert "♡ wellbeing" in new


def test_moved_anchor_is_loud():
    import pytest

    for rel, fn in ALL_PATCHES.items():
        with pytest.raises(PatchError):
            fn("nothing anchors here\n")
