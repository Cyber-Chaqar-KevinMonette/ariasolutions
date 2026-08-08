"""Pre-apply structural checks for aria-quality-sentinel's patcher (staged-only)."""
from __future__ import annotations

import py_compile
import sys
import tempfile
from pathlib import Path

MODULE_ROOT = Path(__file__).parent.parent
REPO_ROOT = MODULE_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))

from patcher import ALL_PATCHES, DOC_PATCHES, MARK, PatchError  # noqa: E402

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


def test_every_code_patch_applies_compiles_and_is_idempotent():
    for rel, fn in ALL_PATCHES.items():
        text = (SRC / rel).read_text(encoding="utf-8")
        new, changed = fn(text)
        assert changed, rel
        assert MARK in new and _compiles(new), rel
        again, changed2 = fn(new)
        assert not changed2 and again == new, rel


def test_stewardship_init_registers_quality_sentinel():
    new, _ = ALL_PATCHES["stewardship/__init__.py"](
        (SRC / "stewardship/__init__.py").read_text(encoding="utf-8"))
    assert "quality_sentinel" in new


def test_app_patch_adds_the_persistence_method_and_call_site():
    new, _ = ALL_PATCHES["cockpit/app.py"](
        (SRC / "cockpit/app.py").read_text(encoding="utf-8"))
    assert "def _persist_worker_latch" in new
    assert "self._persist_worker_latch(group)" in new


def test_doc_patch_applies_and_is_idempotent():
    text = (REPO_ROOT / "GOD_TIER_CRITERIA.md").read_text(encoding="utf-8")
    new, changed = DOC_PATCHES["GOD_TIER_CRITERIA.md"](text)
    assert changed
    assert "Worker supervision / self-restart. **MET**" in new
    assert "**GAP**" not in new.split("Worker supervision")[1][:120]
    assert "~~Dead-worker badges~~" in new
    again, changed2 = DOC_PATCHES["GOD_TIER_CRITERIA.md"](new)
    assert not changed2 and again == new


def test_moved_anchor_is_loud():
    import pytest

    for rel, fn in ALL_PATCHES.items():
        with pytest.raises(PatchError):
            fn("nothing anchors here\n")
    with pytest.raises(PatchError):
        DOC_PATCHES["GOD_TIER_CRITERIA.md"]("nothing anchors here\n")
