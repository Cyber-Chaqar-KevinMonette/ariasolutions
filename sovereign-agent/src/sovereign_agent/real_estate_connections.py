"""real_estate_connections.py — "who to contact to get this flipped
immediately," matched to the strategy note `real_estate_strategy.suggest_strategy()`
already returns.

Kevin, 2026-08-01: "have the bot explain how each property can be flipped
and all the connections to get it flipped immediately." suggest_strategy()
answers the financing/closing HOW; this answers WHO. A small, curated
directory — deliberately NOT the ~60-site list Kevin pasted from another
tool's research. That list was honest that it isn't actually "200 verified/
trustworthy" resources; most of the small "wholesale marketplace" startups
in it are unverifiable SEO content, not something Aria should confidently
hand Kevin as vetted. Only platforms independently known to be real,
established, and legitimate are included here. Matches against
suggest_strategy()'s own stable output prefixes rather than re-deriving the
distress-signal keyword match, so there is exactly one source of truth for
"what category is this listing."
"""
from __future__ import annotations

from dataclasses import dataclass


__all__ = ["Connection", "suggest_connections"]


@dataclass(frozen=True)
class Connection:
    name: str
    url: str
    note: str


# Universal — useful regardless of strategy, always included.
_UNIVERSAL: tuple[Connection, ...] = (
    Connection("Craigslist (real estate > by owner)", "https://craigslist.org",
              "No login needed — post the deal or find a cash buyer directly, "
              "no marketplace fee."),
    Connection("BiggerPockets forums/marketplace", "https://www.biggerpockets.com",
              "The largest established investor community — post the deal, "
              "find local cash buyers, or ask for a strategy sanity-check."),
)

_SUBJECT_TO: tuple[Connection, ...] = (
    Connection("A real estate attorney licensed in the property's state", "",
              "Subject-to deals need a real closing/title-transfer attorney — "
              "not optional, this isn't a DIY paperwork situation."),
    Connection("Connected Investors", "https://connectedinvestors.com",
              "Large investor network with a verified private-lender directory "
              "if the subject-to structure needs a bridge."),
)

_SELLER_FINANCING: tuple[Connection, ...] = (
    Connection("A title company in the property's county", "",
              "Seller-financing notes still need a title company to handle "
              "the closing and record the deed/note properly."),
    Connection("BiggerPockets forums", "https://www.biggerpockets.com",
              "Search 'seller financing' — real investors sharing real note "
              "terms and structures they've actually closed."),
)

_BRRRR: tuple[Connection, ...] = (
    Connection("Local hard-money lenders (search '<city> hard money lender')", "",
              "Rate/terms vary a lot by market — get 2-3 real quotes before "
              "committing, don't take the first offer."),
    Connection("RealtyTrac", "https://www.realtytrac.com",
              "Comps + distressed-property data to sanity-check the ARV "
              "before the rehab budget is locked in."),
)

_CASH_CLOSE: tuple[Connection, ...] = (
    Connection("Auction.com", "https://www.auction.com",
              "Major, established foreclosure/REO auction marketplace — "
              "real bidding activity, useful for comps even if not bidding."),
    Connection("Connected Investors", "https://connectedinvestors.com",
              "Cash-buyer network — the fastest way to find someone who can "
              "actually close quickly on a clean conventional deal."),
)

_DEFAULT: tuple[Connection, ...] = (
    Connection("LoopNet", "https://www.loopnet.com",
              "For comps and market context when there's no strong distress "
              "signal yet — treat as a standard purchase until the numbers say otherwise."),
)

# Ordered most-specific-first, matched against suggest_strategy()'s own
# stable text prefixes — mirrors real_estate_strategy._STRATEGY_RULES'
# ordering discipline (first match wins) without re-deriving its keyword
# table, so there's one source of truth for "what category is this."
_CATEGORY_RULES: tuple[tuple[str, tuple[Connection, ...]], ...] = (
    ("Subject-to candidate", _SUBJECT_TO),
    ("Seller financing", _SELLER_FINANCING),
    ("Hard-money + BRRRR", _BRRRR),
    ("Conventional or cash-close", _CASH_CLOSE),
)


def suggest_connections(strategy_text: str) -> list[Connection]:
    """Real, curated contacts for the strategy suggest_strategy() already
    returned. Universal entries always included; category-specific ones
    prepended when the strategy text matches a known category prefix."""
    text = strategy_text or ""
    for prefix, connections in _CATEGORY_RULES:
        if prefix in text:
            return [*connections, *_UNIVERSAL]
    return [*_DEFAULT, *_UNIVERSAL]
