"""Tests for header-reorg-d (Kevin, 2026-08-02): "all the most important
should be immediately present, and whatever can come after." The header
row went from 17 always-visible controls down to 9 + the gear icon; 6
moved into the existing ⋮ commands popup; My Inbox was removed entirely.
(game-pane-toggle-btn was added right after, for the new Game Studio
pane -- a distinct button from game-toggle-btn, which toggles an
unrelated stats display -- bringing the row to 10.)
"""
from __future__ import annotations

import pytest


_ALWAYS_VISIBLE = (
    "palette-menu-btn", "quick-view-btn", "layout-cycle-btn",
    "session-setup-btn", "add-time-btn",
    "game-toggle-btn", "movie-toggle-btn", "screen-toggle-btn",
    "game-pane-toggle-btn", "bots-toggle-btn",
)
_REMOVED_FROM_HEADER = (
    "discord-control-btn", "suggestions-btn", "task-guide-btn",
    "stripe-links-btn", "sources-control-btn", "instructions-btn",
    "my-inbox-btn",
)
_MOVED_TO_POPUP = (
    "discord-control", "suggestions", "task-guide",
    "stripe-links", "sources-control",
)


@pytest.mark.asyncio
async def test_exactly_nine_always_visible_header_buttons():
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.app import MenuTriggerButton

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        row = app.query_one("#palette-row")
        trigger_ids = {b.id for b in row.query(MenuTriggerButton)}
        assert trigger_ids == set(_ALWAYS_VISIBLE)


@pytest.mark.asyncio
async def test_removed_buttons_are_gone_from_the_header():
    from sovereign_agent.cockpit import CockpitApp

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        for bid in _REMOVED_FROM_HEADER:
            assert len(app.query(f"#{bid}")) == 0, bid


def test_moved_actions_are_reachable_in_the_popup():
    from sovereign_agent.cockpit.app import REFERENCE_BUTTONS

    actions = {c.action for c in REFERENCE_BUTTONS}
    for action in _MOVED_TO_POPUP:
        assert action in actions, action


def test_no_duplicate_action_keys_in_reference_buttons():
    from sovereign_agent.cockpit.app import REFERENCE_BUTTONS

    actions = [c.action for c in REFERENCE_BUTTONS]
    assert len(actions) == len(set(actions))


@pytest.mark.asyncio
async def test_my_inbox_is_fully_removed():
    from sovereign_agent.cockpit import CockpitApp

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        assert not hasattr(app, "action_my_inbox")
        app._handle_slash("/my-inbox")
        await pilot.pause()
        # unrecognized verb: no screen pushed, cockpit stays on the base screen
        assert type(app.screen).__name__ != "MyInboxScreen"


@pytest.mark.asyncio
async def test_moved_actions_still_open_their_real_screens():
    """The point of moving these isn't losing them -- confirm the actual
    underlying action still works, called the same way the popup's
    CommandButton click handler calls it (cmd.action dispatch)."""
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.discord_control_screen import DiscordControlScreen
    from sovereign_agent.cockpit.sources_control_screen import SourcesControlScreen

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        app.action_discord_control()
        await pilot.pause()
        assert isinstance(app.screen, DiscordControlScreen)
        app.pop_screen()
        await pilot.pause()

        app.action_sources_control()
        await pilot.pause()
        assert isinstance(app.screen, SourcesControlScreen)
