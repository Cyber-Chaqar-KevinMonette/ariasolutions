"""Tests for header-status-v2-d — Auto/Semi-Auto top-level + real-flag-
grounded sub-modes (Thinking/Planning/Researching/Building) next to the
theme name in the cockpit header's sub_title. Supersedes
test_header_status.py's Planning/Thinking/Auto scheme."""
from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _reset_run_state():
    """_RUN_STATE is a module-level singleton — isolate each test."""
    from sovereign_agent.cockpit.app import _RUN_STATE
    saved = (_RUN_STATE.active, _RUN_STATE.goal, _RUN_STATE.current_subtask,
             _RUN_STATE.last_flag)
    _RUN_STATE.active = False
    _RUN_STATE.goal = ""
    _RUN_STATE.current_subtask = ""
    _RUN_STATE.last_flag = ""
    yield
    (_RUN_STATE.active, _RUN_STATE.goal, _RUN_STATE.current_subtask,
     _RUN_STATE.last_flag) = saved


def _mock_store(active_session=None, tier=1):
    store = MagicMock()
    store.get_max_trust_tier.return_value = tier
    store.trust_tier_remaining_seconds.return_value = 0  # tier-expiry-d
    store.status.return_value = active_session
    return store


def _active_session(tier=3):
    return MagicMock(status="active", trust_tier=tier)


@pytest.mark.asyncio
async def test_semi_auto_idle_shows_no_submode():
    from sovereign_agent.cockpit import CockpitApp

    with patch("sovereign_agent.auto_crown.get_auto_crown_store",
              return_value=_mock_store(active_session=None, tier=1)):
        async with CockpitApp().run_test() as pilot:
            app = pilot.app
            app._refresh_sub_title()
            assert "Semi-Auto" in app.sub_title
            assert ":" not in app.sub_title.split("Semi-Auto", 1)[1]  # no sub-mode suffix
            assert "T1" in app.sub_title


@pytest.mark.asyncio
async def test_auto_idle_shows_auto_alone():
    """auto_active now comes from the combined crown+session check
    (_is_real_auto_active) added by auto-crown-fix-d, not raw
    AutoCrownStore alone — mocked directly here, its own logic is
    covered by test_auto_crown_fix.py."""
    from sovereign_agent.cockpit import CockpitApp

    with patch("sovereign_agent.auto_crown.get_auto_crown_store",
              return_value=_mock_store(active_session=_active_session(), tier=3)):
        async with CockpitApp().run_test() as pilot:
            app = pilot.app
            with patch.object(app, "_is_real_auto_active", return_value=True):
                app._refresh_sub_title()
            assert "Auto" in app.sub_title
            assert "Semi-Auto" not in app.sub_title


@pytest.mark.asyncio
async def test_semi_auto_thinking_fallback():
    """Active run, no specific flag matched -> honest fallback, not a guess."""
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.app import _RUN_STATE

    _RUN_STATE.active = True
    _RUN_STATE.last_flag = "token-usage-d"
    _RUN_STATE.goal = "some ongoing task"
    with patch("sovereign_agent.auto_crown.get_auto_crown_store",
              return_value=_mock_store(active_session=None, tier=1)):
        async with CockpitApp().run_test() as pilot:
            app = pilot.app
            app._refresh_sub_title()
            assert "Semi-Auto: Thinking" in app.sub_title


@pytest.mark.asyncio
async def test_auto_researching_from_qa_flag():
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.app import _RUN_STATE

    _RUN_STATE.active = True
    _RUN_STATE.last_flag = "qa-start-d"
    _RUN_STATE.goal = "is Steam or itch.io better for a first release"
    with patch("sovereign_agent.auto_crown.get_auto_crown_store",
              return_value=_mock_store(active_session=_active_session(), tier=3)):
        async with CockpitApp().run_test() as pilot:
            app = pilot.app
            with patch.object(app, "_is_real_auto_active", return_value=True):
                app._refresh_sub_title()
            assert "Auto: Researching" in app.sub_title


