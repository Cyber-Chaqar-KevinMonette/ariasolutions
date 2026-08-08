"""Pre-apply structural checks for aria-memory-compact's patcher (staged-only)."""
from __future__ import annotations

import py_compile
import sys
import tempfile
from pathlib import Path

MODULE_ROOT = Path(__file__).parent.parent
REPO_ROOT = MODULE_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))

from patcher import (  # noqa: E402
    MARK, PatchError, patch_chunk_store, patch_cli, patch_stewardship_init,
)

STEWARDSHIP_INIT = REPO_ROOT / "src/sovereign_agent/stewardship/__init__.py"
CLI = REPO_ROOT / "src/sovereign_agent/cli.py"
CHUNK_STORE = REPO_ROOT / "src/sovereign_agent/checkpoint_chunks/store.py"


def _compiles(source: str) -> bool:
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as fh:
        fh.write(source)
        tmp = fh.name
    try:
        py_compile.compile(tmp, doraise=True)
        return True
    finally:
        Path(tmp).unlink(missing_ok=True)


def test_all_three_patches_apply_and_are_idempotent():
    for path, fn in ((STEWARDSHIP_INIT, patch_stewardship_init),
                     (CLI, patch_cli),
                     (CHUNK_STORE, patch_chunk_store)):
        text = path.read_text(encoding="utf-8")
        new, changed = fn(text)
        assert changed, path.name
        assert MARK in new and _compiles(new), path.name
        again, changed2 = fn(new)
        assert not changed2 and again == new, path.name


def test_cli_patch_adds_the_compact_app():
    new, _ = patch_cli(CLI.read_text(encoding="utf-8"))
    assert 'app.add_typer(compact_app, name="compact")' in new


def test_moved_anchor_is_loud():
    import pytest

    for fn in (patch_stewardship_init, patch_cli, patch_chunk_store):
        with pytest.raises(PatchError):
            fn("nothing anchors here\n")
