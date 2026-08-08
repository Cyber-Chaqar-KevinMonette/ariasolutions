"""Patcher tests for aria-atelier — verify both patch functions against the
CURRENT live loop.py / app.py, before anything is applied. Text-transform
assertions only (no sys.modules shadow-copy needed for these)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

STAGING = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(STAGING))
from patcher import MARK, PatchError, patch_app, patch_loop  # noqa: E402

REPO_ROOT = STAGING.parent
LOOP_PATH = REPO_ROOT / "src" / "sovereign_agent" / "loop.py"
APP_PATH = REPO_ROOT / "src" / "sovereign_agent" / "cockpit" / "app.py"
WORK_EVENTS_PAYLOAD = (
    STAGING / "payload" / "src" / "sovereign_agent" / "work_events.py"
)


def _live_loop_text() -> str:
    return LOOP_PATH.read_text(encoding="utf-8")


def _live_app_text() -> str:
    return APP_PATH.read_text(encoding="utf-8")


def test_loop_patch_applies_cleanly():
    new_text, _ = patch_loop(_live_loop_text())  # changed may be False if already applied
    assert MARK in new_text
    assert "maybe_emit_work_event" in new_text


def test_loop_patch_is_idempotent():
    once, _ = patch_loop(_live_loop_text())
    twice, changed2 = patch_loop(once)
    assert changed2 is False
    assert once == twice


def test_app_patch_applies_cleanly():
    new_text, _ = patch_app(_live_app_text())  # changed may be False if already applied
    assert MARK in new_text
    assert '#atelier-log' in new_text
    assert '#atelier-pane' in new_text
    assert '#divider-4' in new_text


def test_app_patch_is_idempotent():
    once, _ = patch_app(_live_app_text())
    twice, changed2 = patch_app(once)
    assert changed2 is False
    assert once == twice


def test_patched_loop_py_compiles():
    import py_compile
    import tempfile

    new_text, _ = patch_loop(_live_loop_text())
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(new_text)
        tmp_path = f.name
    py_compile.compile(tmp_path, doraise=True)


def test_patched_app_py_compiles():
    import py_compile
    import tempfile

    new_text, _ = patch_app(_live_app_text())
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(new_text)
        tmp_path = f.name
    py_compile.compile(tmp_path, doraise=True)


def test_work_events_payload_compiles():
    import py_compile

    py_compile.compile(str(WORK_EVENTS_PAYLOAD), doraise=True)


def test_render_event_routes_work_flags_before_generic_logic():
    """The work- routing branch must be the FIRST thing _render_event does
    after the JSON-decode guard, so generic flags are completely unaffected
    and work- flags never fall through to the color-by-flag logic below."""
    new_text, _ = patch_app(_live_app_text())
    method_start = new_text.index("def _render_event(self, raw: str) -> None:")
    method_slice = new_text[method_start : method_start + 1200]
    routing_idx = method_slice.index('startswith("work-")')
    color_logic_idx = method_slice.index('if "end" in flag:')
    assert routing_idx < color_logic_idx


def test_render_work_event_method_added_with_all_three_ops():
    new_text, _ = patch_app(_live_app_text())
    assert "def _render_work_event(self, ev: dict) -> None:" in new_text
    method_start = new_text.index("def _render_work_event")
    method_slice = new_text[method_start : method_start + 2000]
    assert 'op == "write"' in method_slice
    assert 'op == "edit"' in method_slice
    assert 'op == "command"' in method_slice


def test_missing_anchor_raises_patch_error_not_silent_noop():
    with pytest.raises(PatchError):
        patch_loop("this text has none of the expected anchors")
    with pytest.raises(PatchError):
        patch_app("this text has none of the expected anchors")


def test_already_patched_text_is_a_noop_for_both():
    loop_once, _ = patch_loop(_live_loop_text())
    loop_twice, changed = patch_loop(loop_once)
    assert changed is False
    assert loop_twice == loop_once

    app_once, _ = patch_app(_live_app_text())
    app_twice, changed = patch_app(app_once)
    assert changed is False
    assert app_twice == app_once
