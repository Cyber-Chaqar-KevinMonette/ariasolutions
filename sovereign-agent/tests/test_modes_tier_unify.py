"""Tests for modes-tier-unify-d.

Kevin, 2026-07-25: "Modes should activate auto and tiers at the same time
I believe it says it does but it does not actually do so." Root cause:
picking a 3h+ profile in /modes without first unlocking that trust tier
via /tiers (F4) used to fail with a CrownError pointing Kevin at that
SEPARATE screen. Now the tier ceremony (the same approval phrase
tier_screen.py already uses) happens inline, in ModesScreen itself.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest


@pytest.mark.asyncio
async def test_picking_auto_3h_at_tier_1_prompts_for_the_tier_phrase_inline():
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.modes_crown_ui import ModesScreen
    from sovereign_agent.cockpit.tier_screen import approval_phrase

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        app.push_screen(ModesScreen())
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, ModesScreen)

        with patch("sovereign_agent.auto_crown.AutoCrownStore.get_max_trust_tier",
                  return_value=1):
            event = type("E", (), {"button": type("B", (), {"id": "mode-auto-3h"})(), "stop": lambda self: None})()
            screen.on_button_pressed(event)

        assert screen._pending_tier_mode == "auto-3h"
        status = screen.query_one("#modes-status")
        assert approval_phrase(3) in str(status.render())


@pytest.mark.asyncio
async def test_correct_tier_phrase_raises_tier_then_asks_for_the_modes_own_confirmation():
    """auto-3h needs BOTH: the tier-3 approval AND its own separate typed
    confirmation ("I approve 3 hours of autonomy") -- two distinct,
    deliberate ceremonies, neither silently skipped."""
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.modes_crown_ui import ModesScreen
    from sovereign_agent.cockpit.tier_screen import approval_phrase

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        app.push_screen(ModesScreen())
        await pilot.pause()
        screen = app.screen
        screen._pending_tier_mode = "auto-3h"

        raised = []
        with patch("sovereign_agent.auto_crown.AutoCrownStore.set_trust_tier",
                  side_effect=lambda tier, **kw: raised.append(tier)):
            screen._handle_tier_confirmation(approval_phrase(3))

        assert raised == [3]
        assert screen._pending_tier_mode == ""
        assert screen._pending_mode == "auto-3h"  # now waiting on the mode's OWN phrase
        status = screen.query_one("#modes-status")
        assert "I approve 3 hours of autonomy" in str(status.render())


@pytest.mark.asyncio
async def test_wrong_tier_phrase_does_not_raise_the_tier():
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.modes_crown_ui import ModesScreen

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        app.push_screen(ModesScreen())
        await pilot.pause()
        screen = app.screen
        screen._pending_tier_mode = "auto-3h"

        with patch("sovereign_agent.auto_crown.AutoCrownStore.set_trust_tier") as set_tier:
            screen._handle_tier_confirmation("nope not the phrase")

        set_tier.assert_not_called()
        assert screen._pending_tier_mode == "auto-3h"  # still pending, not silently dropped


@pytest.mark.asyncio
async def test_no_tier_prompt_when_already_approved():
    """work/auto-1h need only tier 1 (the default) -- must arm directly,
    no inline tier ceremony in the way."""
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.modes_crown_ui import ModesScreen

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        app.push_screen(ModesScreen())
        await pilot.pause()
        screen = app.screen

        with patch.object(screen, "_set_mode") as set_mode:
            event = type("E", (), {"button": type("B", (), {"id": "mode-auto-1h"})(), "stop": lambda self: None})()
            screen.on_button_pressed(event)

        assert screen._pending_tier_mode == ""
        set_mode.assert_called_once_with("auto-1h")
