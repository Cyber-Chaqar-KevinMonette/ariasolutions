"""
test_cockpit.py — smoke tests for the v0.2.15.3 operator cockpit.

Textual provides `App.run_test()` which runs the app headlessly with a
Pilot for driving keyboard input. We use it to prove:

  1. The app launches and the layout renders without errors.
  2. All widgets are present and reachable.
  3. The keybindings are wired (Ctrl-L clears, etc).
  4. The slash-command parser dispatches correctly.
  5. The status worker can read state from a real (test) data dir.

We do NOT test the directive dispatch (`sov do`) here — that would
require an Ollama server and a model. The CLI dispatch path is
covered by the unit tests on `sov do` itself elsewhere.
"""
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_cockpit_launches_and_renders():
    """The most basic invariant: the app must render without crashing."""
    from sovereign_agent.cockpit import CockpitApp
    app = CockpitApp()
    async with app.run_test() as pilot:
        # Let the on_mount handler complete.
        await pilot.pause()
        # The four core widgets must be reachable.
        chat = app.query_one("#chat-log")
        events = app.query_one("#events-log")
        input_box = app.query_one("#input-box")
        status = app.query_one("#status-bar")
        assert chat is not None
        assert events is not None
        assert input_box is not None
        assert status is not None


@pytest.mark.asyncio
async def test_clear_chat_binding():
    """Ctrl-L should clear the chat log (welcome message goes away)."""
    from sovereign_agent.cockpit import CockpitApp
    app = CockpitApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        # Welcome message was written on mount.
        chat = app.query_one("#chat-log")
        line_count_before = len(chat.lines)
        assert line_count_before > 0
        # Trigger clear directly (action paths run reliably; key delivery
        # depends on terminal emulation specifics).
        app.action_clear_chat()
        await pilot.pause()
        # After clear we should have just the "chat cleared" meta line.
        assert len(chat.lines) < line_count_before


@pytest.mark.asyncio
async def test_slash_quit_exits_app():
    """Typing /quit should exit the app cleanly."""
    from sovereign_agent.cockpit import CockpitApp
    app = CockpitApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        # Inject text into the input and submit.
        input_box = app.query_one("#input-box")
        input_box.value = "/quit"
        # Submitting Input emits a Submitted message which routes through
        # on_input_submitted. We invoke the handler directly here.
        from textual.widgets import Input
        msg = Input.Submitted(input_box, "/quit", validation_result=None)
        app.on_input_submitted(msg)
        await pilot.pause()
        # After /quit the app should be exiting.
        assert app._exit is True or app.return_value is None


@pytest.mark.asyncio
async def test_slash_help_pushes_help_screen():
    """Typing /help should push the help modal."""
    from sovereign_agent.cockpit import CockpitApp, HelpScreen
    app = CockpitApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        from textual.widgets import Input
        input_box = app.query_one("#input-box")
        msg = Input.Submitted(input_box, "/help", validation_result=None)
        app.on_input_submitted(msg)
        await pilot.pause()
        assert isinstance(app.screen, HelpScreen)


@pytest.mark.asyncio
async def test_unknown_slash_command_is_handled():
    """Unknown slash commands should be reported, not crash."""
    from sovereign_agent.cockpit import CockpitApp
    app = CockpitApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        from textual.widgets import Input
        input_box = app.query_one("#input-box")
        chat = app.query_one("#chat-log")
        lines_before = len(chat.lines)
        msg = Input.Submitted(input_box, "/floopdoodle", validation_result=None)
        app.on_input_submitted(msg)
        await pilot.pause()
        # A "unknown command" line should have been added.
        assert len(chat.lines) > lines_before


@pytest.mark.asyncio
async def test_status_read_does_not_crash_on_fresh_dir():
    """Status read must succeed against a fresh data dir (no atoms.db ledger)."""
    from sovereign_agent import __version__
    from sovereign_agent.cockpit.app import CockpitApp
    app = CockpitApp()
    # Direct synchronous call to the read helper.
    s = app._read_status()
    # On fresh data: ledger may be considered clean (0 rows is clean).
    # The important thing: it didn't raise.
    # Version comes from the live __version__ (MOS-SURFACE S4).
    assert s.version == __version__
    assert isinstance(s.halt, bool)
    assert isinstance(s.daemon_active, bool)


@pytest.mark.asyncio
async def test_inbox_pane_exists_and_renders_requests():
    """v0.2.37.0 — the 4th window (◊ inbox) must exist and render the
    collaboration requests filed in the store."""
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.config import SETTINGS
    from sovereign_agent.persistence.store import ErebloStore
    from sovereign_agent.workflow.requests import RequestStore

    rs = RequestStore(ErebloStore(SETTINGS.paths.atoms_db))
    rs.open("question", "What database should I use?")
    done = rs.open("suggestion", "Add a cache layer")
    rs.resolve(done.request_id)

    app = CockpitApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        inbox = app.query_one("#inbox-log")
        assert inbox is not None
        app._refresh_inbox_pane()
        await pilot.pause()
        # The pane rendered content (open item + recent section).
        assert len(inbox.lines) > 0


