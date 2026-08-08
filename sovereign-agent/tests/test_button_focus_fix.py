"""Tests for button-focus-fix-d — the quick-view button must not be a
focus target (same stuck-highlight bug the commands button already had,
fixed via MenuTriggerButton's can_focus=False)."""
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_quick_view_button_is_a_menu_trigger_button_not_focusable():
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.app import MenuTriggerButton

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        btn = app.query_one("#quick-view-btn")
        assert isinstance(btn, MenuTriggerButton)
        assert btn.can_focus is False


@pytest.mark.asyncio
async def test_quick_view_button_click_still_works(tmp_path):
    from textual.widgets import Button

    from sovereign_agent.cockpit import CockpitApp

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        main = app.query_one("#main")
        was_simplified = main.has_class("chat-top") and main.has_class("obs-focus")
        btn = app.query_one("#quick-view-btn", Button)
        await pilot.click(btn)
        await pilot.pause()
        now_simplified = main.has_class("chat-top") and main.has_class("obs-focus")
        assert now_simplified != was_simplified  # the click still toggled the view


@pytest.mark.asyncio
async def test_quick_view_shows_live_activity_not_just_chat_and_inbox():
    """Kevin, 2026-07-21: "Add the live window in the other view mode
    with the horizontal views. I [want] to see live activity." The
    quick-view combo (chat-top + obs-focus) used to hide live-pane like
    plain obs-focus does -- it must now show it."""
    from sovereign_agent.cockpit import CockpitApp

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        app.action_quick_view()
        await pilot.pause()
        main = app.query_one("#main")
        assert main.has_class("chat-top") and main.has_class("obs-focus")
        live_pane = app.query_one("#live-pane")
        assert live_pane.styles.display != "none"


@pytest.mark.asyncio
async def test_layout_cycle_button_is_a_menu_trigger_button_not_focusable():
    """view-selectors-d (Kevin, 2026-07-21): "should we add another view
    button? and treat the two view button like view selectors?" -- a
    second, dedicated button for cycling pane layout (columns/rows/
    chat-top), same can_focus=False discipline as every other
    fire-and-handoff button in this file."""
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.app import MenuTriggerButton

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        btn = app.query_one("#layout-cycle-btn")
        assert isinstance(btn, MenuTriggerButton)
        assert btn.can_focus is False


@pytest.mark.asyncio
async def test_layout_cycle_button_click_actually_cycles_the_layout():
    from textual.widgets import Button

    from sovereign_agent.cockpit import CockpitApp

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        main = app.query_one("#main")
        assert not main.has_class("layout-rows") and not main.has_class("chat-top")

        btn = app.query_one("#layout-cycle-btn", Button)
        await pilot.click(btn)
        await pilot.pause()
        assert main.has_class("layout-rows")  # columns -> rows

        await pilot.click(btn)
        await pilot.pause()
        assert main.has_class("chat-top") and not main.has_class("layout-rows")

        await pilot.click(btn)
        await pilot.pause()
        assert not main.has_class("layout-rows") and not main.has_class("chat-top")
