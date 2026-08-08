"""Tests for advertising — rotation deck, cadence floor, dry-run default."""
from __future__ import annotations

import json

from sovereign_agent.advertising import (
    AD_MIN_INTERVAL_S,
    ad_status,
    build_deck,
    load_copy,
    maybe_publish_ad,
    next_ad,
    publish_ad,
    render_ad_status,
)
from sovereign_agent.shop import Product, save


def _seed(tmp_path, n=2):
    for i in range(n):
        save(Product(name=f"Alert Bot {i}", blurb=f"pings for {i}",
                     price_cents=800, stripe_url="https://buy.stripe.com/x"),
             tmp_path)


# ── the deck ─────────────────────────────────────────────────────────────────
def test_deck_is_shop_card_plus_active_products(tmp_path):
    _seed(tmp_path, 2)
    save(Product(name="Retired Bot", active=False), tmp_path)
    deck = build_deck(tmp_path)
    labels = [label for label, _ in deck]
    assert labels[0] == "shop" and len(deck) == 3
    assert "Retired Bot" not in labels
    # cards are real embeds with the professional footer
    for _, embed in deck:
        assert embed["title"] and "#storefront" in embed["footer"]["text"]


def test_deck_survives_an_empty_shop(tmp_path):
    deck = build_deck(tmp_path)
    assert len(deck) == 1 and deck[0][0] == "shop"


def test_product_card_carries_price_mode_and_link(tmp_path):
    _seed(tmp_path, 1)
    label, embed = build_deck(tmp_path)[1]
    assert label == "Alert Bot 0"
    assert "$8/mo" in embed["description"] and "24/7" in embed["description"]
    assert embed["url"] == "https://buy.stripe.com/x"


# ── cadence floor: spam impossible by construction ───────────────────────────
def test_first_ad_allowed_then_floor_engages(tmp_path, monkeypatch):
    _seed(tmp_path)
    monkeypatch.setenv("DISCORD_ADS_WEBHOOK_URL", "https://example.test/hook")
    sent = []
    import sovereign_agent.discord_runtime.delivery as delivery

    monkeypatch.setattr(
        delivery.WebhookDelivery, "send",
        lambda self, content, embeds=None, username=None: (
            sent.append((content, embeds)),
            delivery.DeliveryResult(sent=True, dry_run=False, detail="sent"),
        )[1])
    ok, detail = publish_ad(tmp_path, live=True, now=1000.0)
    assert ok and "shop" in detail and len(sent) == 1
    # immediately again → structurally refused, even with live=True
    ok2, detail2 = publish_ad(tmp_path, live=True, now=1001.0)
    assert not ok2 and "cadence floor" in detail2 and len(sent) == 1
    # a caller can NOT shrink the floor
    ok3, _ = publish_ad(tmp_path, live=True, now=1002.0, min_interval_s=1.0)
    assert not ok3
    # after the floor elapses, the NEXT card in the rotation goes out
    ok4, detail4 = publish_ad(tmp_path, live=True,
                              now=1000.0 + AD_MIN_INTERVAL_S + 1)
    assert ok4 and "Alert Bot 0" in detail4 and len(sent) == 2


def test_dry_run_never_advances_rotation_or_cadence(tmp_path):
    _seed(tmp_path)
    before = next_ad(tmp_path)[0]
    ok, detail = publish_ad(tmp_path, live=False, now=1000.0)
    assert not ok and "dry-run" in detail
    assert next_ad(tmp_path)[0] == before           # rotation unchanged
    assert ad_status(tmp_path, now=1001.0).allowed  # cadence unburned


def test_status_render_reports_cooldown(tmp_path):
    _seed(tmp_path)
    (tmp_path / "advertising").mkdir(parents=True, exist_ok=True)
    (tmp_path / "advertising" / "state.json").write_text(
        json.dumps({"last_sent_ts": 1000.0, "index": 1}))
    s = ad_status(tmp_path, now=1000.0 + 3600)
    assert not s.allowed and s.wait_s > 0
    text = render_ad_status(tmp_path, now=1000.0 + 3600)
    assert "cooling down" in text and "Alert Bot 0" in text


# ── kevin's tunable copy + the daemon hook ───────────────────────────────────
def test_copy_override(tmp_path):
    assert load_copy(tmp_path) == ""
    (tmp_path / "advertising").mkdir(parents=True, exist_ok=True)
    (tmp_path / "advertising" / "copy.txt").write_text("Summer sale is live!")
    assert load_copy(tmp_path) == "Summer sale is live!"


def test_daemon_hook_is_opt_in_and_live_only(tmp_path, monkeypatch):
    _seed(tmp_path)
    monkeypatch.delenv("DISCORD_ADS_AUTO", raising=False)
    assert maybe_publish_ad(tmp_path, live=True, now=1000.0) is None  # no opt-in
    monkeypatch.setenv("DISCORD_ADS_AUTO", "1")
    assert maybe_publish_ad(tmp_path, live=False, now=1000.0) is None  # dry-run daemon
    # opted-in + live → it attempts (webhook unset → not sent, honest note)
    monkeypatch.delenv("DISCORD_ADS_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    note = maybe_publish_ad(tmp_path, live=True, now=1000.0)
    assert note is not None and "dry-run" in note
