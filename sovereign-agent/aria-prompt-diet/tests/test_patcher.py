"""Patcher tests for aria-prompt-diet — verify the patch function against
the CURRENT live loop.py, before anything is applied."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

STAGING = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(STAGING))
from patcher import MARK, PatchError, patch_loop  # noqa: E402

REPO_ROOT = STAGING.parent
LOOP_PY = REPO_ROOT / "src" / "sovereign_agent" / "loop.py"
DIET_PAYLOAD = STAGING / "payload" / "src" / "sovereign_agent" / "prompt_diet.py"


def _live() -> str:
    return LOOP_PY.read_text(encoding="utf-8")


def test_applies_and_compiles():
    import py_compile
    import tempfile

    new, _ = patch_loop(_live())
    assert MARK in new
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(new)
        tmp = f.name
    py_compile.compile(tmp, doraise=True)


def test_idempotent():
    once, _ = patch_loop(_live())
    twice, changed2 = patch_loop(once)
    assert changed2 is False and twice == once


def test_system_prompt_routes_through_diet():
    new, _ = patch_loop(_live())
    assert "_diet_render(SYSTEM_PROMPT_TEMPLATE, mode.value).format(" in new


def test_tool_list_routes_through_diet_at_both_sites():
    """Both the initial build AND the mid-loop mode-switch rebuild must
    stay dieted."""
    new, _ = patch_loop(_live())
    assert new.count("_diet_select_tools(") == 2  # the two call sites
    assert "import select_tools as _diet_select_tools" in new


def test_diet_event_recorded():
    new, _ = patch_loop(_live())
    assert '"prompt-diet-d"' in new
    assert '"tools_sent"' in new
    assert '"tools_registered"' in new


def test_missing_anchor_raises():
    with pytest.raises(PatchError):
        patch_loop("no anchors here")


def test_diet_payload_compiles():
    import py_compile
    import tempfile

    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(DIET_PAYLOAD.read_text(encoding="utf-8"))
        tmp = f.name
    py_compile.compile(tmp, doraise=True)
