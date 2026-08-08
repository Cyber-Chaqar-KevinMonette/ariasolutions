"""real_estate_gate.py — the narrow hook that turns a raw real-estate
lead into a decision: post it or not, with the deal math and a strategy
note attached.

Called from `discord_runtime/runtime.py` right after the existing
`is_actionable` noise filter, only for verticals whose slug starts with
"realestate-" — every other vertical's poll loop is untouched.
"""
from __future__ import annotations

import re
from typing import Optional


__all__ = ["process_real_estate_item"]

_PRICE_RE = re.compile(r"\$\s?([\d][\d,]*(?:\.\d+)?)\s?(?:k\b)?", re.IGNORECASE)


def _extract_price(text: str) -> Optional[float]:
    """A best-effort dollar figure from the listing's own text — never
    fabricated, None if nothing parses. A trailing 'k' (e.g. "$250k")
    multiplies by 1000."""
    m = _PRICE_RE.search(text or "")
    if not m:
        return None
    raw = m.group(1).replace(",", "")
    try:
        value = float(raw)
    except ValueError:
        return None
    if m.group(0).strip().lower().endswith("k"):
        value *= 1000
    return value


def process_real_estate_item(
    *, text: str, url: str, property_type: str, data_dir, requirements=None,
) -> tuple[bool, object, str]:
    """Returns (should_post, analysis_or_None, strategy_note).

    should_post is False whenever the lead doesn't clear Kevin's buy-box
    (location/price/cash-flow thresholds) or its property type isn't one
    he's asked for (property_types is empty = no filter, matches every
    type). A missing price means no deal math is possible — the item can
    still post (location/property-type gating still applies) with a
    placeholder note rather than being silently dropped."""
    from sovereign_agent import real_estate_requirements as rereq
    from sovereign_agent.real_estate_deal_analyzer import analyze_deal, estimate_rent_range
    from sovereign_agent.real_estate_strategy import suggest_strategy
    from sovereign_agent.actionability import extract_location

    if requirements is None:
        requirements = rereq.load_requirements(data_dir)

    if requirements.property_types and property_type not in requirements.property_types:
        return False, None, ""

    location = extract_location(text) or ""
    price = _extract_price(text)

    analysis = None
    if price is not None and price > 0:
        rent_low, rent_mid, rent_high = estimate_rent_range(price)
        analysis = analyze_deal(price, rent_low, rent_mid, rent_high)

    if not rereq.requirement_passes(
        data_dir=data_dir, item_location=location, price=price,
        analysis=analysis, requirements=requirements,
    ):
        return False, analysis, ""

    strategy_note = suggest_strategy(text, analysis)
    return True, analysis, strategy_note
