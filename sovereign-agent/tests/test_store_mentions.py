"""Tests for store_mentions — honest location clues, never invented."""
from __future__ import annotations

from sovereign_agent.store_mentions import (
    detect_mentions,
    location_note,
    mention_line,
    rank_stores_by_distance,
)


def test_detects_named_stores():
    assert "Clarksville" in detect_mentions("Clarksville Target got a drop")
    m = detect_mentions("Pokemon restock at Target on Fort Campbell today")
    assert any("Fort Campbell" in x for x in m)
    assert "store #1234" in detect_mentions("Walmart store #1234 has stock")


def test_no_mention_is_honest_silence():
    assert detect_mentions("great pull today!") == []
    assert mention_line("just a discussion") == ""
    assert "mentioned:" in mention_line("Clarksville Target drop")


def test_distance_ranking_is_an_honest_stub():
    # never fabricates addresses — returns [] until the API key lands
    assert rank_stores_by_distance(["Clarksville"], {"zips": ["42240"]}) == []


def test_location_note_is_honest_about_the_api():
    n = location_note({"zips": ["42240"]})
    assert "42240" in n and "API" in n
    n2 = location_note(None)
    assert "My Area" in n2 and "API" in n2