@pytest.mark.asyncio
async def test_auto_planning_from_workflow_designed_flag():
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.app import _RUN_STATE

    _RUN_STATE.active = True
    _RUN_STATE.last_flag = "workflow-designed-d"
    with patch("sovereign_agent.auto_crown.get_auto_crown_store",
              return_value=_mock_store(active_session=_active_session(), tier=3)):
        async with CockpitApp().run_test() as pilot:
            app = pilot.app
            with patch.object(app, "_is_real_auto_active", return_value=True):
                app._refresh_sub_title()
            assert "Auto: Planning" in app.sub_title


@pytest.mark.asyncio
async def test_auto_building_from_subtask_flags():
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.app import _RUN_STATE

    for flag in ("subtask-start-d", "subtask-done-d",
                "workflow-step-start-d", "workflow-step-done-d"):
        _RUN_STATE.active = True
        _RUN_STATE.last_flag = flag
        with patch("sovereign_agent.auto_crown.get_auto_crown_store",
                  return_value=_mock_store(active_session=_active_session(), tier=3)):
            async with CockpitApp().run_test() as pilot:
                app = pilot.app
                with patch.object(app, "_is_real_auto_active", return_value=True):
                    app._refresh_sub_title()
                assert "Auto: Building" in app.sub_title, f"failed for flag={flag}"


@pytest.mark.asyncio
async def test_activity_fragment_appended_when_present():
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.app import _RUN_STATE

    _RUN_STATE.active = True
    _RUN_STATE.last_flag = "subtask-start-d"
    _RUN_STATE.current_subtask = "wire the export presets"
    with patch("sovereign_agent.auto_crown.get_auto_crown_store",
              return_value=_mock_store(active_session=_active_session(), tier=3)):
        async with CockpitApp().run_test() as pilot:
            app = pilot.app
            with patch.object(app, "_is_real_auto_active", return_value=True):
                app._refresh_sub_title()
            assert "Auto: Building: wire the export presets" in app.sub_title


@pytest.mark.asyncio
async def test_tier_shown_regardless_of_top_mode():
    from sovereign_agent.cockpit import CockpitApp

    with patch("sovereign_agent.auto_crown.get_auto_crown_store",
              return_value=_mock_store(active_session=None, tier=4)):
        async with CockpitApp().run_test() as pilot:
            app = pilot.app
            app._refresh_sub_title()
            assert "T4" in app.sub_title


@pytest.mark.asyncio
async def test_degrades_gracefully_if_auto_crown_unavailable():
    from sovereign_agent.cockpit import CockpitApp

    with patch("sovereign_agent.auto_crown.get_auto_crown_store",
              side_effect=RuntimeError("boom")):
        async with CockpitApp().run_test() as pilot:
            app = pilot.app
            app._refresh_sub_title()  # must not raise
            assert app.sub_title


@pytest.mark.asyncio
async def test_arming_via_f2_modes_screen_refreshes_the_header_immediately():
    """Kevin, 2026-07-21: "it kicked me out of auto mode... I mean in
    the header." Root cause: ModesScreen._set_mode() (F2's arm path)
    changed the real crown state correctly but never force-refreshed the
    header the way /auto already did -- the header only caught up on the
    next periodic tick, showing stale "Non-auto" in between and looking
    exactly like a kick-out that never actually happened."""
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.modes_crown_ui import ModesScreen

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        assert "Semi-Auto" in app.sub_title  # baseline: nothing armed yet

        app.push_screen(ModesScreen())
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, ModesScreen)
        screen._set_mode("auto-1h")
        await pilot.pause()

        # The header must already say Auto -- not "eventually", not on
        # the next 8s tick, but the instant arming happened.
        assert "Auto" in app.sub_title
        assert "Semi-Auto" not in app.sub_title
