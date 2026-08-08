"""Pre-apply structural checks for aria-git-flow's patcher (staged-only)."""
from __future__ import annotations

import py_compile
import sys
import tempfile
from pathlib import Path

MODULE_ROOT = Path(__file__).parent.parent
REPO_ROOT = MODULE_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))

from patcher import ALL_PATCHES, MARK, PatchError, TOOLS_IMPORT_MARK  # noqa: E402

SRC = REPO_ROOT / "src/sovereign_agent"

# tools/__init__.py follows the repo's own "<name>-import-d"/"-all-d"
# anchor-chain convention instead of the shared module MARK (so path_scan's
# ships-tools/no-registration check recognizes it, like every other module).
_MARKS_BY_FILE = {"tools/__init__.py": TOOLS_IMPORT_MARK}


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
        expect = _MARKS_BY_FILE.get(rel, MARK)
        assert expect in new and _compiles(new), rel
        again, changed2 = fn(new)
        assert not changed2 and again == new, rel


def test_tools_init_registers_git_checkpoint():
    new, _ = ALL_PATCHES["tools/__init__.py"](
        (SRC / "tools/__init__.py").read_text(encoding="utf-8"))
    assert "GitCheckpointTool" in new


def test_git_tools_patch_adds_the_backstop():
    new, _ = ALL_PATCHES["tools/git_tools.py"](
        (SRC / "tools/git_tools.py").read_text(encoding="utf-8"))
    assert "not a permitted git verb" in new
    assert "force flags are not permitted" in new


def test_new_git_write_payload_compiles_and_carries_the_mark():
    payload = MODULE_ROOT / "payload/src/sovereign_agent/tools/git_write.py"
    text = payload.read_text(encoding="utf-8")
    assert 'MARK = "git-flow-d"' in text
    assert _compiles(text)
    for name in ("GitAddTool", "GitCommitTool", "GitCreateBranchTool",
                 "GitCheckpointTool", "_ensure_not_default_branch",
                 "_garden_check", "_FORBIDDEN_VERBS"):
        assert name in text, name


def test_moved_anchor_is_loud():
    import pytest

    for rel, fn in ALL_PATCHES.items():
        with pytest.raises(PatchError):
            fn("nothing anchors here\n")
