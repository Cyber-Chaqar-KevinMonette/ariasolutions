"""UI smoke tests for the Shop Studio (real cockpit, isolated tmp data dir)."""
from __future__ import annotations

import pytest

from sovereign_agent.cockpit.shop_studio_screen import _dollars, _to_cents, cycle_index


# ── pure helpers ────────────────────────────────────────────────────────────
def test_cycle_index_wraps():
    assert cycle_index(0, 3, -1) == 2
    assert cycle_index(2, 3, 1) == 0
    assert cycle_index(0, 0, 1) == 0


def test_dollar_cents_round_trip():
    assert _to_cents("8") == 800
    assert _to_cents("$12.50") == 1250
    assert _to_cents("") == 0
    assert _dollars(800) == "8"
    assert _dollars(1250) == "12.5"
    assert _dollars(0) == ""


# ── UI smoke ────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_shop_studio_opens_and_saves(tmp_path_factory):
    from textual.widgets import Button, Input

    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.app import ShopStudioScreen
    from sovereign_agent.config import SETTINGS
    from sovereign_agent.shop import load

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        app.action_shop_studio()
        await pilot.pause()
        assert isinstance(app.screen, ShopStudioScreen)
        app.screen.query_one("#shop-name", Input).value = "Restock Alert Bot"
        app.screen.query_one("#shop-price", Input).value = "8"
        app.screen.query_one("#shop-setup", Input).value = "30"
        await pilot.click(app.screen.query_one("#shop-save-btn", Button))
        await pilot.pause()
        saved = load("Restock Alert Bot", SETTINGS.paths.data_dir)
        assert saved is not None
        assert saved.price_cents == 800 and saved.setup_cents == 3000


@pytest.mark.asyncio
async def test_shop_studio_seed_and_carousel(tmp_path_factory):
    from textual.widgets import Button

    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.app import ShopStudioScreen

    async with CockpitApp().run_test(size=(120, 60)) as pilot:
        app = pilot.app
        app.action_shop_studio()
        await pilot.pause()
        assert isinstance(app.screen, ShopStudioScreen)
        seed = app.screen.query_one("#shop-seed", Button)
        seed.scroll_visible(animate=False)
        await pilot.pause()
        await pilot.click(seed)
        await pilot.pause()
        assert len(app.screen._products) == 10   # starter catalog seeded
        assert app.screen._pi == 0
        nxt = app.screen.query_one("#shop-next", Button)
        nxt.scroll_visible(animate=False)
        await pilot.pause()
        await pilot.click(nxt)
        await pilot.pause()
        assert app.screen._pi == 1


@pytest.mark.asyncio
async def test_shop_studio_publish_is_dry_run(tmp_path_factory):
    from textual.widgets import Button

    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.app import ShopStudioScreen
    from sovereign_agent.config import SETTINGS
    from sovereign_agent.shop import seed_starter_catalog

    seed_starter_catalog(SETTINGS.paths.data_dir)
    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        app.action_shop_studio()
        await pilot.pause()
        screen = app.screen
        await pilot.click(screen.query_one("#shop-publish-btn", Button))
        await pilot.pause()
        # publish from the cockpit is dry-run — nothing sent, no crash, still open
        assert isinstance(app.screen, ShopStudioScreen)
        # and prove the underlying publish path is dry-run
        from sovereign_agent.shop import publish_storefront
        r = publish_storefront(SETTINGS.paths.data_dir, live=False)
        assert r.dry_run and not r.sent
