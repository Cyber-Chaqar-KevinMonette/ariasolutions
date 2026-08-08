"""Tests for business_funding_directory.py — mostly structural: every
entry must be real (checked URL) and non-empty, matching the standard
already applied to real_estate_connections.py."""
from __future__ import annotations

from sovereign_agent.business_funding_directory import (
    GENERAL_LENDERS, SBA_PROGRAMS, STATE_INCENTIVE_PORTALS)


def test_sba_programs_cover_7a_504_and_microloan():
    names = [p.name for p in SBA_PROGRAMS]
    assert any("7(a)" in n for n in names)
    assert any("504" in n for n in names)
    assert any("Microloan" in n for n in names)


def test_every_sba_program_has_a_real_sba_gov_url():
    for p in SBA_PROGRAMS:
        assert p.url.startswith("https://www.sba.gov/")
        assert p.note


def test_state_incentive_portals_have_real_urls():
    for p in STATE_INCENTIVE_PORTALS:
        assert p.url.startswith("https://")
        assert p.note


def test_general_lenders_section_includes_score():
    names = [p.name for p in GENERAL_LENDERS]
    assert any("SCORE" in n for n in names)


def test_no_entry_is_empty():
    for group in (SBA_PROGRAMS, STATE_INCENTIVE_PORTALS, GENERAL_LENDERS):
        for entry in group:
            assert entry.name
            assert entry.note
