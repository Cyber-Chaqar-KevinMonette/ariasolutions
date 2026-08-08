"""Behavior tests for aria-paste-plus (Workstream B) — prove the patched
cockpit actually boots and pastes correctly, using a shadow copy of the
whole package (never touches real src/). STAGED ONLY: this file is never
promoted to live tests/ — see test_paste_plus_live.py, which is what gets
copied to the promoted/live `tests/` dir instead (plain imports, zero
sys.modules manipulation, learned the hard way twice already this session
in test_locator_events_fix.py and test_security_strip_wire.py)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest


def _find_repo_root(start: Path) -> Path:
    for candidate in (start, *start.parents):
        if (candidate / "src" / "sovereign_agent" / "cockpit" / "app.py").is_file():
            return candidate
    raise RuntimeError("could not locate repo root from " + str(start))


def _find_staging_root(start: Path) -> Path:
    for candidate in (start, *start.parents):
        if (candidate / "aria-paste-plus" / "patcher.py").is_file():
            return candidate / "aria-paste-plus"
    raise RuntimeError("could not locate aria-paste-plus/ from " + str(start))


REPO_ROOT = _find_repo_root(Path(__file__).resolve())
STAGING = _find_staging_root(Path(__file__).resolve())


def _build_shadow(tmp_path) -> Path:
    import shutil

    sys.path.insert(0, str(STAGING))
    from patcher import patch_app

    shadow = tmp_path / "shadow"
    shutil.copytree(REPO_ROOT / "src" / "sovereign_agent", shadow / "sovereign_agent")
    for pyc in shadow.rglob("__pycache__"):
        shutil.rmtree(pyc)

    app_py = shadow / "sovereign_agent" / "cockpit" / "app.py"
    patched, _ = patch_app(app_py.read_text(encoding="utf-8"))
    from patcher import MARK
    assert MARK in patched
    app_py.write_text(patched, encoding="utf-8")

    screen_src = (
        STAGING / "payload" / "src" / "sovereign_agent" / "cockpit"
        / "paste_preview_screen.py"
    )
    (shadow / "sovereign_agent" / "cockpit" / "paste_preview_screen.py").write_text(
        screen_src.read_text(encoding="utf-8"), encoding="utf-8"
    )
    return shadow


@pytest.fixture
def shadow_cockpit(tmp_path, monkeypatch):
    """Import CockpitApp + PastePreviewScreen from the shadow copy, saving
    and restoring sys.modules so this never pollutes later tests in the
    same process. Legitimate here (staged, pre-apply verification only —
    never promoted to live tests/)."""
    shadow = _build_shadow(tmp_path)
    saved = {
        name: mod for name, mod in sys.modules.items()
        if name == "sovereign_agent" or name.startswith("sovereign_agent.")
    }
    for name in saved:
        del sys.modules[name]

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    sys.path.insert(0, str(shadow))
    try:
        import sovereign_agent.cockpit.app as shadow_app_mod
        yield shadow_app_mod
    finally:
        sys.path.remove(str(shadow))
        for name in list(sys.modules):
            if name == "sovereign_agent" or name.startswith("sovereign_agent."):
                del sys.modules[name]
        sys.modules.update(saved)


def test_patched_cockpit_imports_cleanly(shadow_cockpit):
    assert shadow_cockpit.CockpitApp is not None
    assert shadow_cockpit.PastePreviewScreen is not None


@pytest.mark.asyncio
async def test_single_line_paste_still_collapses_and_inserts_at_cursor(shadow_cockpit, monkeypatch):
    """Single-line clipboard content must behave EXACTLY as before this
    workstream — no PastePreviewScreen, straight insert at cursor."""
    from textual.widgets import Input

    monkeypatch.setattr(
        shadow_cockpit.CockpitApp, "_read_clipboard", staticmethod(lambda: "hello world")
    )
    app_cls = shadow_cockpit.CockpitApp
    async with app_cls().run_test() as pilot:
        app = pilot.app
        base_screen = app.screen
        app.action_paste_clipboard()
        await pilot.pause()
        assert app.screen is base_screen  # no modal pushed
        input_box = app.query_one("#input-box", Input)
        assert input_box.value == "hello world"


@pytest.mark.asyncio
async def test_multiline_paste_opens_preview_screen_instead_of_collapsing(shadow_cockpit, monkeypatch):
    """The actual regression this workstream fixes: pasted multi-line text
    used to become one space-joined line. Now it opens an editable preview
    with the newlines intact."""
    from textual.widgets import Input, TextArea

    pasted = "line one\nline two\nline three"
    monkeypatch.setattr(
        shadow_cockpit.CockpitApp, "_read_clipboard", staticmethod(lambda: pasted)
    )
    app_cls = shadow_cockpit.CockpitApp
    async with app_cls().run_test() as pilot:
        app = pilot.app
        app.action_paste_clipboard()
        await pilot.pause()

        assert isinstance(app.screen, shadow_cockpit.PastePreviewScreen)
        area = app.screen.query_one("#paste-preview-area", TextArea)
        assert area.text == pasted  # newlines preserved, nothing collapsed

        # Input box must still be empty — nothing was silently inserted.
        input_box = app.query_one("#input-box", Input)
        assert input_box.value == ""


@pytest.mark.asyncio
async def test_send_button_dispatches_edited_text_and_closes_popup(shadow_cockpit, monkeypatch):
    from textual.widgets import Button

    pasted = "first\nsecond"
    monkeypatch.setattr(
        shadow_cockpit.CockpitApp, "_read_clipboard", staticmethod(lambda: pasted)
    )
    dispatched = []
    monkeypatch.setattr(
        shadow_cockpit.CockpitApp, "_dispatch_turn", lambda self, text: dispatched.append(text)
    )
    app_cls = shadow_cockpit.CockpitApp
    async with app_cls().run_test() as pilot:
        app = pilot.app
        base_screen = app.screen
        app.action_paste_clipboard()
        await pilot.pause()

        send_btn = app.screen.query_one("#paste-send-btn", Button)
        await pilot.click(send_btn)
        await pilot.pause()

        assert app.screen is base_screen  # popup closed
        assert dispatched == [pasted]


@pytest.mark.asyncio
async def test_cancel_discards_text_without_dispatching(shadow_cockpit, monkeypatch):
    from textual.widgets import Button

    pasted = "abandon\nthis"
    monkeypatch.setattr(
        shadow_cockpit.CockpitApp, "_read_clipboard", staticmethod(lambda: pasted)
    )
    dispatched = []
    monkeypatch.setattr(
        shadow_cockpit.CockpitApp, "_dispatch_turn", lambda self, text: dispatched.append(text)
    )
    app_cls = shadow_cockpit.CockpitApp
    async with app_cls().run_test() as pilot:
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
async def test_send_pasted_text_routes_slash_commands_through_slash_handler(shadow_cockpit, monkeypatch):
    """_send_pasted_text must honor the same top-priority slash-command
    rule as on_input_submitted — a pasted block that happens to start with
    '/' should not be treated as a conversation turn."""
    handled = []
    monkeypatch.setattr(
        shadow_cockpit.CockpitApp, "_handle_slash", lambda self, text: handled.append(text)
    )
    dispatched = []
    monkeypatch.setattr(
        shadow_cockpit.CockpitApp, "_dispatch_turn", lambda self, text: dispatched.append(text)
    )
    app_cls = shadow_cockpit.CockpitApp
    async with app_cls().run_test() as pilot:
        app = pilot.app
        app._send_pasted_text("/help\nsome extra context")
        assert handled == ["/help\nsome extra context"]
        assert dispatched == []


@pytest.mark.asyncio
async def test_right_click_on_input_box_triggers_paste(shadow_cockpit, monkeypatch):
    """The second half of Workstream B: right-click (button 3) on
    #input-box pastes, same as Ctrl+V."""
    from textual.widgets import Input

    monkeypatch.setattr(
        shadow_cockpit.CockpitApp, "_read_clipboard", staticmethod(lambda: "right clicked in")
    )
    app_cls = shadow_cockpit.CockpitApp
    async with app_cls().run_test() as pilot:
        app = pilot.app
        input_box = app.query_one("#input-box", Input)
        await pilot.click(input_box, button=3)
        await pilot.pause()
        assert input_box.value == "right clicked in"


@pytest.mark.asyncio
async def test_left_click_on_input_box_still_positions_cursor_normally(shadow_cockpit, monkeypatch):
    """Regression guard: adding the right-click handler must not disturb
    ordinary left-click cursor placement."""
    from textual.widgets import Input

    called = []
    monkeypatch.setattr(
        shadow_cockpit.CockpitApp,
        "action_paste_clipboard",
        lambda self: called.append(1),
    )
    app_cls = shadow_cockpit.CockpitApp
    async with app_cls().run_test() as pilot:
        app = pilot.app
        input_box = app.query_one("#input-box", Input)
        input_box.value = "abcdef"
        await pilot.click(input_box, button=1)
        await pilot.pause()
        assert called == []  # left-click never triggers paste
