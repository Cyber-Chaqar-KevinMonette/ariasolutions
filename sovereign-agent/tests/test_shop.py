"""Tests for shop.py — the Bot Shop catalog engine."""
from __future__ import annotations

import pytest

from sovereign_agent.shop import (
    BILLING_KINDS,
    TIERS,
    Product,
    compose_shop_report,
    delete,
    is_shop_query,
    list_all,
    load,
    money,
    save,
    seed_pass_products,
    seed_starter_catalog,
    shop_dir,
    slugify,
    validate,
)


# ── model / pricing ─────────────────────────────────────────────────────────
def test_money_formats_cleanly():
    assert money(500) == "$5"
    assert money(1250) == "$12.50"
    assert money(0) == "$0"


def test_price_label_variants():
    assert Product(name="A", billing="monthly", price_cents=800).price_label() == "$8/mo"
    assert Product(name="A", billing="yearly", price_cents=9000).price_label() == "$90/yr"
    assert Product(name="A", billing="one_time", price_cents=4000).price_label() == "$40"
    assert Product(name="A", billing="monthly", price_cents=800,
                   setup_cents=3000).price_label() == "$30 setup + $8/mo"


def test_price_label_shows_duration_for_one_time_passes():
    """passes-d: a one-time product with duration_days set shows a
    friendly unit ('24 hours'/'week'/'month'/'year') instead of a bare
    price with no cadence at all."""
    assert Product(name="A", billing="one_time", price_cents=300,
                   duration_days=1).price_label() == "$3 / 24 hours"
    assert Product(name="A", billing="one_time", price_cents=900,
                   duration_days=7).price_label() == "$9 / week"
    assert Product(name="A", billing="one_time", price_cents=1900,
                   duration_days=30).price_label() == "$19 / month"
    assert Product(name="A", billing="one_time", price_cents=14900,
                   duration_days=365).price_label() == "$149 / year"
    # a plain one-time product (no duration) is unaffected
    assert Product(name="A", billing="one_time",
                   price_cents=2000).price_label() == "$20"


def test_validate_rejects_negative_duration_days():
    assert "duration_days cannot be negative" in validate(
        Product(name="A", duration_days=-1))


def test_runs_without_her_is_inverse_of_attended():
    assert Product(name="A", attended=False).runs_without_her is True
    assert Product(name="A", attended=True).runs_without_her is False


def test_billing_and_tiers_catalogs():
    assert {"monthly", "yearly", "one_time"} == {k for k, _ in BILLING_KINDS}
    assert {"", "basic", "pro", "vip"} == {k for k, _ in TIERS}


# ── validation ──────────────────────────────────────────────────────────────
def test_validate_requires_name():
    assert any("name is required" in e for e in validate(Product(name="")))


def test_validate_rejects_bad_billing_and_tier():
    assert validate(Product(name="A", billing="weekly"))
    assert validate(Product(name="A", tier="platinum"))


def test_validate_rejects_negative_price_and_bad_url():
    assert validate(Product(name="A", price_cents=-1))
    assert validate(Product(name="A", stripe_url="not-a-url"))
    assert not validate(Product(name="A", stripe_url="https://buy.stripe.com/x"))


# ── store round-trip ────────────────────────────────────────────────────────
def test_save_load_round_trip(tmp_path):
    save(Product(name="Pro", tier="pro", billing="monthly", price_cents=1200,
                 stripe_url="https://buy.stripe.com/pro"), tmp_path)
    got = load("Pro", tmp_path)
    assert got is not None and got.tier == "pro" and got.price_cents == 1200
    assert got.created_at and got.modified_at


def test_save_invalid_raises(tmp_path):
    with pytest.raises(ValueError):
        save(Product(name=""), tmp_path)


def test_list_all_sorted_by_sort_then_name(tmp_path):
    save(Product(name="Zeta", sort=10), tmp_path)
    save(Product(name="Alpha", sort=20), tmp_path)
    assert [p.name for p in list_all(tmp_path)] == ["Zeta", "Alpha"]   # sort wins


def test_list_all_only_active(tmp_path):
    save(Product(name="Live", active=True), tmp_path)
    save(Product(name="Hidden", active=False), tmp_path)
    names = [p.name for p in list_all(tmp_path, only_active=True)]
    assert names == ["Live"]


def test_delete(tmp_path):
    save(Product(name="Gone"), tmp_path)
    assert delete("Gone", tmp_path) is True
    assert delete("Gone", tmp_path) is False


def test_corrupt_file_skipped(tmp_path):
    save(Product(name="Good"), tmp_path)
    (shop_dir(tmp_path) / "broken.json").write_text("{bad", encoding="utf-8")
    assert [p.name for p in list_all(tmp_path)] == ["Good"]


def test_slugify_path_safe():
    assert slugify("../../etc") == "etc"
    assert slugify("") == "product"


# ── seed + chat bridge ──────────────────────────────────────────────────────
def test_seed_starter_catalog_is_idempotent(tmp_path):
    first = seed_starter_catalog(tmp_path)
    assert len(first) == 10                   # 3 tiers + 4 monthly + 3 one-time/custom
    again = seed_starter_catalog(tmp_path)
    assert again == []                       # nothing re-written
    assert len(list_all(tmp_path)) == 10
    # the tiers lead, VIP is the attended (with-Aria) one
    names = [p.name for p in list_all(tmp_path)]
    assert names[:3] == ["Basic", "Pro", "VIP"]
    assert load("VIP", tmp_path).attended is True


