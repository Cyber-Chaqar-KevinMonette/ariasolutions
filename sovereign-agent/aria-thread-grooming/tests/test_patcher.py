"""Pre-apply structural checks for aria-thread-grooming's patcher (staged-only)."""
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


def test_patched_scanner_behaves(tmp_path):
    """Behavioral pre-apply check: exec the PATCHED scanner source and run
    it on a synthetic tree — the idioms are recognized, orphans still are."""
    import textwrap
    import types

    src = (SRC / "loose_threads/scanner.py").read_text(encoding="utf-8")
    patched, _ = ALL_PATCHES["loose_threads/scanner.py"](src)
    mod = types.ModuleType("_patched_scanner")
    sys.modules["_patched_scanner"] = mod   # dataclasses needs the module ref
    try:
        exec(compile(patched, "<patched scanner>", "exec"), mod.__dict__)
    except Exception:
        sys.modules.pop("_patched_scanner", None)
        raise

    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "mod.py").write_text(textwrap.dedent('''
        import mcp

        @mcp.tool()
        def endpoint(): ...

        class FooChannel(MemoryChannel): ...

        def true_orphan(): ...
    '''), encoding="utf-8")
    try:
        scan = mod.scan_threads(pkg)
    finally:
        sys.modules.pop("_patched_scanner", None)
    flagged = {t.symbol.rsplit(".", 1)[-1] for t in scan.threads}
    assert flagged == {"true_orphan"}


def test_bridge_patch_wires_both_entry_points():
    new, _ = ALL_PATCHES["session_bridge.py"](
        (SRC / "session_bridge.py").read_text(encoding="utf-8"))
    assert new.count("_lease_check(") >= 3    # def + two call sites
    assert "arm_lease" in new and "disarm_lease" in new


def test_moved_anchor_is_loud():
    import pytest

    for rel, fn in ALL_PATCHES.items():
        with pytest.raises(PatchError):
            fn("nothing anchors here\n")
