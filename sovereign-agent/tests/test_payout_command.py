"""Tests for `/payout` — payouts-d.

Kevin, 2026-07-25: chose fully automated payouts for marketer
commissions. Covers the cockpit command dispatch: bare status (who's
owed what, or why nothing would move) and `/payout run` (mocked Stripe
Connect, off the UI thread).
"""
from __future__ import annotations

from unittest.mock import patch

import pytest


@pytest.mark.asyncio
async def test_bare_payout_shows_nothing_owed_by_default():
    from sovereign_agent.cockpit import CockpitApp

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        with patch.object(app, "_write_meta") as write_meta:
            app._handle_payout_command("")
        messages = " ".join(c.args[0] for c in write_meta.call_args_list)
        assert "no marketer has a pending balance" in messages


@pytest.mark.asyncio
async def test_bare_payout_lists_who_is_owed():
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent import referrals as rf
    from sovereign_agent.config import SETTINGS

    rf.ensure_profile(SETTINGS.paths.data_dir, "900100001")
    rf.set_marketer(SETTINGS.paths.data_dir, "900100001", on=True)
    rf.record_earning(SETTINGS.paths.data_dir, "900100001", 5000, "stripe")

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        with patch.object(app, "_write_meta") as write_meta:
            app._handle_payout_command("")
        messages = " ".join(c.args[0] for c in write_meta.call_args_list)
        assert "900100001: $50.00 pending" in messages
        assert "/payout run" in messages


@pytest.mark.asyncio
async def test_payout_run_with_no_stripe_key():
    from sovereign_agent.cockpit import CockpitApp

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        with patch("sovereign_agent.credentials.read_env", return_value={}), \
             patch.object(app, "_write_meta") as write_meta:
            app._handle_payout_command("run")
            await pilot.pause()
        messages = " ".join(c.args[0] for c in write_meta.call_args_list)
        assert "no Stripe key vaulted" in messages


@pytest.mark.asyncio
async def test_payout_run_reports_a_successful_payout():
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent import referrals as rf, payouts as po
    from sovereign_agent.config import SETTINGS

    data_dir = SETTINGS.paths.data_dir
    rf.ensure_profile(data_dir, "900100001")
    rf.set_marketer(data_dir, "900100001", on=True)
    rf.record_earning(data_dir, "900100001", 5000, "stripe")
    po._save_accounts(data_dir, {"900100001": "acct_1"})

    def fake_run_payouts(data_dir_arg, opener, key, **kwargs):
        return {"paid": [{"marketer": "900100001", "cents": 5000,
                          "transfer_id": "tr_1"}],
                "skipped": [], "total_cents": 5000, "detail": "ok"}

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        with patch("sovereign_agent.credentials.read_env",
                  return_value={"STRIPE_SECRET_KEY": "sk_test"}), \
             patch.object(po, "run_payouts", fake_run_payouts), \
             patch.object(app, "_write_meta") as write_meta:
            app._handle_payout_command("run")
            await pilot.pause()
        messages = " ".join(c.args[0] for c in write_meta.call_args_list)
        assert "1 marketer(s) paid" in messages
        assert "$50.00 total" in messages


@pytest.mark.asyncio
async def test_payout_run_reports_why_nothing_paid():
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent import payouts as po

    def fake_run_payouts(data_dir_arg, opener, key, **kwargs):
        return {"paid": [], "skipped": [{"marketer": "900100001",
                                        "reason": "no Connect account"}],
                "total_cents": 0, "detail": "ok"}

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        with patch("sovereign_agent.credentials.read_env",
                  return_value={"STRIPE_SECRET_KEY": "sk_test"}), \
             patch.object(po, "run_payouts", fake_run_payouts), \
             patch.object(app, "_write_meta") as write_meta:
            app._handle_payout_command("run")
            await pilot.pause()
        messages = " ".join(c.args[0] for c in write_meta.call_args_list)
        assert "nothing paid out" in messages
        assert "no Connect account" in messages
