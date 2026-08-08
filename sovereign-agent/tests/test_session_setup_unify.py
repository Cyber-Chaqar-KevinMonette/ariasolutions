"""Tests for session-setup-unify-d.

Kevin, 2026-07-25: "Maybe add a button next to the layout button that
opens to unified auto, tiers, and modes menu... session or setup."
The unified screen IS ModesScreen (already covers modes+tiers as of the
modes-tier-unify-d fix) plus a new custom-hours (1-12h) picker added to
it -- not a fourth separate screen duplicating that logic. A new
"session-setup-btn" button beside layout-cycle-btn opens the same
screen /modes already does.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest


@pytest.mark.asyncio
async def test_session_setup_button_opens_the_modes_screen():
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.modes_crown_ui import ModesScreen

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        await pilot.click("#session-setup-btn")
        await pilot.pause()
        assert isinstance(app.screen, ModesScreen)


@pytest.mark.asyncio
async def test_custom_hours_input_exists_in_modes_screen():
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.modes_crown_ui import ModesScreen
    from textual.widgets import Input

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        app.push_screen(ModesScreen())
        await pilot.pause()
        screen = app.screen
        assert screen.query_one("#modes-custom-hours", Input) is not None


@pytest.mark.asyncio
async def test_custom_hours_at_tier_1_arms_directly_without_a_tier_prompt():
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.modes_crown_ui import ModesScreen

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        app.push_screen(ModesScreen())
        await pilot.pause()
        screen = app.screen

        with patch("sovereign_agent.auto_crown.AutoCrownStore.get_max_trust_tier",
                  return_value=1), \
             patch.object(screen, "_arm_custom") as arm_custom:
            screen._handle_custom_hours("0.5")

        arm_custom.assert_called_once_with(0.5)
        assert screen._pending_tier_hours is None


@pytest.mark.asyncio
async def test_custom_hours_above_tier_ceiling_prompts_for_the_tier_phrase():
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.modes_crown_ui import ModesScreen
    from sovereign_agent.cockpit.tier_screen import approval_phrase

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        app.push_screen(ModesScreen())
        await pilot.pause()
        screen = app.screen

        with patch("sovereign_agent.auto_crown.AutoCrownStore.get_max_trust_tier",
                  return_value=1):
            screen._handle_custom_hours("6")  # needs tier 4

        assert screen._pending_tier_hours == 6.0
        status = screen.query_one("#modes-status")
        assert approval_phrase(4) in str(status.render())


@pytest.mark.asyncio
async def test_custom_hours_rejects_bad_input_without_crashing():
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.modes_crown_ui import ModesScreen

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        app.push_screen(ModesScreen())
        await pilot.pause()
        screen = app.screen

        screen._handle_custom_hours("not a number")
        status = screen.query_one("#modes-status")
        assert "enter a number" in str(status.render())

        screen._handle_custom_hours("15")  # out of range
        status = screen.query_one("#modes-status")
        assert "between 1 and 12" in str(status.render())


@pytest.mark.asyncio
async def test_correct_tier_phrase_arms_the_custom_duration():
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.modes_crown_ui import ModesScreen
    from sovereign_agent.cockpit.tier_screen import approval_phrase

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        app.push_screen(ModesScreen())
        await pilot.pause()
        screen = app.screen
        screen._pending_tier_hours = 6.0

        with patch("sovereign_agent.auto_crown.AutoCrownStore.set_trust_tier") as set_tier, \
             patch.object(screen, "_arm_custom") as arm_custom:
            screen._handle_tier_confirmation(approval_phrase(4))

        set_tier.assert_called_once_with(4)
        arm_custom.assert_called_once_with(6.0)
        assert screen._pending_tier_hours is None
