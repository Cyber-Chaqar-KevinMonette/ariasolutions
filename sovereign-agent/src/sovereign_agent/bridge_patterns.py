"""bridge_patterns — one hardened matcher for all her NL bridge triggers.

Her chat bridges (self/work/health/next/journal/bots/shop/bot-health/
suggestions/credentials/…) each detect their question with trigger phrases.
Before this module, each did its own naive `phrase in text.lower()` — which
already produced one real routing bug (a suggestions trigger shadowed by the
next-report bridge) and silently missed matches when the text carried curly
quotes, unicode variants, or doubled spaces.

Now every detector goes through the same two functions:

  • `normalize(text)` — NFKC unicode fold (homoglyphs, wide chars), curly
    quotes/apostrophes → straight, casefold (stronger than lower), collapse
    all whitespace runs to single spaces.
  • `match_any(text, triggers)` — normalized substring match; the trigger
    tuple is normalized once and cached (module-level tuples make this a
    one-time cost per bridge).

Deliberately KEEPS substring semantics (not word-boundary) so behavior is
identical to before plus normalization — "the shop" still matches "the
shops", which existing bridges rely on. The routing safety comes from the
**collision matrix** in tests/test_bridge_patterns.py: every trigger phrase
of every bridge is pushed through all detectors in conversation.py's order,
and the FIRST detector to fire must be the phrase's owner — the shadowing
class of bug is now structurally impossible to reintroduce.
"""
from __future__ import annotations

import unicodedata
from functools import lru_cache

__all__ = ["normalize", "match_any"]

# curly/typographic characters that phones and editors substitute silently
_TRANSLATE = str.maketrans({
    "‘": "'", "’": "'", "‚": "'", "‛": "'",
    "“": '"', "”": '"', "„": '"',
    "–": "-", "—": "-", "−": "-",
    " ": " ",
})


def normalize(text: str) -> str:
    """The one canonical form every bridge matches against."""
    if not text:
        return ""
    t = unicodedata.normalize("NFKC", text)
    t = t.translate(_TRANSLATE)
    t = t.casefold()
    return " ".join(t.split())


@lru_cache(maxsize=256)
def _normalized_triggers(triggers: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(normalize(t) for t in triggers)


def match_any(text: str, triggers: tuple[str, ...]) -> bool:
    """True if any trigger phrase occurs in the normalized text."""
    if not text or not triggers:
        return False
    t = normalize(text)
    return any(k in t for k in _normalized_triggers(tuple(triggers)))