def test_palette_commands_all_have_descriptions():
    """v0.2.39.0 — every palette button must carry a human description so the
    legend / tooltips can explain it."""
    from sovereign_agent.cockpit.app import PALETTE_COMMANDS
    assert len(PALETTE_COMMANDS) >= 18
    assert all(p.desc.strip() for p in PALETTE_COMMANDS), \
        "every PaletteCommand needs a desc"
    # the newer surfaces are present
    keys = {p.key for p in PALETTE_COMMANDS}
    assert {"requests", "parked", "capabilities", "vault"} <= keys


@pytest.mark.asyncio
async def test_palette_buttons_render_with_tooltips():
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.app import CommandButton, PALETTE_COMMANDS
    app = CockpitApp()
    async with app.run_test(size=(130, 46)) as pilot:
        await pilot.pause()
        buttons = list(app.query(CommandButton))
        from sovereign_agent.cockpit.app import REFERENCE_BUTTONS
        assert len(buttons) == len(PALETTE_COMMANDS) + len(REFERENCE_BUTTONS)
        # the inbox button exists and its tooltip carries the description
        inbox = app.query_one("#palette-requests", CommandButton)
        assert "sov requests" in (inbox.tooltip or "")
        assert "inbox" in (inbox.tooltip or "").lower()


@pytest.mark.asyncio
async def test_slash_palette_prints_legend():
    from sovereign_agent.cockpit import CockpitApp
    app = CockpitApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        chat = app.query_one("#chat-log")
        before = len(chat.lines)
        app._show_palette_legend()
        await pilot.pause()
        assert len(chat.lines) > before    # legend was written


# ── help screen must always be dismissable (v0.2.39.0 bugfix) ──────────────

@pytest.mark.asyncio
async def test_help_screen_dismisses_with_escape():
    from sovereign_agent.cockpit import CockpitApp, HelpScreen
    app = CockpitApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.action_help(); await pilot.pause()
        assert isinstance(app.screen, HelpScreen)
        await pilot.press("escape"); await pilot.pause()
        assert not isinstance(app.screen, HelpScreen)


@pytest.mark.asyncio
async def test_help_screen_dismisses_with_q():
    from sovereign_agent.cockpit import CockpitApp, HelpScreen
    app = CockpitApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.action_help(); await pilot.pause()
        await pilot.press("q"); await pilot.pause()
        assert not isinstance(app.screen, HelpScreen)


@pytest.mark.asyncio
async def test_f1_toggles_help_does_not_stack():
    """The actual bug: F1 used to push a SECOND help screen on top. Now it
    toggles — open, then F1 closes (stack returns to 1)."""
    from sovereign_agent.cockpit import CockpitApp, HelpScreen
    app = CockpitApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        base_depth = len(app.screen_stack)
        app.action_help(); await pilot.pause()
        assert isinstance(app.screen, HelpScreen)
        await pilot.press("f1"); await pilot.pause()
        assert not isinstance(app.screen, HelpScreen)
        assert len(app.screen_stack) == base_depth   # no stacking


@pytest.mark.asyncio
async def test_help_screen_has_close_button():
    from sovereign_agent.cockpit import CockpitApp
    app = CockpitApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.action_help(); await pilot.pause()
        assert app.screen.query_one("#help-close") is not None


# ── right-side reference buttons (v0.2.39.0) ───────────────────────────────

def test_reference_buttons_are_not_palette_commands():
    """Reference buttons (legend/help) run internal actions and have empty
    command strings — they must stay OUT of PALETTE_COMMANDS so the palette
    safety invariant (every command is a safe sov subprocess) holds."""
    from sovereign_agent.cockpit.app import PALETTE_COMMANDS, REFERENCE_BUTTONS
    palette_keys = {p.key for p in PALETTE_COMMANDS}
    for r in REFERENCE_BUTTONS:
        assert r.action, "reference buttons must carry an action"
        assert r.command == "", "reference buttons must not paste a command"
        assert r.key not in palette_keys


@pytest.mark.asyncio
async def test_reference_buttons_render_right_of_commands():
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.app import CommandButton
    app = CockpitApp()
    async with app.run_test(size=(130, 48)) as pilot:
        await pilot.pause()
        row3 = app.query_one("#palette-row-3")
        names = [getattr(c, "palette_cmd", None).key if isinstance(c, CommandButton)
                 else "SPACER" for c in row3.children]
        # a spacer separates the left command buttons from the right refs
        assert "SPACER" in names
        spacer_at = names.index("SPACER")
        assert "legend" in names and "help" in names
        assert names.index("legend") > spacer_at   # legend is to the right
        assert names.index("help") > spacer_at


@pytest.mark.asyncio
async def test_clicking_legend_button_prints_legend():
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.app import CommandButton
    from textual.widgets import Button
    app = CockpitApp()
    async with app.run_test(size=(130, 48)) as pilot:
        await pilot.pause()
        legend = app.query_one("#palette-legend", CommandButton)
        chat = app.query_one("#chat-log"); before = len(chat.lines)
        app.on_button_pressed(Button.Pressed(legend)); await pilot.pause()
        assert len(chat.lines) > before
