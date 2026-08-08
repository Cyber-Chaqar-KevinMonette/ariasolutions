"""Tests for fulfillment.py — where & how do I get it (Kevin's ask)."""
from __future__ import annotations

from sovereign_agent.fulfillment import (
    BOTH,
    DELIVERY,
    INSTORE,
    detect_retailer,
    fulfillment_line,
    fulfillment_of,
)


def test_retailer_detection():
    assert detect_retailer("It Takes Two PS5 @ Walmart")["name"] == "Walmart"
    assert detect_retailer("RTX 5070 | Microcenter")["name"] == "Micro Center"
    assert detect_retailer("Mafia at Amazon")["name"] == "Amazon"
    assert detect_retailer("Zygarde at Target")["name"] == "Target"
    assert detect_retailer("just a reddit chat") is None


def test_fulfillment_models():
    # online-only ships
    assert fulfillment_of("game at Amazon")["fill"] == DELIVERY
    # big-box = both
    assert fulfillment_of("deal @ Walmart")["fill"] == BOTH
    # dollar general = in-store
    assert fulfillment_of("DG restock in-store")["fill"] == INSTORE
    # locators only where there are stores
    assert fulfillment_of("at Target")["locator"]
    assert fulfillment_of("at Amazon")["locator"] == ""


def test_signals_refine_default():
    # a DG item that ALSO ships → both
    assert fulfillment_of("pokemon at dollar general free shipping")["fill"] == BOTH
    # a Target item flagged in-store-only clearance → in-store
    assert fulfillment_of("clearance ymmv in-store at Target")["fill"] == INSTORE
    # unknown retailer but 'free shipping' → still tells them it ships
    assert fulfillment_of("mystery deal free shipping")["fill"] == DELIVERY
    assert fulfillment_of("mystery deal free shipping")["known"] is False


def test_fulfillment_line_shape_and_honest_silence():
    line = fulfillment_line("RTX 5070 | Microcenter")
    assert "🏪🚚" in line and "Micro Center" in line
    assert "find your store" in line and "microcenter.com" in line
    assert "~10a" in line                       # typical hours
    # nothing knowable → empty, never fabricated
    assert fulfillment_line("what's the value of these dunks?") == ""
    # amazon: ships, no locator link
    amz = fulfillment_line("game at Amazon")
    assert "ships to you" in amz and "find your store" not in amz