def test_seed_pass_products_is_idempotent(tmp_path):
    """passes-d (Kevin, 2026-07-26): "24 hour pass... week pass, month
    pass, year pass." One shared all-access role, sold by duration only."""
    first = seed_pass_products(tmp_path)
    assert len(first) == 4
    again = seed_pass_products(tmp_path)
    assert again == []                        # nothing re-written
    assert len(list_all(tmp_path)) == 4

    by_name = {p.name: p for p in list_all(tmp_path)}
    assert set(by_name) == {"24-Hour Pass", "Week Pass", "Month Pass", "Year Pass"}
    for p in by_name.values():
        assert p.billing == "one_time"
        assert p.kind == "access-pass"
        assert p.access_role == "Pass-Holder"   # one shared tier, not 4 roles
        assert validate(p) == []

    assert by_name["24-Hour Pass"].duration_days == 1
    assert by_name["Week Pass"].duration_days == 7
    assert by_name["Month Pass"].duration_days == 30
    assert by_name["Year Pass"].duration_days == 365
    assert by_name["24-Hour Pass"].price_cents == 300
    assert by_name["Week Pass"].price_cents == 900
    assert by_name["Month Pass"].price_cents == 1900
    assert by_name["Year Pass"].price_cents == 14900


def test_is_shop_query():
    assert is_shop_query("what's in the shop?")
    assert is_shop_query("show me our prices")
    assert not is_shop_query("how are you feeling")


def test_compose_shop_report_empty(tmp_path):
    out = compose_shop_report(tmp_path)
    assert "/shop" in out and "empty" in out


def test_compose_shop_report_lists_products(tmp_path):
    seed_starter_catalog(tmp_path)
    out = compose_shop_report(tmp_path)
    assert "Basic" in out and "$5/mo" in out and "autonomous" in out
    assert "VIP" in out and "with-Aria" in out


def test_storefront_never_drops_a_product(tmp_path, monkeypatch):
    """missing-product-d (Kevin, 2026-07-17): the live storefront silently
    dropped Custom Bot — 10 products + the stats card = 11 embeds, and a
    single-message [:10] cap ate the last one. Structural now: EVERY
    active product gets an embed, and publish chunks into as many
    messages as Discord's 10-embed cap requires. A growing catalog can
    never silently lose its newest product again."""
    from sovereign_agent.shop import (
        Product, publish_storefront, save, storefront_embeds)
    for i in range(12):
        save(Product(name=f"Bot {i:02d}", blurb="x", kind="bot",
                     billing="monthly", price_cents=500, sort=i), tmp_path)
    embeds = storefront_embeds(
        __import__("sovereign_agent.shop", fromlist=["list_all"])
        .list_all(tmp_path, only_active=True))
    assert len(embeds) == 12                      # no truncation, ever

    sends = []

    class FakeDelivery:
        def __init__(self, env, live=False):
            pass

        def send(self, text, embeds=None, username=""):
            sends.append((text, list(embeds or [])))
            from sovereign_agent.discord_runtime.delivery import DeliveryResult
            return DeliveryResult(sent=True, dry_run=False, detail="ok")

    import sovereign_agent.discord_runtime.delivery as dmod
    monkeypatch.setattr(dmod, "WebhookDelivery", FakeDelivery)
    publish_storefront(tmp_path, live=True, include_stats=True)
    all_embeds = [e for _, chunk in sends for e in chunk]
    assert len(sends) == 2                        # 13 embeds → 2 messages
    assert all(len(chunk) <= 10 for _, chunk in sends)
    assert len(all_embeds) == 13                  # stats + all 12 products
    assert sends[0][0].startswith("🛒")           # header on first message
    assert sends[1][0] == ""                      # continuation is quiet


def test_publish_buy_links_posts_every_active_product_no_stats_card(tmp_path, monkeypatch):
    """passes-d (Kevin, 2026-07-26): "channels for direct purchase
    links." Same chunking discipline as publish_storefront, but no
    stats card — this is a link list, not the storefront pitch."""
    from sovereign_agent.shop import Product, publish_buy_links, save

    save(Product(name="24-Hour Pass", billing="one_time", price_cents=300,
                 duration_days=1), tmp_path)
    save(Product(name="Week Pass", billing="one_time", price_cents=900,
                 duration_days=7), tmp_path)
    save(Product(name="Inactive", billing="one_time", price_cents=100,
                 active=False), tmp_path)

    sends = []

    class FakeDelivery:
        def __init__(self, env, live=False):
            pass

        def send(self, text, embeds=None, username=""):
            sends.append((text, list(embeds or [])))
            from sovereign_agent.discord_runtime.delivery import DeliveryResult
            return DeliveryResult(sent=True, dry_run=False, detail="ok")

    import sovereign_agent.discord_runtime.delivery as dmod
    monkeypatch.setattr(dmod, "WebhookDelivery", FakeDelivery)
    publish_buy_links(tmp_path, live=True)

    all_embeds = [e for _, chunk in sends for e in chunk]
    assert len(all_embeds) == 2                    # active products only
    assert {e["title"] for e in all_embeds} == {"24-Hour Pass", "Week Pass"}
    assert sends[0][0].startswith("🔗")            # its own header, not 🛒
    assert "/buy or /passes" in sends[0][0]
