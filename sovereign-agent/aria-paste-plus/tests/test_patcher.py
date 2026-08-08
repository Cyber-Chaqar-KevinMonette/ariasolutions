"""Patcher tests for aria-paste-plus — verify the patch function itself
against the CURRENT live app.py, before anything is applied. Text-transform
assertions only (no sys.modules shadow-copy — that anti-pattern is reserved
for behavior tests that need to actually import a pre-apply patched module;
this file only checks the transform, so plain text checks suffice)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

STAGING = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(STAGING))
from patcher import MARK, PatchError, patch_app  # noqa: E402

REPO_ROOT = STAGING.parent
APP_PATH = REPO_ROOT / "src" / "sovereign_agent" / "cockpit" / "app.py"


def _live_text() -> str:
    return APP_PATH.read_text(encoding="utf-8")


def test_patch_applies_cleanly_against_live_app_py():
    text = _live_text()
    new_text, _ = patch_app(text)  # changed may be False if already applied
    assert MARK in new_text


def test_patch_is_idempotent():
    text = _live_text()
    once, _ = patch_app(text)
    twice, changed2 = patch_app(once)
    assert changed2 is False
    assert once == twice


def test_patched_app_py_compiles():
    import py_compile
    import tempfile

    text = _live_text()
    new_text, _ = patch_app(text)
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(new_text)
        tmp_path = f.name
    py_compile.compile(tmp_path, doraise=True)


def test_paste_preview_screen_payload_compiles():
    import py_compile

    payload = (
        STAGING / "payload" / "src" / "sovereign_agent" / "cockpit"
        / "paste_preview_screen.py"
    )
    py_compile.compile(str(payload), doraise=True)


def test_ripple_input_gets_on_mouse_down_checking_button_3():
    text = _live_text()
    new_text, _ = patch_app(text)
    assert "def on_mouse_down(self, event) -> None:  # paste-plus-d" in new_text
    assert "event.button == 3" in new_text


def test_action_paste_clipboard_checks_for_multiline_before_collapsing():
    text = _live_text()
    new_text, _ = patch_app(text)
    # The new multi-line branch must appear BEFORE the collapse line inside
    # the patched action_paste_clipboard body.
    action_start = new_text.index("def action_paste_clipboard(self) -> None:")
    action_slice = new_text[action_start : action_start + 2000]
    multiline_check_idx = action_slice.index('"\\n" in normalized')
    collapse_idx = action_slice.index("single_line = text.replace")
    assert multiline_check_idx < collapse_idx


def test_send_pasted_text_method_added_and_routes_slash_commands():
    text = _live_text()
    new_text, _ = patch_app(text)
    assert "def _send_pasted_text(self, text: str) -> None:  # paste-plus-d" in new_text
    method_start = new_text.index("def _send_pasted_text")
    method_slice = new_text[method_start : method_start + 600]
    assert 'text.startswith("/")' in method_slice
    assert "self._handle_slash(text)" in method_slice
    assert "self._dispatch_turn(text)" in method_slice


def test_missing_anchor_raises_patch_error_not_silent_noop():
    with pytest.raises(PatchError):
        patch_app("this text has none of the expected anchors")


def test_already_patched_text_is_a_noop():
    text = _live_text()
    once, _ = patch_app(text)
    twice, changed = patch_app(once)
    assert changed is False
    assert twice == once
