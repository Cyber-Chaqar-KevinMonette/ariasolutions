"""Pre-apply structural checks for aria-modes-crown's patcher (staged-only)."""
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


def test_tools_init_registers_both_tools():
    new, _ = ALL_PATCHES["tools/__init__.py"](
        (SRC / "tools/__init__.py").read_text(encoding="utf-8"))
    assert "SetStanceTool" in new and "ObservatoryTool" in new


def test_app_patch_adds_bindings_actions_and_slash_verbs():
    new, _ = ALL_PATCHES["cockpit/app.py"](
        (SRC / "cockpit/app.py").read_text(encoding="utf-8"))
    assert 'Binding("f2"' in new and 'Binding("f3"' in new
    assert "def action_modes_crown" in new and "def action_observatory" in new
    assert 'verb == "modes"' in new


def test_bridge_patch_adds_the_gate_and_both_call_sites():
    new, _ = ALL_PATCHES["session_bridge.py"](
        (SRC / "session_bridge.py").read_text(encoding="utf-8"))
    assert new.count("_crown_gate(") >= 3   # def + two call sites
    assert "def _crown_gate" in new


def test_loop_patch_gates_both_cache_sites_on_cacheable():
    new, _ = ALL_PATCHES["loop.py"](
        (SRC / "loop.py").read_text(encoding="utf-8"))
    assert 'getattr(tool, "cacheable", True)' in new
    assert new.count('getattr(tool, "cacheable", True)') == 2


def test_tool_paging_patch_sets_cacheable_false():
    new, _ = ALL_PATCHES["tools/tool_paging.py"](
        (SRC / "tools/tool_paging.py").read_text(encoding="utf-8"))
    assert "cacheable = False" in new


def test_moved_anchor_is_loud():
    import pytest

    for rel, fn in ALL_PATCHES.items():
        with pytest.raises(PatchError):
            fn("nothing anchors here\n")
