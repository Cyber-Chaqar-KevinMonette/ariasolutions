"""post_intent — signal vs noise: what is this post actually FOR?

Kevin (2026-07-18, the #retro-games observation): posts about people who
ALREADY BOUGHT things ("look what I got!") feel like noise next to live
deals. "We want AVAILABLE items, the highest-leverage deals — buying
posts, selling posts, showcase posts separated or not shown at all."

So every scout item gets an INTENT before it may post:

  AVAILABLE  — a live deal/restock a member can act on RIGHT NOW (the
               only intent tracker channels carry by default)
  SHOWCASE   — someone showing a purchase/collection (great vibes, zero
               leverage — ledgered, not posted)
  SELLING    — a person selling (FS/WTS) — networking lane, not a deal
  BUYING     — a person seeking (WTB/ISO) — networking lane
  EXPIRED    — the post itself says it's dead (OOS/expired/ended)
  UNKNOWN    — no signal either way (treated as AVAILABLE — we never
               silence a possible live deal on a guess)

Pure, deterministic, case-insensitive; first-match precedence EXPIRED >
SELLING > BUYING > SHOWCASE > AVAILABLE — a dead "deal" is dead no
matter how it's phrased, and marketplace flags beat showcase phrasing.
"""
from __future__ import annotations

import re

__all__ = ["AVAILABLE", "SHOWCASE", "SELLING", "BUYING", "EXPIRED",
           "UNKNOWN", "classify", "default_allowed", "passes_intent"]

AVAILABLE = "available"
SHOWCASE = "showcase"
SELLING = "selling"
BUYING = "buying"
EXPIRED = "expired"
UNKNOWN = "unknown"

# order matters — first hit wins within each bucket scan
_EXPIRED_PAT = (
    "expired", "out of stock", "oos", "sold out", "deal is dead", "dead deal",
    "ended", "no longer available", "price is back up", "[dead]",
)
_SELLING_PAT = (
    "[fs]", "wts", "for sale", "selling my", "taking offers", "[selling]",
    "fs/ft", "[fs/ft]",
)
_BUYING_PAT = (
    "wtb", "[wtb]", "iso ", "in search of", "looking to buy", "want to buy",
    "anyone selling",
)
_SHOWCASE_PAT = (
    "look what i", "finally got", "finally arrived", "just arrived",
    "arrived today", "my collection", "collection so far", "mail day",
    "mailday", "pickup of the", "todays pickup", "today's pickup", "haul",
    "just picked up", "i scored", "scored this", "came in the mail",
    "unboxing", "just bought", "i bought", "glad i grabbed", "my grail",
    "finally found", "found this at", "so happy with", "check out my",
)
_AVAILABLE_PAT = (
    "in stock", "restock", "back in stock", "available now", "deal:",
    "% off", "price drop", "dropped to", "on sale", "clearance", "coupon",
    "promo code", "free shipping", "lowest price", "$",
)

_WORD_RE = re.compile(r"[a-z0-9$%\[\]/':.\- ]+")


def _norm(text: str) -> str:
    text = (text or "").lower()
    return " ".join(_WORD_RE.findall(text))


def classify(text: str) -> str:
    """Intent of one post title/body snippet. Deterministic, total."""
    t = " " + _norm(text) + " "
    if any(p in t for p in _EXPIRED_PAT):
        return EXPIRED
    if any(p in t for p in _SELLING_PAT):
        return SELLING
    if any(p in t for p in _BUYING_PAT):
        return BUYING
    if any(p in t for p in _SHOWCASE_PAT):
        return SHOWCASE
    if any(p in t for p in _AVAILABLE_PAT):
        return AVAILABLE
    return UNKNOWN


def default_allowed() -> frozenset[str]:
    """What a tracker channel carries unless a source overrides:
    live deals + unknown (never silence a possible live deal on a guess)."""
    return frozenset({AVAILABLE, UNKNOWN})


def passes_intent(text: str, allowed: frozenset[str] | None = None) -> tuple[bool, str]:
    """(passes, intent) — the poll-loop gate. UNKNOWN passes by default."""
    intent = classify(text)
    allow = default_allowed() if allowed is None else allowed
    return intent in allow, intent
