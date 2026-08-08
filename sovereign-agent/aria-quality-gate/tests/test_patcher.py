"""Pre-apply structural checks for aria-quality-gate's patcher (staged-only)."""
from __future__ import annotations

import py_compile
import subprocess
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


def _bash_syntax_ok(source: str) -> bool:
    with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False) as fh:
        fh.write(source)
        tmp = fh.name
    try:
        r = subprocess.run(["bash", "-n", tmp], capture_output=True, text=True)
        return r.returncode == 0
    finally:
        Path(tmp).unlink(missing_ok=True)


def test_python_patch_applies_compiles_and_is_idempotent():
    for rel, fn in ALL_PATCHES.items():
        text = (SRC / rel).read_text(encoding="utf-8")
        new, changed = fn(text)
        assert changed, rel
        assert MARK in new and _compiles(new), rel
        again, changed2 = fn(new)
        assert not changed2 and again == new, rel


def test_script_patches_apply_and_are_idempotent_and_valid_bash():
    files = {"pre_apply_gate.sh": REPO_ROOT / "scripts/pre_apply_gate.sh",
             "safe_apply.sh": REPO_ROOT / "scripts/safe_apply.sh"}
    for rel, fn in SCRIPT_PATCHES.items():
        text = files[rel].read_text(encoding="utf-8")
        new, changed = fn(text)
        assert changed, rel
        assert MARK in new, rel
        assert _bash_syntax_ok(new), rel
        again, changed2 = fn(new)
        assert not changed2 and again == new, rel


def test_pre_apply_gate_worst_wins():
    new, _ = SCRIPT_PATCHES["pre_apply_gate.sh"](
        (REPO_ROOT / "scripts/pre_apply_gate.sh").read_text(encoding="utf-8"))
    assert "qrc" in new and 'qrc -ne 0' in new


def test_safe_apply_rides_the_existing_ok_variable():
    new, _ = SCRIPT_PATCHES["safe_apply.sh"](
        (REPO_ROOT / "scripts/safe_apply.sh").read_text(encoding="utf-8"))
    # the new block must set ok=0 on BLOCK, feeding the PRE-EXISTING
    # rollback check ("if [[ $ok -eq 0 ]]") rather than inventing a new one
    quality_block_idx = new.index(MARK)
    rollback_check_idx = new.index('if [[ $ok -eq 0 ]]')
    assert quality_block_idx < rollback_check_idx
    assert "ok=0" in new[quality_block_idx:rollback_check_idx]


def test_moved_anchor_is_loud():
    import pytest

    for rel, fn in ALL_PATCHES.items():
        with pytest.raises(PatchError):
            fn("nothing anchors here\n")
    for rel, fn in SCRIPT_PATCHES.items():
        with pytest.raises(PatchError):
            fn("nothing anchors here\n")
