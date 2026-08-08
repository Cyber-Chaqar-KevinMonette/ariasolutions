"""Behavior tests for aria-paste-plus, promoted to live tests/ — tests the
REAL, already-patched `sovereign_agent.cockpit.app` directly, no shadow
copy, no `sys.modules` manipulation.

The staged `test_paste_plus.py` (stays in `aria-paste-plus/tests/`, never
promoted) uses a shadow-copy-and-patch mechanism to verify the patch
function itself works correctly BEFORE the code is applied to live. Once
applied, that mechanism is unnecessary — and this session found TWICE
(`test_locator_events_fix.py`, `test_security_strip_wire.py`) that
promoting a shadow-copy test file to live tests/ can actively pollute
unrelated tests elsewhere in the suite via its sys.modules save/delete/
restore dance decoupling shared module-level singletons from conftest.py's
isolation fixtures. Root-cause fix: don't do it. Test the real, live module
directly, exactly like test_cockpit.py does.
"""
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_patched_cockpit_imports_cleanly():
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.app import PastePreviewScreen
    assert CockpitApp is not None
    assert PastePreviewScreen is not None


@pytest.mark.asyncio
async def test_single_line_paste_still_collapses_and_inserts_at_cursor(monkeypatch):
    from sovereign_agent.cockpit import CockpitApp
    from textual.widgets import Input

    monkeypatch.setattr(CockpitApp, "_read_clipboard", staticmethod(lambda: "hello world"))
    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        base_screen = app.screen
        app.action_paste_clipboard()
        await pilot.pause()
        assert app.screen is base_screen
        input_box = app.query_one("#input-box", Input)
        assert input_box.value == "hello world"


@pytest.mark.asyncio
async def test_multiline_paste_opens_preview_screen_instead_of_collapsing(monkeypatch):
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.app import PastePreviewScreen
    from textual.widgets import Input, TextArea

    pasted = "line one\nline two\nline three"
    monkeypatch.setattr(CockpitApp, "_read_clipboard", staticmethod(lambda: pasted))
    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        app.action_paste_clipboard()
        await pilot.pause()

        assert isinstance(app.screen, PastePreviewScreen)
        area = app.screen.query_one("#paste-preview-area", TextArea)
        assert area.text == pasted

        input_box = app.query_one("#input-box", Input)
        assert input_box.value == ""


@pytest.mark.asyncio
async def test_send_button_dispatches_edited_text_and_closes_popup(monkeypatch):
    from sovereign_agent.cockpit import CockpitApp
    from textual.widgets import Button

    pasted = "first\nsecond"
    monkeypatch.setattr(CockpitApp, "_read_clipboard", staticmethod(lambda: pasted))
    dispatched = []
    monkeypatch.setattr(CockpitApp, "_dispatch_turn", lambda self, text: dispatched.append(text))
    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        base_screen = app.screen
        app.action_paste_clipboard()
        await pilot.pause()

        send_btn = app.screen.query_one("#paste-send-btn", Button)
        await pilot.click(send_btn)
        await pilot.pause()

        assert app.screen is base_screen
        assert dispatched == [pasted]


@pytest.mark.asyncio
async def test_cancel_discards_text_without_dispatching(monkeypatch):
    from sovereign_agent.cockpit import CockpitApp
    from textual.widgets import Button

    pasted = "abandon\nthis"
    monkeypatch.setattr(CockpitApp, "_read_clipboard", staticmethod(lambda: pasted))
    dispatched = []
    monkeypatch.setattr(CockpitApp, "_dispatch_turn", lambda self, text: dispatched.append(text))
    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        base_screen = app.screen
        app.action_paste_clipboard()
        await pilot.pause()

        cancel_btn = app.screen.query_one("#paste-cancel-btn", Button)
        await pilot.click(cancel_btn)
        await pilot.pause()

        assert app.screen is base_screen
        assert dispatched == []


@pytest.mark.asyncio
async def test_send_pasted_text_routes_slash_commands_through_slash_handler(monkeypatch):
    from sovereign_agent.cockpit import CockpitApp

    handled = []
    monkeypatch.setattr(CockpitApp, "_handle_slash", lambda self, text: handled.append(text))
    dispatched = []
    monkeypatch.setattr(CockpitApp, "_dispatch_turn", lambda self, text: dispatched.append(text))
    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        app._send_pasted_text("/help\nsome extra context")
        assert handled == ["/help\nsome extra context"]
        assert dispatched == []


@pytest.mark.asyncio
async def test_right_click_on_input_box_triggers_paste(monkeypatch):
    from sovereign_agent.cockpit import CockpitApp
    from textual.widgets import Input

    monkeypatch.setattr(CockpitApp, "_read_clipboard", staticmethod(lambda: "right clicked in"))
    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        input_box = app.query_one("#input-box", Input)
        await pilot.click(input_box, button=3)
        await pilot.pause()
        assert input_box.value == "right clicked in"


@pytest.mark.asyncio
async def test_left_click_on_input_box_still_positions_cursor_normally(monkeypatch):
    from sovereign_agent.cockpit import CockpitApp
    from textual.widgets import Input

    called = []
    monkeypatch.setattr(
        CockpitApp, "action_paste_clipboard", lambda self: called.append(1)
    )
    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        input_box = app.query_one("#input-box", Input)
        input_box.value = "abcdef"
        await pilot.click(input_box, button=1)
        await pilot.pause()
        assert called == []
