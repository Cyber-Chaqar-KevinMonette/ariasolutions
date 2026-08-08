"""Tests for mid-session-add-time-d.

Kevin, 2026-07-25: "I should be able to change the hours of auto mid work
flow... without breaking anything and without stopping her from work."
AutoCrownStore.extend() only edits the stored session record -- the
running loop just reads a later deadline on its next check, so nothing
about an in-flight session is interrupted. The "+1h" button and
`/addtime [hours]` are the human-facing controls for the tool
(extend_auto) Aria already had.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


def test_auto_crown_store_extend_raises_when_nothing_active(tmp_path):
    from sovereign_agent.auto_crown import AutoCrownStore

    store = AutoCrownStore(tmp_path)
    with pytest.raises(ValueError):
        store.extend(1.0)


def test_auto_crown_store_extend_adds_time_to_a_real_session(tmp_path):
    from sovereign_agent.auto_crown import AutoCrownStore

    store = AutoCrownStore(tmp_path)
    session = store.start(duration_hours=1.0, trust_tier=1, reason="test", session_id="s1")
    original_expiry = session.expires_at

    extended = store.extend(2.0)

    assert extended.duration_hours == pytest.approx(3.0)
    assert extended.expires_at == pytest.approx(original_expiry + 2.0 * 3600)


def test_extend_trust_tier_moves_a_live_timed_elevation(tmp_path):
    """add-time-tier-sync-d: the elevated tier has its OWN countdown,
    separate from the auto session's -- extend_trust_tier() must move it
    too, or +1h silently leaves the tier to expire on the old schedule."""
    from sovereign_agent.auto_crown import AutoCrownStore

    store = AutoCrownStore(tmp_path)
    store.set_trust_tier(3, expires_in_hours=2.0)
    original_remaining = store.trust_tier_remaining_seconds()

    moved = store.extend_trust_tier(1.0)

    assert moved is True
    new_remaining = store.trust_tier_remaining_seconds()
    assert new_remaining == pytest.approx(original_remaining + 3600, abs=2)


def test_extend_trust_tier_is_a_noop_at_baseline_tier_1(tmp_path):
    from sovereign_agent.auto_crown import AutoCrownStore

    store = AutoCrownStore(tmp_path)
    # tier 1 is the permanent baseline -- nothing timed to extend
    assert store.extend_trust_tier(1.0) is False


def test_extend_trust_tier_is_a_noop_for_an_untimed_elevation(tmp_path):
    from sovereign_agent.auto_crown import AutoCrownStore

    store = AutoCrownStore(tmp_path)
    store.set_trust_tier(3, expires_in_hours=0)  # explicit "never expires"
    assert store.extend_trust_tier(1.0) is False


def test_extend_trust_tier_is_a_noop_when_no_trust_file_exists(tmp_path):
    from sovereign_agent.auto_crown import AutoCrownStore

    store = AutoCrownStore(tmp_path)
    assert store.extend_trust_tier(1.0) is False


@pytest.mark.asyncio
async def test_add_time_button_calls_extend_and_reports_remaining():
    from sovereign_agent.cockpit import CockpitApp

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        fake_session = MagicMock()
        fake_session.remaining_minutes.return_value = 125.0
        with patch("sovereign_agent.auto_crown.get_auto_crown_store") as get_store, \
             patch.object(app, "_write_meta") as write_meta:
            get_store.return_value.extend.return_value = fake_session
            app._handle_add_time(1.0)

        get_store.return_value.extend.assert_called_once_with(1.0)
        get_store.return_value.extend_trust_tier.assert_called_once_with(1.0)
        messages = " ".join(c.args[0] for c in write_meta.call_args_list)
        assert "+1h added" in messages
        assert "2h05m" in messages


@pytest.mark.asyncio
async def test_add_time_notes_when_an_elevated_tier_was_extended_too():
    from sovereign_agent.cockpit import CockpitApp

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        fake_session = MagicMock()
        fake_session.remaining_minutes.return_value = 60.0
        with patch("sovereign_agent.auto_crown.get_auto_crown_store") as get_store, \
             patch.object(app, "_write_meta") as write_meta:
            get_store.return_value.extend.return_value = fake_session
            get_store.return_value.extend_trust_tier.return_value = True
            app._handle_add_time(1.0)

        messages = " ".join(c.args[0] for c in write_meta.call_args_list)
        assert "elevated tier extended too" in messages


@pytest.mark.asyncio
async def test_add_time_omits_tier_note_when_no_tier_was_extended():
    from sovereign_agent.cockpit import CockpitApp

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        fake_session = MagicMock()
        fake_session.remaining_minutes.return_value = 60.0
        with patch("sovereign_agent.auto_crown.get_auto_crown_store") as get_store, \
             patch.object(app, "_write_meta") as write_meta:
            get_store.return_value.extend.return_value = fake_session
            get_store.return_value.extend_trust_tier.return_value = False
            app._handle_add_time(1.0)

        messages = " ".join(c.args[0] for c in write_meta.call_args_list)
        assert "elevated tier extended too" not in messages


@pytest.mark.asyncio
async def test_add_time_with_nothing_armed_gives_a_clear_message_not_a_crash():
    from sovereign_agent.cockpit import CockpitApp

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        with patch("sovereign_agent.auto_crown.get_auto_crown_store") as get_store, \
             patch.object(app, "_write_meta") as write_meta:
            get_store.return_value.extend.side_effect = ValueError("no active auto session to extend")
            app._handle_add_time(1.0)

        messages = " ".join(c.args[0] for c in write_meta.call_args_list)
        assert "no active auto session" in messages


@pytest.mark.asyncio
async def test_addtime_command_defaults_to_one_hour():
    from sovereign_agent.cockpit import CockpitApp

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        with patch.object(app, "_handle_add_time") as handler:
            app._handle_slash("/addtime")
        handler.assert_called_once_with(1.0)


@pytest.mark.asyncio
async def test_addtime_command_accepts_an_explicit_value():
    from sovereign_agent.cockpit import CockpitApp

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        with patch.object(app, "_handle_add_time") as handler:
            app._handle_slash("/addtime 3")
        handler.assert_called_once_with(3.0)


@pytest.mark.asyncio
async def test_addtime_command_rejects_garbage_without_crashing():
    from sovereign_agent.cockpit import CockpitApp

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        with patch.object(app, "_handle_add_time") as handler:
            app._handle_slash("/addtime banana")
        handler.assert_not_called()


@pytest.mark.asyncio
async def test_add_time_button_click_triggers_the_handler():
    from sovereign_agent.cockpit import CockpitApp

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        with patch.object(app, "_handle_add_time") as handler:
            await pilot.click("#add-time-btn")
        handler.assert_called_once_with(1.0)
