"""UI smoke for the Stripe Links Vault screen.

stripe-links-d (Kevin, 2026-07-26): "add a button and menu for stripe
control panel inside the cockpit front end so I can see all the current
stripe links, and just configuation slots for stripe links so I can
update them easily via the cockpit <3 like a stripe links vault."
"""
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_screen_lists_every_product_and_shows_the_current_link():
    from textual.widgets import Select, Static

    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.app import StripeLinksScreen
    from sovereign_agent.config import SETTINGS
    from sovereign_agent.shop import Product, save

    save(Product(name="Pro", billing="monthly", price_cents=1200,
                 stripe_url="https://buy.stripe.com/pro"), SETTINGS.paths.data_dir)
    save(Product(name="Basic", billing="monthly", price_cents=500),
         SETTINGS.paths.data_dir)

    async with CockpitApp().run_test(size=(120, 60)) as pilot:
        app = pilot.app
        app.action_stripe_links()
        await pilot.pause()
        assert isinstance(app.screen, StripeLinksScreen)
        status = str(app.screen.query_one("#sl-status", Static).render())
        assert "Pro" in status and "https://buy.stripe.com/pro" in status
        assert "Basic" in status
        assert "1/2 product(s)" in status


@pytest.mark.asyncio
async def test_saving_a_new_link_writes_it_back_to_the_product():
    from textual.widgets import Button, Input, Select

    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.app import StripeLinksScreen
    from sovereign_agent.config import SETTINGS
    from sovereign_agent.shop import Product, load, save

    save(Product(name="VIP", billing="monthly", price_cents=2500),
         SETTINGS.paths.data_dir)

    async with CockpitApp().run_test(size=(120, 60)) as pilot:
        app = pilot.app
        app.action_stripe_links()
        await pilot.pause()
        assert isinstance(app.screen, StripeLinksScreen)
        app.screen.query_one("#sl-which", Select).value = "VIP"
        await pilot.pause()
        value = app.screen.query_one("#sl-value", Input)
        value.value = "https://buy.stripe.com/vip-new-link"
        await pilot.click(app.screen.query_one("#sl-save-btn", Button))
        await pilot.pause()

        product = load("VIP", SETTINGS.paths.data_dir)
        assert product.stripe_url == "https://buy.stripe.com/vip-new-link"


@pytest.mark.asyncio
async def test_a_non_url_value_is_rejected_and_nothing_is_saved():
    from textual.widgets import Button, Input, Select, Static

    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.app import StripeLinksScreen
    from sovereign_agent.config import SETTINGS
    from sovereign_agent.shop import Product, load, save

    save(Product(name="Basic", billing="monthly", price_cents=500),
         SETTINGS.paths.data_dir)

    async with CockpitApp().run_test(size=(120, 60)) as pilot:
        app = pilot.app
        app.action_stripe_links()
        await pilot.pause()
        assert isinstance(app.screen, StripeLinksScreen)
        app.screen.query_one("#sl-which", Select).value = "Basic"
        await pilot.pause()
        app.screen.query_one("#sl-value", Input).value = "not-a-url"
        await pilot.click(app.screen.query_one("#sl-save-btn", Button))
        await pilot.pause()

        assert load("Basic", SETTINGS.paths.data_dir).stripe_url == ""
        help_text = str(app.screen.query_one("#sl-help", Static).render())
        assert "https://" in help_text


@pytest.mark.asyncio
async def test_clear_link_button_blanks_the_stripe_url():
    from textual.widgets import Button, Select

    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.app import StripeLinksScreen
    from sovereign_agent.config import SETTINGS
    from sovereign_agent.shop import Product, load, save

    save(Product(name="Pro", billing="monthly", price_cents=1200,
                 stripe_url="https://buy.stripe.com/pro"), SETTINGS.paths.data_dir)

    async with CockpitApp().run_test(size=(120, 60)) as pilot:
        app = pilot.app
        app.action_stripe_links()
        await pilot.pause()
        assert isinstance(app.screen, StripeLinksScreen)
        app.screen.query_one("#sl-which", Select).value = "Pro"
        await pilot.pause()
        await pilot.click(app.screen.query_one("#sl-clear-btn", Button))
        await pilot.pause()

        assert load("Pro", SETTINGS.paths.data_dir).stripe_url == ""


@pytest.mark.asyncio
async def test_paste_from_clipboard_fills_the_value_field():
    from textual.widgets import Input

    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.app import StripeLinksScreen
    from sovereign_agent.config import SETTINGS
    from sovereign_agent.shop import Product, save

    save(Product(name="Basic", billing="monthly", price_cents=500),
         SETTINGS.paths.data_dir)

    async with CockpitApp().run_test(size=(120, 60)) as pilot:
        app = pilot.app
        app.action_stripe_links()
        await pilot.pause()
        assert isinstance(app.screen, StripeLinksScreen)
        app.screen._paste_from_clipboard(
            reader=lambda: ("  https://buy.stripe.com/pasted  ", "via wl-paste"))
        await pilot.pause()
        assert app.screen.query_one("#sl-value", Input).value == \
            "https://buy.stripe.com/pasted"


@pytest.mark.asyncio
async def test_action_toggles_the_screen_closed_when_reopened():
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.app import StripeLinksScreen

    async with CockpitApp().run_test(size=(120, 60)) as pilot:
        app = pilot.app
        app.action_stripe_links()
        await pilot.pause()
        assert isinstance(app.screen, StripeLinksScreen)
        app.action_stripe_links()
        await pilot.pause()
        assert not isinstance(app.screen, StripeLinksScreen)


@pytest.mark.asyncio
async def test_slash_command_alias_opens_the_screen():
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.app import StripeLinksScreen

    async with CockpitApp().run_test(size=(120, 60)) as pilot:
        app = pilot.app
        app._handle_slash("/stripe-links")
        await pilot.pause()
        assert isinstance(app.screen, StripeLinksScreen)
