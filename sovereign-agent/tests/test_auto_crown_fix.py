"""Tests for auto-crown-fix-d — /auto now calls set_crown_mode()
deterministically (never a natural-language directive hoping the model
calls a tool).

header-auto-desync-d (Kevin, 2026-07-25): the header's Auto/Non-auto check
used to ALSO require crown_armed() (mode_crown.json). But start_auto
(tools/auto_tools.py, which Aria may call herself) arms AutoCrownStore
directly and never writes that file — a genuinely active self-service
session always read "Non-auto". Fixed: AutoCrownStore's own session status
is now the sole ground truth, with a force-expire check for stale leases.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# ── _is_real_auto_active() — AutoCrownStore is the sole ground truth ───

@pytest.mark.asyncio
async def test_not_active_when_no_session_at_all():
    from sovereign_agent.cockpit import CockpitApp

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        with patch("sovereign_agent.auto_crown.get_auto_crown_store") as get_store:
            get_store.return_value.status.return_value = None
            assert app._is_real_auto_active() is False


@pytest.mark.asyncio
async def test_not_active_when_session_is_cancelled_or_stale():
    """Exactly Kevin's originally observed case: a crown-armed session
    whose underlying AutoCrownStore session has since been cancelled."""
    from sovereign_agent.cockpit import CockpitApp

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        stale_session = MagicMock(status="cancelled")
        with patch("sovereign_agent.auto_crown.get_auto_crown_store") as get_store:
            get_store.return_value.status.return_value = stale_session
            get_store.return_value.is_expired.return_value = False
            assert app._is_real_auto_active() is False


@pytest.mark.asyncio
async def test_active_when_session_genuinely_active_via_modes_crown():
    from sovereign_agent.cockpit import CockpitApp

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        real_session = MagicMock(status="active")
        with patch("sovereign_agent.auto_crown.get_auto_crown_store") as get_store:
            get_store.return_value.status.return_value = real_session
            get_store.return_value.is_expired.return_value = False
            assert app._is_real_auto_active() is True


@pytest.mark.asyncio
async def test_active_when_session_armed_via_self_service_start_auto():
    """The actual bug: a session armed via the start_auto TOOL (never
    writes mode_crown.json) must still read as Auto in the header."""
    from sovereign_agent.cockpit import CockpitApp

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        real_session = MagicMock(status="active")
        with patch("sovereign_agent.modes_crown.profiles.crown_armed", return_value=False), \
             patch("sovereign_agent.auto_crown.get_auto_crown_store") as get_store:
            get_store.return_value.status.return_value = real_session
            get_store.return_value.is_expired.return_value = False
            assert app._is_real_auto_active() is True


@pytest.mark.asyncio
async def test_force_expires_a_lease_past_its_deadline_before_reading_status():
    from sovereign_agent.cockpit import CockpitApp

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        with patch("sovereign_agent.auto_crown.get_auto_crown_store") as get_store:
            store = get_store.return_value
            store.is_expired.return_value = True
            store.status.return_value = MagicMock(status="expired")
            app._is_real_auto_active()
            store.expire.assert_called_once()


# ── /auto command — deterministic, direct calls ────────────────────────

@pytest.mark.asyncio
async def test_bare_auto_arms_auto_1h_directly_when_inactive():
    from sovereign_agent.cockpit import CockpitApp

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        with patch.object(app, "_is_real_auto_active", return_value=False), \
             patch("sovereign_agent.modes_crown.profiles.set_crown_mode") as set_mode:
            app._handle_auto_command("")
        set_mode.assert_called_once()
        assert set_mode.call_args.args[0] == "auto-1h"


@pytest.mark.asyncio
async def test_bare_auto_disarms_directly_when_active():
    from sovereign_agent.cockpit import CockpitApp

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        with patch.object(app, "_is_real_auto_active", return_value=True), \
             patch("sovereign_agent.modes_crown.profiles.set_crown_mode") as set_mode:
            app._handle_auto_command("")
        set_mode.assert_called_once()
        assert set_mode.call_args.args[0] == "chat"


@pytest.mark.asyncio
async def test_auto_stop_disarms_directly():
    from sovereign_agent.cockpit import CockpitApp

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        with patch("sovereign_agent.modes_crown.profiles.set_crown_mode") as set_mode:
            app._handle_auto_command("stop")
        set_mode.assert_called_once()
        assert set_mode.call_args.args[0] == "chat"


@pytest.mark.asyncio
async def test_auto_one_hour_arms_directly_no_confirmation_needed():
    from sovereign_agent.cockpit import CockpitApp

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        with patch("sovereign_agent.modes_crown.profiles.set_crown_mode") as set_mode:
            app._handle_auto_command("1")
        set_mode.assert_called_once()
        assert set_mode.call_args.args[0] == "auto-1h"
        assert set_mode.call_args.kwargs.get("confirm", "") == ""


@pytest.mark.asyncio
async def test_auto_three_hours_never_silently_arms():
    """The whole point: the 3-hour tier's typed confirmation must never
    be bypassed by this command, even though it's meant to be quick."""
    from sovereign_agent.cockpit import CockpitApp

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        with patch("sovereign_agent.modes_crown.profiles.set_crown_mode") as set_mode, \
             patch.object(app, "_write_meta") as write_meta:
            app._handle_auto_command("3")
        set_mode.assert_not_called()
        msg = write_meta.call_args.args[0]
        assert "I approve 3 hours of autonomy" in msg
        assert "F2" in msg or "/modes" in msg


@pytest.mark.asyncio
async def test_auto_command_never_dispatches_a_natural_language_directive():
    """Root cause of the original bug: _dispatch_directive depends on the
    model choosing to call a tool. None of these paths may use it."""
    from sovereign_agent.cockpit import CockpitApp

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        with patch("sovereign_agent.modes_crown.profiles.set_crown_mode"), \
             patch.object(app, "_dispatch_directive") as dispatch:
            for arg in ("", "stop", "1", "3", "status"):
                app._handle_auto_command(arg)
        dispatch.assert_not_called()


@pytest.mark.asyncio
async def test_crown_error_reported_not_silently_swallowed():
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.modes_crown.profiles import CrownError

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        with patch("sovereign_agent.modes_crown.profiles.set_crown_mode",
                  side_effect=CrownError("trust tier 1 too low")), \
             patch.object(app, "_write_meta") as write_meta:
            app._handle_auto_command("1")
        assert "trust tier 1 too low" in write_meta.call_args.args[0]
