"""Tests for sale_urgency — uses the REAL date strings observed live on the
Christian Co. KY and Montgomery Co. TN pages on 2026-08-03."""
from __future__ import annotations

from datetime import date

from sovereign_agent.real_estate_sale_urgency import (
    EARLY, EXPIRED, URGENT, WORKABLE, days_until_sale, is_live_lead, label,
    parse_sale_date, urgency)

TODAY = date(2026, 8, 3)

# verbatim from the live pages
CHRISTIAN = "Sale Date: 07/27/2026"
MONTGOMERY_1 = "Sale Date: August 26th, 2026 @ 10 AM"
MONTGOMERY_2 = "Sale Date: August 26th, 2026, at 10:00 a.m."
MONTGOMERY_3 = "Sale Date: August 26, 2026 @ 10 AM"


def test_parses_numeric_format():
    assert parse_sale_date(CHRISTIAN) == date(2026, 7, 27)


def test_parses_all_observed_text_formats():
    for s in (MONTGOMERY_1, MONTGOMERY_2, MONTGOMERY_3):
        assert parse_sale_date(s) == date(2026, 8, 26), s


def test_expired_listing_is_not_a_live_lead():
    """The real bug: 10 of 13 live listings were for a sale already past."""
    assert urgency(CHRISTIAN, today=TODAY) == EXPIRED
    assert is_live_lead(CHRISTIAN, today=TODAY) is False
    assert days_until_sale(CHRISTIAN, today=TODAY) == -7


def test_future_sale_is_a_workable_lead():
    assert urgency(MONTGOMERY_1, today=TODAY) == WORKABLE
    assert is_live_lead(MONTGOMERY_1, today=TODAY) is True
    assert days_until_sale(MONTGOMERY_1, today=TODAY) == 23


def test_urgency_bands():
    assert urgency("Sale Date: 08/05/2026", today=TODAY) == URGENT      # 2d
    assert urgency("Sale Date: 08/20/2026", today=TODAY) == WORKABLE    # 17d
    assert urgency("Sale Date: 12/01/2026", today=TODAY) == EARLY       # 120d


def test_unknown_date_fails_open():
    """A listing we can't date must still reach a human, never be dropped."""
    assert parse_sale_date("no date here") is None
    assert urgency("no date here", today=TODAY) is None
    assert is_live_lead("no date here", today=TODAY) is True


def test_garbage_never_raises():
    for junk in ("", None, "13/45/9999", "Sale Date: February 30th, 2026"):
        assert parse_sale_date(junk) is None
        assert is_live_lead(junk, today=TODAY) is True


def test_label_is_human_readable():
    assert "23d to sale" in label(MONTGOMERY_1, today=TODAY)
    assert "passed 7d ago" in label(CHRISTIAN, today=TODAY)
    assert "unknown" in label("nothing", today=TODAY)
