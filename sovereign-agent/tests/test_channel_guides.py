"""Tests for channel_guides — every channel explains itself."""
from __future__ import annotations

from sovereign_agent.discord_admin.blueprint import shop_blueprint
from sovereign_agent.discord_admin.channel_guides import (
    GUIDES,
    already_seeded,
    guide_for,
    mark_seeded,
)


def test_every_blueprint_channel_has_a_guide():
    """Kevin: 'fill EVERY channel' — structural: a future blueprint
    channel without a guide fails the suite."""
    missing = [ch for ch in shop_blueprint().channel_names()
               if guide_for(ch) is None]
    assert not missing, f"channels without guides: {missing}"


def test_guides_are_decoration_tolerant_and_substantive():
    assert guide_for("🛒 storefront") == GUIDES["storefront"]
    assert guide_for("LIVE-DEMO") == GUIDES["live-demo"]
    assert guide_for("no-such-channel") is None
    for name, text in GUIDES.items():
        assert len(text) > 60, f"guide for {name} is too thin"
    # the command room teaches the commands
    assert "/scout" in GUIDES["bot-commands"] and "/ask" in GUIDES["bot-commands"]


def test_seeded_ledger_is_idempotent(tmp_path):
    assert not already_seeded(tmp_path, "storefront")
    mark_seeded(tmp_path, "🛒 storefront")          # decorated on purpose
    assert already_seeded(tmp_path, "storefront")   # canon match
    assert not already_seeded(tmp_path, "welcome")
