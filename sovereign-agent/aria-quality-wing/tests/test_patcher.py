"""Pre-apply structural checks for aria-quality-wing's patcher (staged-only)."""
from __future__ import annotations

import json
import py_compile
import sys
import tempfile
from pathlib import Path

MODULE_ROOT = Path(__file__).parent.parent
REPO_ROOT = MODULE_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))

from patcher import (  # noqa: E402
    ALL_PATCHES, DOC_PATCHES, FLOOR_JSON_PATCHES, MARK, PatchError,
)

SRC = REPO_ROOT / "src/sovereign_agent"
SCRIPTS = REPO_ROOT / "scripts"


def _compiles(source: str) -> bool:
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as fh:
        fh.write(source)
        tmp = fh.name
    try:
        py_compile.compile(tmp, doraise=True)
        return True
    finally:
        Path(tmp).unlink(missing_ok=True)


def test_runner_patch_applies_compiles_and_is_idempotent():
    rel = "proving_ground/runner.py"
    text = (SRC / rel).read_text(encoding="utf-8")
    new, changed = ALL_PATCHES[rel](text)
    assert changed
    assert MARK in new and _compiles(new)
    assert 'SUITE_VERSION = "v4"' in new
    assert "from .quality_wing import QUALITY_TASKS" in new
    again, changed2 = ALL_PATCHES[rel](new)
    assert not changed2 and again == new


def test_standard_doc_patch_applies_and_is_idempotent():
    rel = "GOD_TIER_STANDARD.md"
    text = (REPO_ROOT / rel).read_text(encoding="utf-8")
    new, changed = DOC_PATCHES[rel](text)
    assert changed
    assert "a hardening/test quality score is persisted and gates apply" in new
    again, changed2 = DOC_PATCHES[rel](new)
    assert not changed2 and again == new


def test_floor_json_patch_applies_is_idempotent_and_stays_valid_json():
    rel = "lib/god_tier_floor.json"
    text = (SCRIPTS / rel).read_text(encoding="utf-8")
    new, changed = FLOOR_JSON_PATCHES[rel](text)
    assert changed
    parsed = json.loads(new)
    dims = {d["id"]: d for d in parsed["dimensions"]} if "dimensions" in parsed else {
        d["id"]: d for d in parsed}
    assert "gates apply" in dims["quality"]["check"]
    again, changed2 = FLOOR_JSON_PATCHES[rel](new)
    assert not changed2 and again == new


def test_moved_anchor_is_loud():
    import pytest

    for rel, fn in ALL_PATCHES.items():
        with pytest.raises(PatchError):
            fn("nothing anchors here\n")
    for rel, fn in DOC_PATCHES.items():
        with pytest.raises(PatchError):
            fn("nothing anchors here\n")
    for rel, fn in FLOOR_JSON_PATCHES.items():
        with pytest.raises(PatchError):
            fn("nothing anchors here\n")
