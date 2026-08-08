"""real_estate_strategy.py — free, deterministic financing/closing-strategy
suggestions for a real estate lead.

Kevin, 2026-07-29: "I need the bot to find ways for me to secure deals" —
this is what feeds the #secure-deals channel: a small keyword-rule table
mapping distress-language signals in a listing's own text to a suggested
strategy. Deterministic and local — no paid API, matching "the easiest
and free path is most needed."
"""
from __future__ import annotations


__all__ = ["suggest_strategy"]


# Ordered most-specific-first: the first matching signal wins, so a
# listing mentioning both "pre-foreclosure" and "as-is" gets the more
# actionable subject-to suggestion rather than the generic fallback.
_STRATEGY_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("pre-foreclosure", "behind on payments", "facing foreclosure", "notice of default"),
     "Subject-to candidate — take over the existing mortgage payments rather than "
     "financing a new one; the seller avoids foreclosure on their credit."),
    (("inherited", "estate sale", "probate"),
     "Seller financing candidate — an heir with no mortgage of their own on the "
     "property is often open to carrying the note, no bank involved."),
    (("divorce",),
     "Seller financing or quick-cash-close candidate — a divorce sale usually "
     "prioritizes a fast, simple close over top dollar."),
    (("as-is", "needs work", "fixer", "tlc", "handyman special"),
     "Hard-money + BRRRR candidate — a short-term rehab loan, then refinance into "
     "a long-term mortgage once repairs raise the value."),
    (("motivated seller", "must sell", "priced to sell", "quick sale", "cash only"),
     "Conventional or cash-close candidate — the seller is already primed for "
     "speed; a clean, fast conventional offer often wins here."),
)

_DEFAULT_STRATEGY = (
    "No strong distress signal in the listing text — treat as a standard "
    "conventional purchase until a real comp/appraisal says otherwise."
)


def suggest_strategy(text: str, analysis=None) -> str:
    """A one-line, deterministic strategy suggestion from the listing's
    own text. `analysis` (a `real_estate_deal_analyzer.DealAnalysis`, if
    given) only adjusts the closing note when its "mid" scenario cash
    flow is negative — never overrides the distress-signal match itself."""
    lowered = (text or "").lower()
    strategy = _DEFAULT_STRATEGY
    for keywords, suggestion in _STRATEGY_RULES:
        if any(kw in lowered for kw in keywords):
            strategy = suggestion
            break

    if analysis is not None:
        mid = next((s for s in analysis.scenarios if s.scenario.label == "mid"), None)
        if mid is not None and mid.monthly_cash_flow < 0:
            strategy += (
                " Caution: at the mid rent estimate this doesn't cash-flow "
                "as a rental at current terms — re-check rent comps or the offer price."
            )
    return strategy
