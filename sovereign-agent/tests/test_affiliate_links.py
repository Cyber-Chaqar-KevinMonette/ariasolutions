"""Tests for affiliate_links.py — Amazon Associates tag injection.

Kevin, 2026-07-25: "mainly the third party affiliate links... whatever
can bring us the most money fast." Amazon only for now. The core
invariant: an unconfigured or non-Amazon link must ALWAYS pass through
completely unchanged — a broken/garbled deal link is worse than an
untagged one.
"""
from __future__ import annotations

from sovereign_agent.affiliate_links import tag_url


def test_tags_an_amazon_url_with_the_vaulted_tag(tmp_path, monkeypatch):
    from sovereign_agent.credentials import set_secret
    vault = tmp_path / "shop.env"
    monkeypatch.setenv("ARIA_KEYS_FILE", str(vault))
    set_secret("AMAZON_ASSOCIATE_TAG", "ariashop-20", vault)

    out = tag_url("https://www.amazon.com/dp/B0EXAMPLE")
    assert "tag=ariashop-20" in out
    assert out.startswith("https://www.amazon.com/dp/B0EXAMPLE")


def test_replaces_an_existing_tag_rather_than_duplicating(tmp_path, monkeypatch):
    from sovereign_agent.credentials import set_secret
    vault = tmp_path / "shop.env"
    monkeypatch.setenv("ARIA_KEYS_FILE", str(vault))
    set_secret("AMAZON_ASSOCIATE_TAG", "ariashop-20", vault)

    out = tag_url("https://www.amazon.com/dp/B0X?tag=someoneelse-20&other=1")
    assert out.count("tag=") == 1
    assert "tag=ariashop-20" in out
    assert "other=1" in out


def test_passes_through_unchanged_when_no_tag_configured(tmp_path, monkeypatch):
    monkeypatch.setenv("ARIA_KEYS_FILE", str(tmp_path / "shop.env"))
    url = "https://www.amazon.com/dp/B0EXAMPLE"
    assert tag_url(url) == url


def test_passes_through_unchanged_for_a_non_amazon_domain(tmp_path, monkeypatch):
    from sovereign_agent.credentials import set_secret
    vault = tmp_path / "shop.env"
    monkeypatch.setenv("ARIA_KEYS_FILE", str(vault))
    set_secret("AMAZON_ASSOCIATE_TAG", "ariashop-20", vault)

    url = "https://www.bestbuy.com/site/some-product/123.p"
    assert tag_url(url) == url


def test_passes_through_a_reddit_comment_link_unchanged(tmp_path, monkeypatch):
    monkeypatch.setenv("ARIA_KEYS_FILE", str(tmp_path / "shop.env"))
    url = "https://www.reddit.com/comments/abc123"
    assert tag_url(url) == url


def test_empty_and_malformed_input_never_raises():
    assert tag_url("") == ""
    assert tag_url(None) == ""
    assert tag_url("not a url at all") == "not a url at all"


def test_amazon_subdomain_and_other_tlds_are_recognized(tmp_path, monkeypatch):
    from sovereign_agent.credentials import set_secret
    vault = tmp_path / "shop.env"
    monkeypatch.setenv("ARIA_KEYS_FILE", str(vault))
    set_secret("AMAZON_ASSOCIATE_TAG", "ariashop-20", vault)

    assert "tag=ariashop-20" in tag_url("https://smile.amazon.com/dp/B0X")
    assert "tag=ariashop-20" in tag_url("https://www.amazon.co.uk/dp/B0X")
