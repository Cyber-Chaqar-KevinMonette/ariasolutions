"""Pre-apply structural checks for aria-memory-proof's patcher (staged-only)."""
from __future__ import annotations

import py_compile
import sys
import tempfile
from pathlib import Path

MODULE_ROOT = Path(__file__).parent.parent
REPO_ROOT = MODULE_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))

from patcher import MARK, PatchError, patch_runner  # noqa: E402

RUNNER = REPO_ROOT / "src/sovereign_agent/proving_ground/runner.py"


def test_runner_patch_applies_and_is_idempotent():
    text = RUNNER.read_text(encoding="utf-8")
    new, changed = patch_runner(text)
    assert changed and MARK in new
    assert 'SUITE_VERSION = "v2"' in new
    assert "OFFLINE_TASKS.update(MEMORY_TASKS)" in new
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as fh:
        fh.write(new)
        tmp = fh.name
    try:
        py_compile.compile(tmp, doraise=True)
    finally:
        Path(tmp).unlink(missing_ok=True)
    again, changed2 = patch_runner(new)
    assert not changed2 and again == new


def test_moved_anchor_is_loud():
    import pytest

    with pytest.raises(PatchError):
        patch_runner("nothing anchors here\n")
