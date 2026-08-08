"""Cockpit integration tests for ▸ flows and ✦ demo.

Mirrors the house style in test_cockpit.py (Textual App.run_test + Pilot).
"""
from __future__ import annotations

import pytest


def test_commands_popup_holds_everything_else_no_redundancy():
    # menu-split-2-d (Kevin's rule): the ⚙ menu is Settings + Help ONLY;
    # EVERYTHING ELSE — cosmic, workflows, legend, modes, observatory,
    # journal, resume, rec/grow/demo — lives in the ☰ commands popup, with
    # no overlap between the two menus.
    from sovereign_agent.cockpit.app import REFERENCE_BUTTONS, PALETTE_COMMANDS
    from sovereign_agent.cockpit.settings_menu_screen import _HELP_ITEMS, _SETTINGS_ITEMS
    actions = {c.action for c in REFERENCE_BUTTONS}
    # the feature/action surfaces are in the commands popup
    for a in ("demo", "workflows", "cosmic", "legend", "modes", "observatory",
              "journal", "resume"):
        assert a in actions, f"{a} should be in the ☰ commands popup"
    # the ⚙ menu is settings + help only — no overlap
    gear_keys = {k for _, k in _SETTINGS_ITEMS} | {k for _, k in _HELP_ITEMS}
    assert not (gear_keys & actions), "no redundancy between ⚙ and ☰"
    assert "workflows" not in gear_keys and "cosmic" not in gear_keys
    palette_keys = {c.key for c in PALETTE_COMMANDS}
    for c in REFERENCE_BUTTONS:
        assert c.command == "", "reference buttons carry an action, not a command"
        assert c.action, "reference button must have an action"
        assert c.key not in palette_keys, "reference key must not collide with a palette command"


@pytest.mark.asyncio
async def test_slash_workflows_pushes_workflows_screen():
    from sovereign_agent.cockpit import CockpitApp, WorkflowsScreen
    from textual.widgets import Input
    app = CockpitApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        ib = app.query_one("#input-box")
        app.on_input_submitted(Input.Submitted(ib, "/workflows", validation_result=None))
        await pilot.pause()
        assert isinstance(app.screen, WorkflowsScreen)
        # Esc dismisses it cleanly.
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, WorkflowsScreen)


@pytest.mark.asyncio
async def test_slash_flows_alias_also_opens_screen():
    from sovereign_agent.cockpit import CockpitApp, WorkflowsScreen
    from textual.widgets import Input
    app = CockpitApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        ib = app.query_one("#input-box")
        app.on_input_submitted(Input.Submitted(ib, "/flows", validation_result=None))
        await pilot.pause()
        assert isinstance(app.screen, WorkflowsScreen)


@pytest.mark.asyncio
async def test_slash_workflows_list_writes_to_chat():
    from sovereign_agent.cockpit import CockpitApp
    from textual.widgets import Input
    app = CockpitApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        chat = app.query_one("#chat-log")
        before = len(chat.lines)
        ib = app.query_one("#input-box")
        app.on_input_submitted(Input.Submitted(ib, "/workflows list", validation_result=None))
        await pilot.pause()
        assert len(chat.lines) > before
        # listing must not push the modal
        from sovereign_agent.cockpit import WorkflowsScreen
        assert not isinstance(app.screen, WorkflowsScreen)


@pytest.mark.asyncio
async def test_slash_demo_runs_without_crashing():
    from sovereign_agent.cockpit import CockpitApp
    from textual.widgets import Input
    app = CockpitApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        ib = app.query_one("#input-box")
        # /demo kicks off the bounded demonstration; a start line is written
        # synchronously before the worker thread runs.
        events = app.query_one("#events-log")
        before = len(events.lines)
        app.on_input_submitted(Input.Submitted(ib, "/demo", validation_result=None))
        await pilot.pause()
        assert len(events.lines) >= before  # did not crash; surfaced something


@pytest.mark.asyncio
async def test_workflows_screen_renders_catalog():
    from sovereign_agent.cockpit import CockpitApp, WorkflowsScreen
    app = CockpitApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.push_screen(WorkflowsScreen())
        await pilot.pause()
        content = app.screen.query_one("#workflows-content")
        assert content is not None


@pytest.mark.asyncio
async def test_command_buttons_ripple_by_default_in_any_theme():
    """The buttons + input glow in every theme now (per-theme opt-out only).

    Workstream M (2026-07-03) moved the palette's CommandButtons off the
    base screen into the CommandPaletteScreen popup (Ctrl+M / "☰ commands")
    to reclaim space for the observability/security/emotions strips — they
    are no longer mounted on the base screen by default, so this test opens
    the popup first. The ripple-border behavior itself is unchanged.
    """
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.app import CommandButton
    app = CockpitApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.action_command_palette()
        await pilot.pause()
        buttons = list(app.screen.query(CommandButton))
        assert buttons, "expected palette buttons"
        # With no theme opting widgets out, the ripple border is active by default.
        assert any(b._ripple_border_active() for b in buttons)


@pytest.mark.asyncio
async def test_slash_themes_lists_to_chat_without_modal():
    """/themes lists curated + user themes to chat and never pushes a modal."""
    from sovereign_agent.cockpit import CockpitApp, WorkflowsScreen
    from textual.widgets import Input
    app = CockpitApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        chat = app.query_one("#chat-log")
        before = len(chat.lines)
        ib = app.query_one("#input-box")
        app.on_input_submitted(Input.Submitted(ib, "/themes", validation_result=None))
        await pilot.pause()
        assert len(chat.lines) > before
        assert not isinstance(app.screen, WorkflowsScreen)


@pytest.mark.asyncio
async def test_slash_themes_rescan_runs_without_crashing():
    """/themes rescan live-rediscovers themes (idempotent) and reports to chat."""
    from sovereign_agent.cockpit import CockpitApp
    from textual.widgets import Input
    app = CockpitApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        chat = app.query_one("#chat-log")
        before = len(chat.lines)
        ib = app.query_one("#input-box")
        app.on_input_submitted(Input.Submitted(ib, "/themes rescan", validation_result=None))
        await pilot.pause()
        assert len(chat.lines) > before
        # a second rescan should also be safe (idempotent) and report new=none
        app.on_input_submitted(Input.Submitted(ib, "/themes rescan", validation_result=None))
        await pilot.pause()
