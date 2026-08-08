"""Tests for grants_tracker.py — parsed against a REAL captured
grants.gov search2 response (curl'd directly 2026-08-01), not synthetic
JSON."""
from __future__ import annotations

import json
from pathlib import Path

from sovereign_agent.grants_tracker import (
    GrantsGovFetcher, build_source_url, parse_search2_response)

_FIXTURES = Path(__file__).parent / "fixtures"


def _real_response() -> dict:
    return json.loads((_FIXTURES / "grants_search2_sample.json").read_text())


def test_parses_real_captured_response():
    opps = parse_search2_response(_real_response())
    assert len(opps) == 3
    first = opps[0]
    assert first.opp_id == "141593"
    assert first.number == "P12AC10113"
    assert first.title == "Vegetation Interns"
    assert first.agency == "National Park Service"
    assert first.status == "posted"


def test_as_text_includes_key_fields():
    opps = parse_search2_response(_real_response())
    text = opps[1].as_text()
    assert "Making America Healthy Again" in text
    assert "Office of the Assistant Secretary for Health" in text
    assert "MP-CPI-25-001" in text
    assert "forecasted" in text


def test_url_builds_a_real_grants_gov_detail_link():
    opps = parse_search2_response(_real_response())
    assert opps[0].url == "https://www.grants.gov/search-results-detail/141593"


def test_empty_hits_returns_empty_list_not_crash():
    assert parse_search2_response({"errorcode": 0, "data": {"oppHits": []}}) == []


def test_unexpected_shape_returns_empty_list_not_crash():
    assert parse_search2_response({}) == []
    assert parse_search2_response({"errorcode": 1}) == []
    assert parse_search2_response("not a dict") == []  # type: ignore[arg-type]


def test_hit_missing_id_is_skipped():
    body = {"errorcode": 0, "data": {"oppHits": [{"title": "no id here"}]}}
    assert parse_search2_response(body) == []


def test_build_source_url_encodes_keyword_and_clamps_days_to_valid_bucket():
    url = build_source_url(keyword="small business", posted_within_days=10)
    assert "keyword=small+business" in url
    assert "postedDays=7" in url or "postedDays=14" in url  # clamps to nearest of 7/14


def test_grants_gov_fetcher_builds_items_from_real_response():
    from sovereign_agent.discord_runtime.sources import Source

    real_body = _real_response()

    class _FakeResp:
        def __init__(self, data: bytes) -> None:
            self._data = data

        def read(self) -> bytes:
            return self._data

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    calls = []

    def fake_opener(url, data, headers, timeout):
        calls.append((url, data, headers, timeout))
        return _FakeResp(json.dumps(real_body).encode("utf-8"))

    fetcher = GrantsGovFetcher(opener=fake_opener)
    source = Source(name="grants-small-business",
                    url=build_source_url(keyword="small business"),
                    kind="grants-gov")
    items = fetcher.fetch(source)
    assert len(items) == 3
    assert items[0].id == "141593"
    assert "Vegetation Interns" in items[0].text
    assert items[0].url.startswith("https://www.grants.gov/search-results-detail/")
    # confirms it actually POSTed (not GETted) with a JSON body
    assert len(calls) == 1
    posted_body = json.loads(calls[0][1])
    assert posted_body["keyword"] == "small business"


def test_grants_gov_fetcher_handles_network_error_gracefully():
    from sovereign_agent.discord_runtime.sources import Source

    def broken_opener(url, data, headers, timeout):
        raise OSError("connection refused")

    outcomes = []
    fetcher = GrantsGovFetcher(opener=broken_opener,
                               on_outcome=lambda name, ok, detail: outcomes.append((name, ok, detail)))
    source = Source(name="grants-x", url=build_source_url(), kind="grants-gov")
    items = fetcher.fetch(source)
    assert items == []
    assert outcomes and outcomes[0][1] is False
