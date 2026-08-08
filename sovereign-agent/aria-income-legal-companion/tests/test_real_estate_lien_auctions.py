"""Tests for real_estate_lien_auctions.py — parsed against REAL saved HTML
(Christian County KY's actual tax-sale-date page, fetched live 2026-08-01)."""
from __future__ import annotations

from pathlib import Path

from sovereign_agent.real_estate_lien_auctions import (
    fetch_christian_county_tax_sale_items, parse_christian_county_tax_sale_date)

_FIXTURES = Path(__file__).parent / "fixtures"


def _html() -> str:
    return (_FIXTURES / "christian_co_tax_sale_date.html").read_text()


def test_parses_real_sale_date_and_deadline():
    ann = parse_christian_county_tax_sale_date(_html())
    assert ann is not None
    assert ann.sale_date == "July 28, 2026"
    assert ann.registration_deadline == "July 20, 2026"


def test_parses_real_phone_number():
    ann = parse_christian_county_tax_sale_date(_html())
    assert ann.phone == "(270) 887-4109"


def test_as_text_labels_it_clearly_as_a_lien_sale_not_a_property_listing():
    ann = parse_christian_county_tax_sale_date(_html())
    text = ann.as_text()
    assert "Christian County" in text
    assert "July 28, 2026" in text
    assert "lien" in text.lower()
    assert "not the property" in text.lower()


def test_no_sale_date_sentence_returns_none_not_a_crash():
    assert parse_christian_county_tax_sale_date("<html><body>nothing here</body></html>") is None


def test_fetch_items_builds_one_stable_item():
    items = fetch_christian_county_tax_sale_items(_html(), "https://christiancountyky.gov/tax-sale-date")
    assert len(items) == 1
    assert "July 28, 2026" in items[0].text
    assert items[0].url == "https://christiancountyky.gov/tax-sale-date"
    # same html -> same id (dedup must work across polls)
    items2 = fetch_christian_county_tax_sale_items(_html(), "https://christiancountyky.gov/tax-sale-date")
    assert items[0].id == items2[0].id


def test_empty_html_returns_no_items():
    assert fetch_christian_county_tax_sale_items("<html></html>", "https://x") == []
