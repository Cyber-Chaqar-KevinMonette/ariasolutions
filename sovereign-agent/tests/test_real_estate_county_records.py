"""Tests for real_estate_county_records.py — parsed against REAL saved HTML
fixtures (a slice of each county's live listings page, fetched directly),
not synthetic markup. If either county site changes its markup, these
should be the first thing to fail."""
from __future__ import annotations

from pathlib import Path

import pytest

from sovereign_agent.real_estate_county_records import (
    parse_christian_county_ky, parse_montgomery_county_tn)

_FIXTURES = Path(__file__).parent / "fixtures"


def _christian_html() -> str:
    return (_FIXTURES / "christian_co_sample.html").read_text()


def _montgomery_html() -> str:
    return (_FIXTURES / "montgomery_tn_sample.html").read_text()


def test_christian_county_parses_all_three_sample_listings():
    listings = parse_christian_county_ky(_christian_html())
    assert len(listings) == 3
    for l in listings:
        assert l.county == "Christian County"
        assert l.state == "KY"


def test_christian_county_extracts_clean_fields_no_bleed_across_labels():
    """Regression: case_name must NOT swallow "Case Number:"/"Sale Date:"
    when they share one <p> with no <br/> between them (some listings on
    this site format that way, some don't)."""
    listings = parse_christian_county_ky(_christian_html())
    first = listings[0]
    assert "Case Number" not in first.case_or_type
    assert "Sale Date" not in first.case_or_type
    assert first.address == "1500 East 1st Street Hopkinsville, KY 42240"
    assert first.sale_date == "07/27/2026"
    assert first.amount == "$19,100.00"
    assert first.detail_url.startswith("https://christiancountymastercommissioner.com/")


def test_christian_county_address_drops_get_map_boilerplate():
    listings = parse_christian_county_ky(_christian_html())
    for l in listings:
        assert "Get Map" not in l.address
        assert "(" not in l.address


def test_montgomery_county_parses_all_three_sample_listings():
    listings = parse_montgomery_county_tn(_montgomery_html())
    assert len(listings) == 3
    for l in listings:
        assert l.county == "Montgomery County"
        assert l.state == "TN"


def test_montgomery_county_extracts_clean_fields_no_bleed_into_captions():
    """Regression: sale_date must NOT swallow the photo <figcaption> text
    that follows it in the flattened (tag-stripped) text — there's no
    real newline at that boundary in the source HTML."""
    listings = parse_montgomery_county_tn(_montgomery_html())
    by_type = {l.case_or_type: l for l in listings}
    assert by_type["JUDICIAL FORECLOSURE"].sale_date == "August 26th, 2026 @ 10 AM"
    assert "brick house" not in by_type["JUDICIAL FORECLOSURE"].sale_date
    assert by_type["JUDICIAL FORECLOSURE"].amount == "$350,000.00"
    assert by_type["FINAL AUCTION"].amount == "$110,220.00"


def test_montgomery_county_handles_listing_with_no_stated_opening_bid():
    """The Shady Lawn Drive listing genuinely has no "Opening Bid" line in
    the source — amount must be empty, not fabricated or borrowed from a
    neighboring listing."""
    listings = parse_montgomery_county_tn(_montgomery_html())
    shady_lawn = next(l for l in listings if "Shady Lawn" in l.address)
    assert shady_lawn.amount == ""


def test_as_text_includes_county_and_state_for_every_listing():
    """Kevin: "have each post list the location and county per post" —
    as_text() is the bridge into the existing real-estate pipeline
    (process_real_estate_item takes text), so the county tag has to
    survive into that string, not just live on the dataclass."""
    for l in parse_christian_county_ky(_christian_html()):
        assert "Christian County, KY" in l.as_text()
    for l in parse_montgomery_county_tn(_montgomery_html()):
        assert "Montgomery County, TN" in l.as_text()


def test_empty_html_returns_no_listings_not_a_crash():
    assert parse_christian_county_ky("<html></html>") == []
    assert parse_montgomery_county_tn("<html></html>") == []


def test_malformed_article_missing_fields_is_skipped_not_crashed():
    junk = '<article><h2 class="blog-entry-title entry-title"><a href="#" rel=bookmark>no fields here</a></h2></article>'
    assert parse_christian_county_ky(junk) == []


def test_fetch_christian_county_items_builds_real_items_with_stable_ids():
    from sovereign_agent.real_estate_county_records import fetch_christian_county_items

    items = fetch_christian_county_items(_christian_html(), "https://christiancountymastercommissioner.com/listings/")
    assert len(items) == 3
    for item in items:
        assert item.id
        assert "Christian County, KY" in item.text
        assert item.url.startswith("https://christiancountymastercommissioner.com/")
    # Same input -> same ids (dedup must actually work across polls).
    items2 = fetch_christian_county_items(_christian_html(), "https://christiancountymastercommissioner.com/listings/")
    assert [i.id for i in items] == [i.id for i in items2]


def test_fetch_montgomery_county_items_builds_real_items_with_stable_ids():
    from sovereign_agent.real_estate_county_records import fetch_montgomery_county_items

    url = "https://montgomerytn.gov/chancery/upcoming-clerk-and-master-sales"
    items = fetch_montgomery_county_items(_montgomery_html(), url)
    assert len(items) == 3
    ids = [i.id for i in items]
    assert len(set(ids)) == 3  # each listing gets a distinct id
    for item in items:
        assert "Montgomery County, TN" in item.text
    items2 = fetch_montgomery_county_items(_montgomery_html(), url)
    assert [i.id for i in items2] == ids


def test_christian_county_strips_get_map_with_literal_en_dash_too():
    """live-bug-d: found via a real production poll, not the original 3-
    listing fixture -- the site mixes the &#8211; ENTITY (converted to "-")
    with a literal en-dash "–" character on some listings (looks
    hand-typed). Both must be stripped, not just the hyphen form."""
    html = (_FIXTURES / "christian_co_endash.html").read_text(encoding="utf-8")
    listings = parse_christian_county_ky(html)
    assert len(listings) == 1
    assert listings[0].address == "1710 Clarence Dr Hopkinsville, KY 4224"
    assert "Get Map" not in listings[0].address
    assert "–" not in listings[0].address
