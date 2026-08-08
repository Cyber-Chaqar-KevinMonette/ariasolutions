"""Behavior tests for menu-split-d — the top-left Settings & Help menu,
the Controls menu (footer replacement), the Changelog viewer, and the
regression that the gear and the ☰ button now open DIFFERENT screens.
"""
from __future__ import annotations

import pytest


def test_menu_screens_import_cleanly():
    from sovereign_agent.cockpit.app import (
        ChangelogScreen,
        CommandPaletteScreen,
        ControlsScreen,
        SettingsMenuScreen,
    )
    assert SettingsMenuScreen is not None
    assert ControlsScreen is not None
    assert ChangelogScreen is not None
    assert CommandPaletteScreen is not None


@pytest.mark.asyncio
async def test_gear_and_commands_open_different_screens():
    """The core redundancy fix: the gear action (settings_menu) and the ☰
    action (command_palette) must push DIFFERENT screen classes."""
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.app import (
        CommandPaletteScreen,
        SettingsMenuScreen,
    )

    async with CockpitApp().run_test() as pilot:
        app = pilot.app

        app.action_settings_menu()
        await pilot.pause()
        assert isinstance(app.screen, SettingsMenuScreen)
        assert not isinstance(app.screen, CommandPaletteScreen)
        app.pop_screen()
        await pilot.pause()

        app.action_command_palette()
        await pilot.pause()
        assert isinstance(app.screen, CommandPaletteScreen)
        assert not isinstance(app.screen, SettingsMenuScreen)


@pytest.mark.asyncio
async def test_settings_menu_theme_item_routes_to_theme_studio():
    # theme-studio-d — the Settings → Theme entry opens the Theme Studio.
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.app import SettingsMenuScreen, ThemeStudioScreen
    from sovereign_agent.cockpit.settings_menu_screen import MenuItemButton

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        app.action_settings_menu()
        await pilot.pause()
        assert isinstance(app.screen, SettingsMenuScreen)

        theme_btn = next(
            b for b in app.screen.query(MenuItemButton) if b.item_key == "theme"
        )
        await pilot.click(theme_btn)
        await pilot.pause()
        # The settings menu closed and the Theme Studio opened.
        assert isinstance(app.screen, ThemeStudioScreen)


@pytest.mark.asyncio
async def test_settings_menu_exit_button_closes():
    from textual.widgets import Button

    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.app import SettingsMenuScreen

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        app.action_settings_menu()
        await pilot.pause()
        assert isinstance(app.screen, SettingsMenuScreen)

        exit_btn = app.screen.query_one("#settings-exit-btn", Button)
        await pilot.click(exit_btn)
        await pilot.pause()
        assert not isinstance(app.screen, SettingsMenuScreen)


@pytest.mark.asyncio
async def test_controls_menu_opens_via_action_and_lists_bindings():
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.app import ControlsScreen

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        app.action_controls()
        await pilot.pause()
        assert isinstance(app.screen, ControlsScreen)
        # Renders something referencing a known control (quit).
        text = " ".join(str(s.render()) for s in app.screen.query("Static"))
        assert "quit" in text.lower()

        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, ControlsScreen)


@pytest.mark.asyncio
async def test_changelog_opens_and_shows_version():
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.app import ChangelogScreen
    from sovereign_agent import __version__

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        app.action_changelog()
        await pilot.pause()
        assert isinstance(app.screen, ChangelogScreen)
        text = " ".join(str(s.render()) for s in app.screen.query("Static"))
        assert __version__ in text


@pytest.mark.asyncio
async def test_footer_key_row_is_gone():
    """menu-split-d removed the always-on Footer; the status row stays."""
    from textual.widgets import Footer

    from sovereign_agent.cockpit import CockpitApp

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        assert len(app.query(Footer)) == 0
        # The heart/status row is still present.
        assert app.query_one("#status-bar") is not None


@pytest.mark.asyncio
async def test_commands_trigger_button_does_not_hold_focus_highlight():
    """stuck-highlight-fix-d — the ☰ commands trigger button must not keep the
    focus-ring after opening (and closing) the popup. It is non-focusable, so
    Textual never restores focus to it and it never stays highlighted."""
    from textual.widgets import Button

    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.app import CommandPaletteScreen, MenuTriggerButton

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        trigger = app.query_one("#palette-menu-btn", Button)
        assert isinstance(trigger, MenuTriggerButton)
        assert trigger.can_focus is False           # never a focus target

        await pilot.click(trigger)                   # opens the popup
        await pilot.pause()
        assert isinstance(app.screen, CommandPaletteScreen)
        app.pop_screen()                             # close it
        await pilot.pause()
        # focus must NOT have been restored to the trigger button
        assert app.focused is not trigger


@pytest.mark.asyncio
async def test_gear_icon_opens_only_settings_not_both():
    """stuck-both-menus-fix-d — clicking the header gear must open ONLY the
    Settings menu, never also the command palette (Kevin: 'it opens both')."""
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.app import (
        CommandPaletteScreen, SettingsHeaderIcon, SettingsMenuScreen,
    )

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        icon = app.query(SettingsHeaderIcon).first()
        await pilot.click(icon)
        await pilot.pause()
        stack = [type(s).__name__ for s in app.screen_stack]
        # exactly the base screen + the settings menu — NOT the command palette
        assert isinstance(app.screen, SettingsMenuScreen)
        assert not any(isinstance(s, CommandPaletteScreen) for s in app.screen_stack), stack
        assert stack.count("SettingsMenuScreen") == 1
