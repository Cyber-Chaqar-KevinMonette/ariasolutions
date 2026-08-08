"""Tests for discord-control-d — turn off/pause/resume/restart the
Discord bot services from the cockpit.

Kevin, 2026-07-25: "add a way for me to control the bot, turn off the
bot, pause the bot, resume the bot, and restart the discord bot. Maybe a
menu and a button next to the 1 hour button."
"""
from __future__ import annotations

from unittest.mock import patch

import pytest


@pytest.mark.asyncio
async def test_discord_control_button_opens_the_screen():
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.discord_control_screen import DiscordControlScreen

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        # header-reorg-d (2026-08-02): this button moved off the header row
        # into the ⋮ commands popup (REFERENCE_BUTTONS, action="discord-control")
        # — the underlying action is unchanged, call it directly.
        app.action_discord_control()
        await pilot.pause()
        assert isinstance(app.screen, DiscordControlScreen)


@pytest.mark.asyncio
async def test_discord_control_command_opens_the_screen():
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.discord_control_screen import DiscordControlScreen

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        app._handle_slash("/discord-control")
        await pilot.pause()
        assert isinstance(app.screen, DiscordControlScreen)


@pytest.mark.asyncio
async def test_screen_shows_live_status_on_mount():
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.discord_control_screen import DiscordControlScreen
    from textual.widgets import Static

    with patch("sovereign_agent.bot_services.render_states",
              return_value="🎛 Discord services: aria-bot ◉ · aria-duty ◉"):
        async with CockpitApp().run_test() as pilot:
            app = pilot.app
            app.push_screen(DiscordControlScreen())
            await pilot.pause()
            status = app.screen.query_one("#discord-control-status", Static)
            assert "aria-bot" in str(status.render())


@pytest.mark.asyncio
async def test_off_and_pause_both_call_toggle_false():
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.discord_control_screen import DiscordControlScreen

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        app.push_screen(DiscordControlScreen())
        await pilot.pause()
        screen = app.screen

        with patch("sovereign_agent.bot_services.toggle",
                  return_value="▪ Discord bots STOPPED") as toggle:
            screen._run_action("off")
            await pilot.pause()
            toggle.assert_called_once_with(False)

        with patch("sovereign_agent.bot_services.toggle",
                  return_value="▪ Discord bots STOPPED") as toggle:
            screen._run_action("pause")
            await pilot.pause()
            toggle.assert_called_once_with(False)


@pytest.mark.asyncio
async def test_resume_calls_toggle_true():
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.discord_control_screen import DiscordControlScreen

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        app.push_screen(DiscordControlScreen())
        await pilot.pause()
        screen = app.screen

        with patch("sovereign_agent.bot_services.toggle",
                  return_value="◉ Discord bots STARTED") as toggle:
            screen._run_action("resume")
            await pilot.pause()
            toggle.assert_called_once_with(True)


@pytest.mark.asyncio
async def test_restart_calls_the_dedicated_restart_function():
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.discord_control_screen import DiscordControlScreen

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        app.push_screen(DiscordControlScreen())
        await pilot.pause()
        screen = app.screen

        with patch("sovereign_agent.bot_services.restart",
                  return_value="↻ Discord bots RESTARTED") as restart:
            screen._run_action("restart")
            await pilot.pause()
            restart.assert_called_once()


@pytest.mark.asyncio
async def test_restart_duty_button_calls_the_dedicated_function():
    """Kevin, 2026-07-28: 'add a button and command for me to restart it
    [aria-duty] ... put inside the bots menu, or discord menu, or merge
    them into one menu.' Merged in here — the fifth button alongside the
    existing pause/resume/restart/off."""
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.discord_control_screen import DiscordControlScreen
    from textual.widgets import Button

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        app.push_screen(DiscordControlScreen())
        await pilot.pause()
        screen = app.screen
        assert screen.query_one("#discord-restart-duty-btn", Button) is not None

        with patch("sovereign_agent.bot_services.restart_duty",
                  return_value="↻ aria-duty RESTARTED — aria-bot ◉ · aria-duty ◉") as restart_duty:
            screen._run_action("restart-duty")
            await pilot.pause()
            restart_duty.assert_called_once()


@pytest.mark.asyncio
async def test_bots_restart_duty_slash_command_calls_the_dedicated_function():
    """The command-line twin of the new button: /bots restart-duty."""
    from sovereign_agent.cockpit import CockpitApp

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        with patch("sovereign_agent.bot_services.restart_duty",
                  return_value="↻ aria-duty RESTARTED — aria-bot ◉ · aria-duty ◉") as restart_duty:
            app._handle_slash("/bots restart-duty")
            await pilot.pause()
            restart_duty.assert_called_once()


@pytest.mark.asyncio
async def test_action_failure_is_reported_not_swallowed():
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.discord_control_screen import DiscordControlScreen
    from textual.widgets import Static

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        app.push_screen(DiscordControlScreen())
        await pilot.pause()
        screen = app.screen

        with patch("sovereign_agent.bot_services.restart",
                  side_effect=RuntimeError("systemd unreachable")):
            screen._run_action("restart")
            await pilot.pause()
        status = screen.query_one("#discord-control-status", Static)
        assert "action failed" in str(status.render())
        assert "RuntimeError" in str(status.render())
