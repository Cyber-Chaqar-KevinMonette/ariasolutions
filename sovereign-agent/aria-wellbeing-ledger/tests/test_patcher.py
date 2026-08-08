"""Pre-apply structural checks for aria-wellbeing-ledger's patcher (staged-only)."""
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


def test_stewardship_init_patch_registers_wellbeing_sentinel():
    new, _ = ALL_PATCHES["stewardship/__init__.py"](
        (SRC / "stewardship/__init__.py").read_text(encoding="utf-8"))
    assert "wellbeing_sentinel" in new
    assert "grounding_sentinel as _grounding_sentinel" in new


def test_companion_tools_patch_fixes_the_events_glob():
    new, _ = ALL_PATCHES["tools/companion_tools.py"](
        (SRC / "tools/companion_tools.py").read_text(encoding="utf-8"))
    assert 'events_dir.glob("events-*.jsonl")' in new
    assert 'events_dir.glob("*.ndjson")' not in new


def test_moved_anchor_is_loud():
    import pytest

    for rel, fn in ALL_PATCHES.items():
        with pytest.raises(PatchError):
            fn("nothing anchors here\n")
