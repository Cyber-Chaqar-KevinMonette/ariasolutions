"""Patcher tests for aria-flexi-layout — verify against the CURRENT live
app.py, before anything is applied."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

STAGING = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(STAGING))
from patcher import MARK, PatchError, patch_app  # noqa: E402

REPO_ROOT = STAGING.parent
APP_PY = REPO_ROOT / "src" / "sovereign_agent" / "cockpit" / "app.py"


def _live() -> str:
    return APP_PY.read_text(encoding="utf-8")


def test_applies_and_compiles():
    import py_compile
    import tempfile

    new, _ = patch_app(_live())
    assert MARK in new
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(new)
        tmp = f.name
    py_compile.compile(tmp, doraise=True)


def test_idempotent():
    once, _ = patch_app(_live())
    twice, changed2 = patch_app(once)
    assert changed2 is False and twice == once


def test_layout_b_is_pure_css_grid():
    new, _ = patch_app(_live())
    assert "#main.layout-rows {" in new
    assert "layout: grid;" in new
    assert "row-span: 4" in new  # chat spans all rows
    assert "#main.layout-rows Rule { display: none; }" in new


def test_binding_and_actions_added():
    new, _ = patch_app(_live())
    assert '"ctrl+o", "toggle_layout"' in new
    assert "def action_toggle_layout" in new
    assert "def _apply_saved_layout" in new
    assert "self._apply_saved_layout()" in new


def test_preference_persisted_and_honored():
    new, _ = patch_app(_live())
    assert "cockpit_layout.json" in new
    assert '"layout": "rows" if rows else "columns"' in new


def test_missing_anchor_raises():
    with pytest.raises(PatchError):
        patch_app("no anchors here")
