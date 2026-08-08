"""Pre-apply structural checks for aria-quality-modes's patcher (staged-only)."""
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


def test_stances_patch_adds_quality_pass_and_the_side_effect():
    new, _ = ALL_PATCHES["modes_crown/stances.py"](
        (SRC / "modes_crown/stances.py").read_text(encoding="utf-8"))
    assert '"quality-pass"' in new
    assert "def quality_gate_clear" in new
    assert "_run_quality_pass_for_stance" in new
    # the original SAFE_STANCES entries all still present, unchanged
    assert '"cool-down"' in new and '"planning"' in new


def test_crown_gate_patch_anchors_immediately_after_cooling_down():
    new, _ = ALL_PATCHES["session_bridge.py"](
        (SRC / "session_bridge.py").read_text(encoding="utf-8"))
    cd_idx = new.index("if cooling_down():")
    qp_idx = new.index("quality-pass")
    assert qp_idx > cd_idx


def test_observatory_patch_adds_the_quality_field_to_gather_and_render():
    new, _ = ALL_PATCHES["modes_crown/observatory.py"](
        (SRC / "modes_crown/observatory.py").read_text(encoding="utf-8"))
    assert 'out["quality"]' in new
    assert "◆ quality" in new


def test_moved_anchor_is_loud():
    import pytest

    for rel, fn in ALL_PATCHES.items():
        with pytest.raises(PatchError):
            fn("nothing anchors here\n")
