"""Tests for tips.py — the Tip Jar (surfaces links, never holds money)."""
from __future__ import annotations

from sovereign_agent.tips import (
    DEFAULT_LINKS,
    TIP_TIERS,
    compose_tip_report,
    is_tip_query,
    load_tip_links,
    set_tip_link,
    tip_buttons,
    tip_embed,
)


def test_links_seed_and_persist(tmp_path):
    links = load_tip_links(tmp_path)
    assert len(links) == len(DEFAULT_LINKS)
    assert (tmp_path / "tips" / "links.json").exists()
    # all are real https payment links
    assert all(v.startswith("https://buy.stripe.com/") for v in links.values())


def test_buttons_cover_every_tier_with_dollars(tmp_path):
    btns = tip_buttons(tmp_path)
    labels = [b["label"] for b in btns]
    assert "💛 $1" in labels and "💛 $1000" in labels
    assert len(btns) == len(TIP_TIERS)
    assert all(b["url"].startswith("https://") for b in btns)


def test_set_tip_link_overrides(tmp_path):
    load_tip_links(tmp_path)
    set_tip_link(tmp_path, 500, "https://buy.stripe.com/NEW5")
    assert load_tip_links(tmp_path)["500"] == "https://buy.stripe.com/NEW5"


def test_embed_and_report(tmp_path):
    e = tip_embed(tmp_path)
    assert "Tip Jar" in e["title"] and "Stripe" in e["description"]
    rep = compose_tip_report(tmp_path)
    assert "$1" in rep and "buy.stripe.com" in rep and "Thank you" in rep


def test_tip_query_matches_but_not_unrelated():
    assert is_tip_query("how do i tip you?")
    assert is_tip_query("where's the tip jar")
    assert is_tip_query("i want to donate")
    assert not is_tip_query("what do you sell")
    assert not is_tip_query("how are the bots")
