"""Pre-apply structural checks for aria-grounding-wing's patcher (staged-only)."""
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


def test_every_py_patch_applies_compiles_and_is_idempotent():
    for rel, fn in ALL_PATCHES.items():
        text = (SRC / rel).read_text(encoding="utf-8")
        new, changed = fn(text)
        assert changed, rel
        assert MARK in new and _compiles(new), rel
        again, changed2 = fn(new)
        assert not changed2 and again == new, rel


def test_runner_patch_bumps_version_and_adds_tail_import():
    rel = "proving_ground/runner.py"
    new, _ = ALL_PATCHES[rel]((SRC / rel).read_text(encoding="utf-8"))
    assert 'SUITE_VERSION = "v5"' in new
    assert "from .grounding_wing import GROUNDING_TASKS" in new


def test_standard_doc_patch_applies_and_is_idempotent():
    rel = "GOD_TIER_STANDARD.md"
    text = (REPO_ROOT / rel).read_text(encoding="utf-8")
    new, changed = DOC_PATCHES[rel](text)
    assert changed
    assert "composite epistemic score is persisted standing" in new
    again, changed2 = DOC_PATCHES[rel](new)
    assert not changed2 and again == new


def test_floor_json_patch_applies_is_idempotent_and_stays_valid_json():
    rel = "lib/god_tier_floor.json"
    text = (SCRIPTS / rel).read_text(encoding="utf-8")
    new, changed = FLOOR_JSON_PATCHES[rel](text)
    assert changed
    parsed = json.loads(new)
    dims = {d["id"]: d for d in parsed["dimensions"]}
    assert "grounded" in dims["honesty"]["check"]
    again, changed2 = FLOOR_JSON_PATCHES[rel](new)
    assert not changed2 and again == new


def test_grounding_module_patch_adds_the_seam_inside_analyze():
    rel = "tribunal/grounding.py"
    new, _ = ALL_PATCHES[rel]((SRC / rel).read_text(encoding="utf-8"))
    assert "verified-fact" in new


def test_epistemic_ledger_patch_adds_the_seam_inside_current_beliefs():
    rel = "epistemic_ledger/ledger.py"
    new, _ = ALL_PATCHES[rel]((SRC / rel).read_text(encoding="utf-8"))
    assert "revision-quality" in new and "lineage" in new


def test_curiosity_patch_adds_the_seam_near_the_calibration_hook():
    rel = "curiosity.py"
    new, _ = ALL_PATCHES[rel]((SRC / rel).read_text(encoding="utf-8"))
    assert "under-claimed" in new and "intended extension point" in new


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
