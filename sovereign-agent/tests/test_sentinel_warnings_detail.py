"""Tests for sentinel-warnings-detail-d.

Kevin, 2026-07-25: Aria said "3 sentinels are showing warnings" but
couldn't say which when asked, and /self-report gave no more detail. The
underlying data was never vague -- gather_health() already names every
sentinel -- doctor's roster check and self_report each independently
dropped everything but "the first one" (or nothing at all) before it
reached a reply. list_sentinel_warnings() is the one shared source both
now use.
"""
from __future__ import annotations

from unittest.mock import patch

from sovereign_agent.stewardship.base import HealthStatus


def _fake_healths():
    return [
        HealthStatus(sentinel_id="glyph_sentinel", level="ok", summary="clean"),
        HealthStatus(sentinel_id="canon_embodiment", level="warning", summary="2 orphaned clauses"),
        HealthStatus(sentinel_id="cache_sentinel", level="warning", summary="stale metadata"),
        HealthStatus(sentinel_id="watchdog_sentinel", level="error", summary="process not responding"),
    ]


def test_list_sentinel_warnings_names_every_flagged_one_worst_first(tmp_path):
    from sovereign_agent.stewardship.registry import list_sentinel_warnings

    with patch("sovereign_agent.stewardship.registry.gather_health", return_value=_fake_healths()):
        warns = list_sentinel_warnings(tmp_path)

    assert [w.sentinel_id for w in warns] == [
        "watchdog_sentinel", "canon_embodiment", "cache_sentinel",
    ]
    assert warns[0].level == "error"


def test_doctor_roster_check_lists_all_flagged_sentinels_not_just_first(tmp_path):
    from sovereign_agent import doctor

    with patch("sovereign_agent.stewardship.registry.gather_health", return_value=_fake_healths()), \
         patch("sovereign_agent.stewardship.registry.list_sentinel_warnings",
               return_value=[h for h in _fake_healths() if h.level != "ok"]):
        result = doctor.check_sentinels_roster()

    assert "canon_embodiment" in result.detail
    assert "cache_sentinel" in result.detail
    assert "watchdog_sentinel" in result.detail


def test_self_report_names_flagged_sentinels_when_asked_about_self(tmp_path):
    from sovereign_agent import self_report

    warns = [h for h in _fake_healths() if h.level != "ok"]
    with patch("sovereign_agent.stewardship.registry.list_sentinel_warnings", return_value=warns):
        report = self_report.compose_self_report("who are you")

    assert "canon_embodiment" in report
    assert "cache_sentinel" in report
    assert "watchdog_sentinel" in report
    assert "Currently flagged" in report


def test_self_report_says_nothing_extra_when_no_warnings(tmp_path):
    from sovereign_agent import self_report

    with patch("sovereign_agent.stewardship.registry.list_sentinel_warnings", return_value=[]):
        report = self_report.compose_self_report("who are you")

    assert "Currently flagged" not in report
