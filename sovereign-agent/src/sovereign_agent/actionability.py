"""actionability — signal vs noise, part two: CAN a member actually act on
this post right now?

Kevin (2026-07-27): "reddit is a very noisy place that doesn't give direct
purchase links or locations. Which we want post with either a purchase
link or a location per post." A discussion post with neither a real
click-through nor a location signal is noise for a deal alert — nothing a
member can act on, no matter how good the post_intent classification
looks. Deterministic, pure; never silences a post on a guess — it only
requires ONE of the two signals, and a permissive location pattern.

Scope: this gate applies to discussion-style sources (RSS feeds — Reddit,
Slickdeals) where an item is a POST ABOUT something. It does NOT apply to
`ChangeFetcher`/`HttpJsonFetcher`-sourced items — a detected page change or
a direct API listing IS the deal itself, already inherently actionable by
construction, with no "does this post have a link" question to ask.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

__all__ = ["has_purchase_link", "has_location_signal", "is_actionable",
          "extract_location"]

# hosts that are just the SOURCE talking about itself (e.g. a reddit
# permalink back to the very comments thread) — a real URL, but never a
# "purchase link."
_SELF_REFERENTIAL_HOSTS = {
    "www.reddit.com", "reddit.com", "old.reddit.com", "oauth.reddit.com",
    "slickdeals.net", "www.slickdeals.net",
}

_ZIP_RE = re.compile(r"\b\d{5}(?:-\d{4})?\b")
# intentionally permissive — never silence a real local post on a guess
_LOCATION_PHRASE_RE = re.compile(
    r"\b(near me|local pickup|localpickup|in-store only|curbside)\b",
    re.IGNORECASE)
# NOT case-insensitive: a real US state code is uppercase ("Clarksville,
# TN") — matching case-insensitively here would treat ANY ", <two
# letters>" (e.g. "talking, no location") as a false location signal.
_CITY_STATE_RE = re.compile(r"\b[A-Za-z][A-Za-z .'-]+,\s*[A-Z]{2}\b")
# stricter than _CITY_STATE_RE above: only 1-2 CAPITALIZED words right
# before ", ST" — for detection, "Available in Clarksville, TN" matching
# is fine either way; for extraction (a real geocode query), it must not
# include the lowercase filler ("Available in") the permissive detector
# is happy to swallow.
_CITY_STATE_EXTRACT_RE = re.compile(
    r"\b((?:[A-Z][a-zA-Z]+\s)?[A-Z][a-zA-Z]+,\s*[A-Z]{2})\b")


def has_purchase_link(url: str) -> bool:
    """A real click-through that isn't just the source linking back to
    itself (a bare discussion-thread permalink)."""
    if not url or not url.startswith("http"):
        return False
    try:
        host = urlparse(url).netloc.lower()
    except Exception:  # noqa: BLE001
        return False
    return bool(host) and host not in _SELF_REFERENTIAL_HOSTS


def has_location_signal(text: str) -> bool:
    """A zip code, or an obvious local-pickup / 'City, ST' phrase."""
    t = text or ""
    return bool(_ZIP_RE.search(t) or _LOCATION_PHRASE_RE.search(t)
                or _CITY_STATE_RE.search(t))


def is_actionable(text: str, url: str) -> bool:
    """Kevin's gate: a post needs EITHER a real purchase link or a
    location signal, or it's noise — suppressed before it ever becomes
    an alert."""
    return has_purchase_link(url) or has_location_signal(text)


def extract_location(text: str) -> str | None:
    """The specific, geocodable location text a post names — a zip code
    (exact) wins when present, else a 'City, ST' phrase. None when
    neither is found (a bare 'near me'/'local pickup' phrase has nothing
    a real map can place, so it's intentionally excluded here — it still
    counts for `has_location_signal`, just not for distance matching).
    location-filter-d (Kevin, 2026-07-27): "wire zip/radius location
    filtering into tracker alerts" — this is the seam geo.py matches a
    member's saved area against."""
    t = text or ""
    m = _ZIP_RE.search(t)
    if m:
        return m.group(0)[:5]      # ignore the +4 suffix for geocoding
    m = _CITY_STATE_EXTRACT_RE.search(t)
    if m:
        return m.group(1)
    return None
