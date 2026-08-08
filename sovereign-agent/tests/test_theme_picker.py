"""Behavior tests for theme-picker-d — the in-cockpit theme switcher.

Textual's built-in command palette (normally Ctrl+P) used to be the only
way to browse/change themes in this cockpit; Ctrl+P was repurposed for
voice push-to-talk (qol-voice-binding-d) and the palette was replaced with
CommandPaletteScreen (command-menu-d), which left theme-switching
unreachable from the UI (`sov theme list`/`sov theme set` — the CLI path
— still worked, masking the gap). This restores it as its own surface.
"""
from __future__ import annotations

import pytest


def test_theme_picker_screen_imports_cleanly():
    from sovereign_agent.cockpit.app import ThemePickerScreen
    assert ThemePickerScreen is not None


@pytest.mark.asyncio
async def test_ctrl_t_opens_the_theme_picker():
    # theme-studio-d — Ctrl+T now opens the Theme Studio (browse/create/edit/
    # remove), the richer replacement for the simple picker.
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.app import ThemeStudioScreen

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        assert not isinstance(app.screen, ThemeStudioScreen)

        await pilot.press("ctrl+t")
        await pilot.pause()
        assert isinstance(app.screen, ThemeStudioScreen)


@pytest.mark.asyncio
async def test_clicking_a_theme_applies_it_and_closes_the_popup():
    from textual.widgets import Button

    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.app import ThemePickerScreen
    from sovereign_agent.cockpit.theme_picker_screen import ThemeChoiceButton

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        app.action_theme_picker()
        await pilot.pause()
        assert isinstance(app.screen, ThemePickerScreen)

        choice_buttons = app.screen.query(ThemeChoiceButton)
        assert len(choice_buttons) > 0
        target = next(b for b in choice_buttons if b.theme_name != app.theme)

        await pilot.click(target)
        await pilot.pause()

        assert app.theme == target.theme_name
        assert not isinstance(app.screen, ThemePickerScreen)  # popup auto-closed


@pytest.mark.asyncio
async def test_exit_button_closes_without_changing_theme():
    from textual.widgets import Button

    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.app import ThemePickerScreen

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        app.action_theme_picker()
        await pilot.pause()
        assert isinstance(app.screen, ThemePickerScreen)

        original_theme = app.theme
        exit_btn = app.screen.query_one("#theme-exit-btn", Button)
        await pilot.click(exit_btn)
        await pilot.pause()

        assert not isinstance(app.screen, ThemePickerScreen)
        assert app.theme == original_theme


@pytest.mark.asyncio
async def test_escape_closes_the_theme_picker():
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.app import ThemePickerScreen

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        app.action_theme_picker()
        await pilot.pause()
        assert isinstance(app.screen, ThemePickerScreen)

        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, ThemePickerScreen)


@pytest.mark.asyncio
async def test_command_palette_exit_button_closes_the_popup():
    """The retrofitted "✕ close" button on the existing commands popup."""
    from textual.widgets import Button

    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.app import CommandPaletteScreen

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        app.action_command_palette()
        await pilot.pause()
        assert isinstance(app.screen, CommandPaletteScreen)

        exit_btn = app.screen.query_one("#cp-exit-btn", Button)
        await pilot.click(exit_btn)
        await pilot.pause()
        assert not isinstance(app.screen, CommandPaletteScreen)
