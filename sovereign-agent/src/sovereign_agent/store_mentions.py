"""store_mentions.py — 📍 pull location clues from a find (honestly).

Kevin's ask (2026-07-17): "note which Targets are receiving drops,
closest→farthest from my location, and the address of each."

The HONEST split:
  • What we CAN do now, truthfully: community restock posts often name the
    store in free text ("Clarksville Target", "Target on Fort Campbell
    Blvd", "store #1234"). We DETECT and surface those mentions, and give
    the retailer's store-locator link so a member finds the exact address
    + hours for their own area.
  • What needs an API key (deferred, NEVER faked): the real per-store
    address of every Target getting a drop, sorted closest→farthest from
    a member's location. That requires Target's store-locator API +
    geocoding. Until a key is vaulted, we say so plainly and do not
    invent addresses — inventing them would violate her honesty kernel.

This module does the honest part + leaves a clean seam
(`rank_stores_by_distance`) for the API upgrade.
"""
from __future__ import annotations

import re

# "Target on/at/in <Place>" — capture up to 3 Capitalized words (a
# street/city name), stopping at the first lowercase word.
_ON_AT = re.compile(
    r"\b(?:target|walmart|best ?buy|gamestop|costco|dollar general)\s+"
    r"(?:on|at|in|near)\s+((?:[A-Z][A-Za-z.]+\s?){1,3})", re.I)
# "<City> Target" — one or two Capitalized words immediately before the
# store word (non-greedy so the store word isn't eaten into the city).
_STORE_ALT = r"(?:[Tt]arget|[Ww]almart|[Bb]est ?[Bb]uy|[Gg]ame[Ss]top)"
_CITY_STORE = re.compile(
    r"\b([A-Z][a-z]+(?:\s(?![Tt]arget|[Ww]almart|[Bb]est|[Gg]ame)"
    r"[A-Z][a-z]+)?)\s+" + _STORE_ALT + r"\b")
_STORE_NUM = re.compile(r"\b(?:store\s*#?|#)\s*(\d{3,5})\b", re.I)
_STOP = {"the", "a", "huge", "big", "pokemon", "new", "target", "walmart",
         "today", "tonight", "now", "drop", "restock", "and", "got", "has"}


def _clean(place: str) -> str:
    # drop trailing filler words the greedy match may have grabbed
    words = [w for w in place.split() if w]
    while words and words[-1].lower() in _STOP:
        words.pop()
    return " ".join(words).strip(" .")[:30]


def detect_mentions(text: str) -> list[str]:
    """Location clues named in the find text. Empty when none — never a
    guess. Deduped, order-preserved."""
    t = str(text or "")
    out: list[str] = []
    for m in _ON_AT.finditer(t):
        c = _clean(m.group(1))
        if c and c.lower() not in _STOP:
            out.append(c)
    for m in _CITY_STORE.finditer(t):
        c = _clean(m.group(1))
        if c and c.lower() not in _STOP:
            out.append(c)
    for m in _STORE_NUM.finditer(t):
        out.append(f"store #{m.group(1)}")
    # dedupe, keep order
    seen, dedup = set(), []
    for x in out:
        k = x.lower()
        if k not in seen:
            seen.add(k)
            dedup.append(x)
    return dedup[:4]


def mention_line(text: str) -> str:
    """A compact '📍 location clue' line for a card — empty if none."""
    m = detect_mentions(text)
    return "📍 mentioned: " + " · ".join(m) if m else ""


def rank_stores_by_distance(mentions, member_area):  # pragma: no cover
    """SEAM for the API upgrade: given detected store mentions + a member's
    area (zip/coords), return stores sorted closest→farthest with real
    addresses. Requires the Target/Places API key — NOT built (we never
    fake addresses). Returns [] today so callers degrade honestly."""
    return []


def location_note(member_area: dict | None = None) -> str:
    """The honest status line about per-store address/distance."""
    if member_area and member_area.get("zips"):
        where = ", ".join(member_area["zips"][:3])
        return (f"📍 Nearest-store addresses + closest→farthest sorting "
                f"for {where} unlock with the Target store-locator API "
                "(coming). For now: tap any card's store-locator link.")
    return ("📍 Set ⚙ My Area (your zip) and — once the store-locator API "
            "is added — I'll list which stores near you are getting drops, "
            "closest first, with addresses. For now the card's locator link "
            "shows your store's address + hours.")


__all__ = ["detect_mentions", "mention_line", "rank_stores_by_distance",
           "location_note"]
