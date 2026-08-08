"""Tests for aria-xp-live-d — the cockpit-side wiring: the always-visible
xp display (now the #game-window, per game-window-d, 2026-07-25 — folded
in from the old standalone xp-strip), and objective tool-call-shaped
events auto-awarding XP.
"""
from __future__ import annotations

import json

import pytest


@pytest.mark.asyncio
async def test_game_window_shows_level_and_total():
    from sovereign_agent.cockpit import CockpitApp

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        app._refresh_game_window()
        await pilot.pause()

        window = app.query_one("#game-window")
        text = str(window.render())
        assert "xp" in text.lower()
        assert "Lv" in text


@pytest.mark.asyncio
async def test_memory_write_tool_event_auto_awards_xp():
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent import aria_xp
    from unittest.mock import patch

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        awarded = []
        with patch("sovereign_agent.aria_xp.award",
                  side_effect=lambda *a, **k: awarded.append((a, k))):
            raw = json.dumps({
                "ts": "2026-07-25T00:00:00Z", "flag": "tool-start-d",
                "payload": {"tool": "memory_write", "tier": 1},
            })
            app._render_event(raw)

        assert awarded
        assert awarded[0][0][0] == "memory_written"


@pytest.mark.asyncio
async def test_write_behavior_pattern_awards_pattern_recognized():
    from sovereign_agent.cockpit import CockpitApp
    from unittest.mock import patch

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        awarded = []
        with patch("sovereign_agent.aria_xp.award",
                  side_effect=lambda *a, **k: awarded.append(a[0])):
            raw = json.dumps({
                "ts": "2026-07-25T00:00:00Z", "flag": "tool-start-d",
                "payload": {"tool": "write_behavior_pattern", "tier": 1},
            })
            app._render_event(raw)

        assert awarded == ["pattern_recognized"]


@pytest.mark.asyncio
async def test_read_behavior_patterns_awards_pattern_recalled():
    from sovereign_agent.cockpit import CockpitApp
    from unittest.mock import patch

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        awarded = []
        with patch("sovereign_agent.aria_xp.award",
                  side_effect=lambda *a, **k: awarded.append(a[0])):
            raw = json.dumps({
                "ts": "2026-07-25T00:00:00Z", "flag": "tool-start-d",
                "payload": {"tool": "read_behavior_patterns", "tier": 0},
            })
            app._render_event(raw)

        assert awarded == ["pattern_recalled"]


@pytest.mark.asyncio
async def test_unrelated_tool_never_awards_xp():
    from sovereign_agent.cockpit import CockpitApp
    from unittest.mock import patch

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        with patch("sovereign_agent.aria_xp.award") as award:
            raw = json.dumps({
                "ts": "2026-07-25T00:00:00Z", "flag": "tool-start-d",
                "payload": {"tool": "read_session", "tier": 0},
            })
            app._render_event(raw)

        award.assert_not_called()


@pytest.mark.asyncio
async def test_game_window_survives_a_ledger_read_failure():
    from sovereign_agent.cockpit import CockpitApp
    from unittest.mock import patch

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        # Assert INSIDE the patch context -- a periodic strip-refresh
        # timer can otherwise fire after unpatching and overwrite the
        # widget with a real, successful render before the check runs.
        with patch("sovereign_agent.aria_xp.total_xp", side_effect=RuntimeError("boom")):
            app._refresh_game_window()  # must not raise
            window = app.query_one("#game-window")
            assert "unavailable" in str(window.render())
