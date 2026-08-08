"""Tests for api_providers — the Key Concierge registry."""
from __future__ import annotations

from sovereign_agent.api_providers import (
    PROVIDERS,
    gatherable,
    get_provider,
    keyless,
    render_status,
    status,
)


def test_registry_integrity():
    slugs = [p.slug for p in PROVIDERS]
    assert len(slugs) == len(set(slugs)), "duplicate provider slugs"
    for p in PROVIDERS:
        assert p.name and p.unlocks
        if p.keyless:
            assert not p.env_vars                    # nothing to gather
        else:
            assert p.env_vars, f"{p.slug} needs env vars"
            assert p.signup_url.startswith("http")
            assert p.steps, f"{p.slug} needs steps"
            assert p.probe, f"{p.slug} needs a validation probe"


def test_the_best_path_providers_present():
    slugs = {p.slug for p in gatherable()}
    for must in ("reddit", "bestbuy", "google-maps", "ebay", "stripe",
                 "brickset", "bricklink"):     # lego-d: the honest LEGO lanes
        assert must in slugs
    # keyless sources declared (already working)
    ks = {p.slug for p in keyless()}
    assert "weather" in ks and "deal-feeds" in ks
    assert "nhtsa" in ks                       # vehicles-d: official + free


def test_every_probe_exists_on_credentials():
    from sovereign_agent import credentials
    for p in gatherable():
        assert hasattr(credentials, p.probe), f"missing {p.probe}"


def test_status_unlocked_vs_blocked():
    st = status({"BESTBUY_API_KEY": "abc"})
    by = {s["slug"]: s for s in st}
    assert by["bestbuy"]["have"] is True
    assert by["reddit"]["have"] is False
    # reddit needs BOTH id and secret
    st2 = status({"REDDIT_CLIENT_ID": "x"})
    assert {s["slug"]: s for s in st2}["reddit"]["have"] is False
    st3 = status({"REDDIT_CLIENT_ID": "x", "REDDIT_CLIENT_SECRET": "y"})
    assert {s["slug"]: s for s in st3}["reddit"]["have"] is True


def test_render_status_is_actionable():
    out = render_status({})
    assert "Key Concierge" in out
    assert "sov keys onboard" in out          # tells you how
    assert "KEY_GATHERING.md" in out          # points at the doc
    assert "keyless" in out.lower()


def test_get_provider():
    assert get_provider("bestbuy").name == "Best Buy Developer API"
    assert get_provider("BestBuy").slug == "bestbuy"   # case-insensitive
    assert get_provider("nope") is None
