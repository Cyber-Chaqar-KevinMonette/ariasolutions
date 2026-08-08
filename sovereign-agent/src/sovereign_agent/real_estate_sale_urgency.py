"""sale_urgency — turn a county sale date into a LEAD WINDOW.

pre-foreclosure-d (Kevin, 2026-08-03): "do what would be best for a world
class real estate agent entering with no money."

The reframe this module encodes: a county foreclosure listing with a sale
date in the FUTURE is not an auction to bid on (that needs cash on the
day). It's a homeowner who still owns the property, is in public distress,
and has a hard deadline. That's a lead you can work with no capital.

A listing whose sale date has PASSED is worthless as a lead — the sale
happened. Measured live 2026-08-03: Christian Co. KY was serving 10
listings for a 07/27/2026 sale (already gone) alongside Montgomery Co.
TN's 3 for 08/26/2026 (live). Without this, 10 of 13 "finds" are noise.

Date formats here are the REAL ones observed on the live county pages,
not invented:
    "07/27/2026"
    "August 26th, 2026 @ 10 AM"
    "August 26, 2026 @ 10 AM"
    "August 26th, 2026, at 10:00 a.m."
"""
from __future__ import annotations

import re
from datetime import date, datetime

__all__ = [
    "parse_sale_date",
    "days_until_sale",
    "urgency",
    "is_live_lead",
    "EXPIRED", "URGENT", "WORKABLE", "EARLY",
]

EXPIRED = "expired"     # sale already happened — not a lead
URGENT = "urgent"       # <= 7 days — probably too late to work a deal
WORKABLE = "workable"   # 8-45 days — the real window
EARLY = "early"         # > 45 days — worth watching, not yet urgent

_MONTHS = {m.lower(): i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"], start=1)}

# 07/27/2026  or  7-27-26
_NUMERIC_RE = re.compile(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})\b")
# August 26th, 2026   /   Aug 26 2026   (ordinal suffix optional)
_TEXT_RE = re.compile(
    r"\b([A-Za-z]{3,9})\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b")


def parse_sale_date(text: str) -> date | None:
    """The sale date named in a listing, or None if none is parseable.

    Never raises — an unparseable date degrades to None, and callers
    treat None as "unknown, don't filter it out" rather than dropping a
    real listing over a formatting quirk.
    """
    t = (text or "").strip()
    if not t:
        return None

    m = _TEXT_RE.search(t)
    if m:
        mon = _MONTHS.get(m.group(1).lower())
        if mon is None:                       # try 3-letter abbreviation
            for name, idx in _MONTHS.items():
                if name.startswith(m.group(1).lower()[:3]):
                    mon = idx
                    break
        if mon is not None:
            try:
                return date(int(m.group(3)), mon, int(m.group(2)))
            except ValueError:
                return None

    m = _NUMERIC_RE.search(t)
    if m:
        mm, dd, yy = (int(m.group(1)), int(m.group(2)), int(m.group(3)))
        if yy < 100:                          # 26 -> 2026
            yy += 2000
        try:
            return date(yy, mm, dd)
        except ValueError:
            return None
    return None


def days_until_sale(text: str, *, today: date | None = None) -> int | None:
    """Days from `today` to the listing's sale date. Negative = past."""
    d = parse_sale_date(text)
    if d is None:
        return None
    return (d - (today or date.today())).days


def urgency(text: str, *, today: date | None = None) -> str | None:
    """Which lead window this listing falls in. None = no date found."""
    n = days_until_sale(text, today=today)
    if n is None:
        return None
    if n < 0:
        return EXPIRED
    if n <= 7:
        return URGENT
    if n <= 45:
        return WORKABLE
    return EARLY


def is_live_lead(text: str, *, today: date | None = None) -> bool:
    """Should this reach Discord at all?

    Fail OPEN on an unknown date: a listing we can't date is still shown
    (better a human glances at one extra post than a real lead is
    silently swallowed — the exact failure mode that made 23 verticals
    look 'healthy' while posting nothing).
    """
    u = urgency(text, today=today)
    return u != EXPIRED


def label(text: str, *, today: date | None = None) -> str:
    """Short human tag for the alert line."""
    n = days_until_sale(text, today=today)
    u = urgency(text, today=today)
    if u is None:
        return "📅 sale date unknown"
    if u == EXPIRED:
        return f"⚰️ sale passed {abs(n)}d ago"
    if u == URGENT:
        return f"🚨 {n}d to sale — likely too late to work"
    if u == WORKABLE:
        return f"🔥 {n}d to sale — owner still owns it, contactable"
    return f"👀 {n}d out — watch"
