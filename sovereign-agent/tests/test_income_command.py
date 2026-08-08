"""Tests for `/income` — income-ledger-d + affiliate-links-d.

Kevin, 2026-07-25: "make income earned a real metric too, but only
updates on verified income received." Covers the cockpit command
dispatch itself (previously untested at this level): bare status,
`/income sync` (Stripe), and `/income record amazon <dollars> [note]` —
the manual verified-entry path for Amazon Associates payouts, since
Amazon exposes no public API for reading commission reports.

`SETTINGS.paths.data_dir` is already redirected to an isolated tmp dir by
the autouse `isolated_paths` fixture (conftest.py) — no per-test override
needed; `_handle_income_command`'s internal calls default to that same
data_dir, so seeding through it lines up automatically.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest


@pytest.mark.asyncio
async def test_bare_income_shows_the_current_total():
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.config import SETTINGS
    from sovereign_agent.income_ledger import record_income
    record_income("ch_1", 2500, data_dir=SETTINGS.paths.data_dir)

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        with patch.object(app, "_write_meta") as write_meta:
            app._handle_income_command("")
        messages = " ".join(c.args[0] for c in write_meta.call_args_list)
        assert "$ 25.00 verified income" in messages


@pytest.mark.asyncio
async def test_income_record_amazon_records_a_verified_entry():
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.config import SETTINGS

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        with patch.object(app, "_write_meta") as write_meta:
            app._handle_income_command("record amazon 42.50 July payout")
        messages = " ".join(c.args[0] for c in write_meta.call_args_list)
        assert "recorded $42.50" in messages

        from sovereign_agent.income_ledger import recent_events, total_income_cents
        assert total_income_cents(SETTINGS.paths.data_dir) == 4250
        events = recent_events(data_dir=SETTINGS.paths.data_dir)
        assert events[0].source == "amazon-associates"
        assert events[0].note == "July payout"


@pytest.mark.asyncio
async def test_income_record_amazon_without_note():
    from sovereign_agent.cockpit import CockpitApp

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        with patch.object(app, "_write_meta") as write_meta:
            app._handle_income_command("record amazon 10")
        messages = " ".join(c.args[0] for c in write_meta.call_args_list)
        assert "recorded $10.00" in messages


@pytest.mark.asyncio
async def test_income_record_rejects_bad_usage():
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.config import SETTINGS

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        for bad in ("record", "record amazon", "record amazon notanumber",
                   "record amazon -5", "record ebay 10"):
            with patch.object(app, "_write_meta") as write_meta:
                app._handle_income_command(bad)
            messages = " ".join(c.args[0] for c in write_meta.call_args_list)
            assert "usage: /income record amazon" in messages, bad

        from sovereign_agent.income_ledger import total_income_cents
        assert total_income_cents(SETTINGS.paths.data_dir) == 0  # nothing bad recorded


@pytest.mark.asyncio
async def test_income_sync_still_works_after_the_record_branch_was_added():
    from sovereign_agent.cockpit import CockpitApp

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        with patch("sovereign_agent.credentials.read_env", return_value={}), \
             patch.object(app, "_write_meta") as write_meta:
            app._handle_income_command("sync")
            await pilot.pause()
        messages = " ".join(c.args[0] for c in write_meta.call_args_list)
        assert "no Stripe key vaulted" in messages
