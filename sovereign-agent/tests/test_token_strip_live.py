"""Tests for strip-min-width-d / token-speed metrics end-to-end liveness.

Kevin, 2026-07-25: "I don't see the token speed or usage anywhere," and
later "remove the container above the command button... it is broken...
add the gamification window instead." game-window-d folded the broken
standalone token strip into the new #game-window (which also carries
level/xp/progress + the most recent event) -- the token data path itself
(_render_event -> _RUN_STATE.ingest -> _refresh_game_window) was never
broken; what's verified here: (1) a real token-usage-d event does update
the visible window text; (2) #palette-row's remaining strips still have a
real min-width + horizontal scroll instead of silent squeezing; (3) every
strip (including the game window) has a real, distinct background so a
correctly-updating widget can't read as an empty box at a glance.
"""
from __future__ import annotations

import json

import pytest


@pytest.mark.asyncio
async def test_a_real_token_usage_event_updates_the_visible_window_text():
    from sovereign_agent.cockpit import CockpitApp

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        raw = json.dumps({
            "ts": "2026-07-25T00:00:00Z", "flag": "token-usage-d",
            "payload": {"prompt_tokens": 100, "completion_tokens": 50,
                       "running_total": 4500, "model": "test-model", "tok_s": 12.34},
        })
        app._render_event(raw)
        app._refresh_game_window()
        await pilot.pause()

        window = app.query_one("#game-window")
        text = str(window.render())
        assert "12.3 tok/s" in text
        assert "4500t session" in text


@pytest.mark.asyncio
async def test_game_window_shows_a_real_placeholder_not_blank_before_any_run():
    from sovereign_agent.cockpit import CockpitApp

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        app._refresh_game_window()
        await pilot.pause()

        window = app.query_one("#game-window")
        text = str(window.render())
        assert text.strip() != ""
        assert "game" in text.lower()


def test_cockpit_strip_has_a_real_readable_minimum_width():
    """Enough characters for '12.3 tok/s · 4500t session' -- the exact
    text this strip renders -- not just a fraction of whatever's left
    after 5 buttons + 5 sibling strips."""
    from sovereign_agent.cockpit.app import CockpitApp

    css = CockpitApp.CSS
    assert "min-width: 18" in css


def test_palette_row_scrolls_instead_of_squeezing_strips_illegible():
    from sovereign_agent.cockpit.app import CockpitApp

    css = CockpitApp.CSS
    row_start = css.index("#palette-row {")
    row_block = css[row_start:row_start + 900]
    assert "overflow-x: auto" in row_block


def test_strips_have_a_real_distinct_background_not_just_surface():
    """strip-contrast-d (Kevin, 2026-07-25): "that huge section is wasted
    space... the token counter... still is not showing." A strip with
    NO explicit background inherits the same $surface as everything
    around it -- correctly-updating text can still read as an empty box
    at a glance. Every strip class (including the game window) must set
    a real, distinct background so it visually pops as its own element."""
    from sovereign_agent.cockpit.app import CockpitApp

    css = CockpitApp.CSS
    for cls in (".cockpit-strip {", ".game-window {"):
        start = css.index(cls)
        block = css[start:css.index("}", start)]
        assert "background: $panel" in block, f"{cls} has no distinct background"
