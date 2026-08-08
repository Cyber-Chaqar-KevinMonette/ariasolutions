"""Pre-apply structural checks for aria-wellbeing-gate's patcher (staged-only)."""
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


def test_wellbeing_init_patch_exports_gate():
    new, _ = ALL_PATCHES["wellbeing/__init__.py"](
        (SRC / "wellbeing/__init__.py").read_text(encoding="utf-8"))
    assert "from .gate import WellbeingGateVerdict, gate" in new


def test_value_report_patch_persists_and_still_returns_the_report():
    new, _ = ALL_PATCHES["tools/companion_tools.py"](
        (SRC / "tools/companion_tools.py").read_text(encoding="utf-8"))
    assert "record_wellbeing_pass" in new
    # the original return path must still be present, unchanged
    assert "return ToolResult(ok=True, output=report)" in new


def test_moved_anchor_is_loud():
    import pytest

    for rel, fn in ALL_PATCHES.items():
        with pytest.raises(PatchError):
            fn("nothing anchors here\n")
