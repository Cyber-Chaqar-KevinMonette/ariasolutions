"""Pre-apply structural checks for aria-one-truth's patcher (staged-only)."""
from __future__ import annotations

import py_compile
import sys
import tempfile
from pathlib import Path

MODULE_ROOT = Path(__file__).parent.parent
REPO_ROOT = MODULE_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))

from patcher import (  # noqa: E402
    MARK, PatchError, patch_cli, patch_stewardship_init,
)

STEWARDSHIP_INIT = REPO_ROOT / "src/sovereign_agent/stewardship/__init__.py"
CLI = REPO_ROOT / "src/sovereign_agent/cli.py"


def _compiles(source: str) -> bool:
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as fh:
        fh.write(source)
        tmp = fh.name
    try:
        py_compile.compile(tmp, doraise=True)
        return True
    finally:
        Path(tmp).unlink(missing_ok=True)


def test_stewardship_init_patch_applies_and_is_idempotent():
    text = STEWARDSHIP_INIT.read_text(encoding="utf-8")
    new, changed = patch_stewardship_init(text)
    assert changed and MARK in new and _compiles(new)
    again, changed2 = patch_stewardship_init(new)
    assert not changed2 and again == new


def test_cli_patch_applies_and_is_idempotent():
    text = CLI.read_text(encoding="utf-8")
    new, changed = patch_cli(text)
    assert changed and MARK in new and _compiles(new)
    assert 'name="truth"' in new
    again, changed2 = patch_cli(new)
    assert not changed2 and again == new


def test_moved_anchor_is_loud_never_silent():
    import pytest

    with pytest.raises(PatchError):
        patch_stewardship_init("nothing anchors here\n")
    with pytest.raises(PatchError):
        patch_cli("nothing anchors here\n")
