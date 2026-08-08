"""Tests for game-window-d — the consolidated gamification window.

Kevin, 2026-07-25: "remove the container above the command button... it
is broken... add the gamification window instead — live score, token
metrics if we can get any working, special effects and animations, as
long as they stay glyph safe." Verifies: the progress bar renders from
real xp state, the flash effect only fires on a genuinely NEW event (never
every 8s poll of the same one), every bar/effect character is a vetted-
safe glyph, and the verified-income line shows up correctly.
"""
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_progress_bar_reflects_real_xp_state(tmp_path, monkeypatch):
    from sovereign_agent.cockpit import CockpitApp
    import sovereign_agent.aria_xp as aria_xp

    monkeypatch.setattr(aria_xp, "total_xp", lambda data_dir=None: 125)  # half of level 1 (250)

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        app._refresh_game_window()
        await pilot.pause()
        window = app.query_one("#game-window")
        text = str(window.render())
        assert "Lv1" in text
        assert "125xp" in text
        # half-full bar: 10 filled (▪) + 10 empty (·) of a 20-wide bar
        assert "▪" * 10 in text
        assert "·" * 10 in text


@pytest.mark.asyncio
async def test_flash_fires_only_on_a_genuinely_new_event(monkeypatch):
    from sovereign_agent.cockpit import CockpitApp
    import sovereign_agent.aria_xp as aria_xp
    from dataclasses import dataclass

    @dataclass
    class _Ev:
        event_type: str
        xp: int
        ts: float

    monkeypatch.setattr(aria_xp, "total_xp", lambda data_dir=None: 10)
    monkeypatch.setattr(aria_xp, "level_for_xp", lambda xp: 1)
    monkeypatch.setattr(aria_xp, "progress_to_next", lambda xp: (10, 250))

    events = [_Ev("task_success", 10, ts=1000.0)]
    monkeypatch.setattr(aria_xp, "recent_events", lambda n=1, data_dir=None: events)

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        window = app.query_one("#game-window")

        # First read after mount: establishes the baseline, no flash (Kevin
        # shouldn't see a pulse just because the cockpit started up).
        app._refresh_game_window()
        await pilot.pause()
        assert "flash" not in window.classes

        # Same event again (e.g. the next 8s poll): still no flash.
        app._refresh_game_window()
        await pilot.pause()
        assert "flash" not in window.classes

        # A genuinely NEW event lands: flash fires.
        events[0] = _Ev("task_success", 10, ts=2000.0)
        app._refresh_game_window()
        await pilot.pause()
        assert "flash" in window.classes


def test_game_window_bar_glyphs_are_all_vetted_safe():
    """Kevin: "as long as they stay glyph safe." The progress bar and the
    window's own brand glyph must only ever use characters glyphs.py has
    already vetted as one-terminal-cell-safe."""
    from sovereign_agent import glyphs as g

    for ch in ("▪", "·", "◊"):
        assert g.is_cataloged(ch) or not g.audit_string(ch), f"{ch!r} not vetted safe"
        assert not g.is_emoji_risk(ch), f"{ch!r} flagged emoji-risk"


@pytest.mark.asyncio
async def test_income_line_shows_no_verified_income_by_default():
    from sovereign_agent.cockpit import CockpitApp

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        app._refresh_game_window()
        await pilot.pause()
        window = app.query_one("#game-window")
        text = str(window.render())
        assert "no verified income yet" in text


@pytest.mark.asyncio
async def test_income_line_shows_a_real_verified_total(tmp_path, monkeypatch):
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent import income_ledger

    monkeypatch.setattr(income_ledger, "total_income_cents", lambda data_dir=None: 3000)

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        app._refresh_game_window()
        await pilot.pause()
        window = app.query_one("#game-window")
        text = str(window.render())
        assert "$30.00 earned" in text


@pytest.mark.asyncio
async def test_game_window_css_has_a_distinct_flash_effect():
    from sovereign_agent.cockpit.app import CockpitApp

    css = CockpitApp.CSS
    assert ".game-window.flash {" in css


# ── game-window-position-d / -ripple-d / -optional-d ────────────────────────
@pytest.mark.asyncio
async def test_game_window_renders_above_the_panes():
    """Kevin, 2026-07-25: "add the game menu above the other windows. And
    so everything that came before stays together." The panes group
    (#main) must not be split by the game window."""
    from sovereign_agent.cockpit import CockpitApp

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        window = app.query_one("#game-window")
        main = app.query_one("#main")
        assert window.region.y < main.region.y


@pytest.mark.asyncio
async def test_game_window_is_a_ripple_static():
    """Kevin: "make the game menu ripple like everything else." """
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.app import RippleStatic

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        window = app.query_one("#game-window")
        assert isinstance(window, RippleStatic)


@pytest.mark.asyncio
async def test_game_window_visible_by_default():
    from sovereign_agent.cockpit import CockpitApp

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        window = app.query_one("#game-window")
        assert window.display is True


@pytest.mark.asyncio
async def test_game_toggle_button_hides_and_shows_the_window():
    from sovereign_agent.cockpit import CockpitApp

    async with CockpitApp().run_test(size=(220, 50)) as pilot:
        app = pilot.app
        window = app.query_one("#game-window")
        assert window.display is True

        await pilot.click("#game-toggle-btn")
        await pilot.pause()
        assert window.display is False

        await pilot.click("#game-toggle-btn")
        await pilot.pause()
        assert window.display is True


@pytest.mark.asyncio
async def test_game_toggle_persists_across_a_fresh_mount(tmp_path, monkeypatch):
    from sovereign_agent.config import SETTINGS
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.game_window_pref import is_visible

    async with CockpitApp().run_test(size=(220, 50)) as pilot:
        app = pilot.app
        await pilot.click("#game-toggle-btn")
        await pilot.pause()
        assert is_visible(SETTINGS.paths.data_dir) is False

    # a fresh cockpit mount honors the persisted choice
    async with CockpitApp().run_test() as pilot2:
        app2 = pilot2.app
        window2 = app2.query_one("#game-window")
        assert window2.display is False


@pytest.mark.asyncio
async def test_game_toggle_command_alias_also_works():
    from sovereign_agent.cockpit import CockpitApp

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        window = app.query_one("#game-window")
        assert window.display is True
        app._handle_slash("/game-toggle")
        await pilot.pause()
        assert window.display is False
