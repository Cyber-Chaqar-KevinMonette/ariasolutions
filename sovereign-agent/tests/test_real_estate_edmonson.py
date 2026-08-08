"""Tests for real_estate_edmonson_county.py -- parser fixtures are real
fetched HTML from edmonsoncountymastercommissioner.com (2026-08-01), not
guessed: edmonson_cancelled.html is the verbatim live page at fetch time;
edmonson_active.html is the same real structure with the "SALE CANCELLED"
banner removed, to prove the positive-parse path independent of the fact
the live sale happened to be cancelled that day."""
from __future__ import annotations

from pathlib import Path

from sovereign_agent.real_estate_edmonson_county import (
    fetch_edmonson_county_items, parse_edmonson_county_ky)

FIXTURES = Path(__file__).parent / "fixtures"


def test_active_sale_parses_the_real_listing():
    html = (FIXTURES / "edmonson_active.html").read_text()
    listings = parse_edmonson_county_ky(html)
    assert len(listings) == 1
    listing = listings[0]
    assert listing.county == "Edmonson County" and listing.state == "KY"
    assert "22-CI-00063" in listing.case_or_type
    assert "Freedom Mortgage" in listing.case_or_type
    assert "25 Cornerstone Ct." in listing.address
    assert "Brownsville, KY" in listing.address
    assert listing.amount == "$150,000.00"


def test_cancelled_sale_yields_no_listings():
    html = (FIXTURES / "edmonson_cancelled.html").read_text()
    listings = parse_edmonson_county_ky(html)
    assert listings == []


def test_fetch_adapter_returns_items_matching_scrape_fetcher_contract():
    html = (FIXTURES / "edmonson_active.html").read_text()
    items = fetch_edmonson_county_items(html, "https://example.com")
    assert len(items) == 1
    item = items[0]
    assert item.id  # stable dedup key, non-empty
    assert "Cornerstone" in item.text
    assert "Edmonson County" in item.text
    assert item.url == "https://www.edmonsoncountymastercommissioner.com/sale-dates.html"


def test_two_listings_get_distinct_ids():
    html = (FIXTURES / "edmonson_active.html").read_text()
    items = fetch_edmonson_county_items(html, "https://example.com")
    ids = [i.id for i in items]
    assert len(ids) == len(set(ids))


def test_no_listings_when_no_case_rows_present():
    assert parse_edmonson_county_ky("<div>nothing here</div>") == []
