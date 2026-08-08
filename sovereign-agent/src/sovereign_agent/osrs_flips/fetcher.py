"""OsrsFlipFetcher — the I/O half of the OSRS flip finder.

Same split as WarframeFlipFetcher: the thinking is in osrs_market.py (pure,
no network); this does HTTP, caching, and turns Flips into Items.

One shared cache across all tiers. The three endpoints are identical no
matter which tier is being polled, so four tier-sources must NOT mean four
sets of API calls — that's rude to a free community service and buys
nothing. One refresh per CACHE_TTL_S serves every tier.

prices.runescape.wiki asks callers to identify themselves in the
User-Agent. We do, honestly, with a contact address — never spoofed, and
never a browser string we aren't.
"""
from __future__ import annotations

import json
import time
from typing import Callable

from sovereign_agent.discord_runtime.sources import Item, Source
from sovereign_agent.osrs_flips.osrs_market import (
    build_average_flips, build_flips, rank_flips)

__all__ = ["OsrsFlipFetcher", "OSRS_USER_AGENT", "API_BASE"]

API_BASE = "https://prices.runescape.wiki/api/v1/osrs"
OSRS_USER_AGENT = ("AriaScout/0.4 (Discord GE flip tracker; "
                   "contact info@ariasolutions.org)")

CACHE_TTL_S = 300.0        # the wiki refreshes ~every 5 min; matching it
_ITEMS_PER_POLL = 5        # a digestible handful, not a wall of spam

# per-tier quality floors — a starter flipper and a whale need different
# noise gates, so these are not one global threshold.
# `max_spread` is the fantasy-flip guard — the cheaper the item, the wider
# its quotes drift from what actually fills, so the starter tier needs the
# tightest leash even though it's the one chasing the biggest ROI numbers.
_TIER_RULES: dict[str, dict] = {
    # starter runs the AVERAGE engine — last-trade quotes on sub-10k items
    # are dominated by outliers (Rosemary seed showed a 10x spread from one
    # sale). Ranked on max_profit, not ROI: at these prices ROI is a big
    # noisy number attached to pennies, and profit-per-window is what
    # actually decides whether the flip was worth the click.
    "starter": {"min_volume": 500, "min_roi": 2.0, "rank": "max_profit",
                "engine": "average", "max_price": 10_000},
    "mid": {"min_volume": 1_000, "min_roi": 1.0, "rank": "max_profit",
            "max_spread": 1.5},
    "high": {"min_volume": 50, "min_roi": 0.8, "rank": "max_profit",
             "max_spread": 1.3},
    "volume": {"min_volume": 100_000, "min_roi": 0.5, "rank": "volume",
               "max_spread": 1.5},
}

_CACHE: dict[str, tuple[float, dict]] = {}


class OsrsFlipFetcher:
    """`source.url` carries the TIER ("starter" | "mid" | "high" |
    "volume") — a marker, not a URL, following the convention
    `scrape()`/`warframe_flip()` already set in verticals.py."""

    def __init__(self, opener: Callable | None = None,
                 on_outcome: Callable | None = None,
                 timeout: float = 25.0) -> None:
        self._opener = opener
        self._on_outcome = on_outcome
        self._timeout = timeout

    def _report(self, source: Source, ok: bool, detail: str) -> None:
        if self._on_outcome is None:
            return
        try:
            self._on_outcome(source.name, ok, detail)
        except Exception:  # noqa: BLE001
            pass

    def _get(self, path: str) -> dict:
        opener = self._opener
        if opener is None:
            from urllib.request import Request, urlopen

            def opener(url, timeout):  # type: ignore[misc]
                return urlopen(Request(
                    url, headers={"User-Agent": OSRS_USER_AGENT}),
                    timeout=timeout)
        with opener(f"{API_BASE}/{path}", self._timeout) as resp:  # type: ignore[misc]
            return json.loads(resp.read())

    def _cached(self, path: str, now: float) -> dict:
        hit = _CACHE.get(path)
        if hit and (now - hit[0]) < CACHE_TTL_S:
            return hit[1]
        data = self._get(path)
        _CACHE[path] = (now, data)
        return data

    def fetch(self, source: Source) -> list[Item]:
        tier = (source.url or "starter").strip().lower()
        rules = _TIER_RULES.get(tier, _TIER_RULES["starter"])
        now = time.time()
        try:
            mapping = self._cached("mapping", now)
            latest = self._cached("latest", now)
            volumes = self._cached("24h", now)
        except Exception as exc:  # noqa: BLE001 — a flaky API never kills the loop
            code = getattr(exc, "code", None)
            self._report(source, False,
                         f"HTTP {code}" if code else type(exc).__name__)
            return []

        try:
            if rules.get("engine") == "average":
                # cheap items: quote from the hourly average, not the last
                # trade — see build_average_flips() for why.
                hourly = self._cached("1h", now)
                flips = build_average_flips(
                    mapping, hourly, volumes, latest=latest,
                    min_volume=rules["min_volume"], min_roi=rules["min_roi"],
                    max_price=rules.get("max_price"))
            else:
                flips = build_flips(
                    mapping, latest, volumes, now=now,
                    min_volume=rules["min_volume"], min_roi=rules["min_roi"],
                    max_spread_ratio=rules.get("max_spread"),
                    tier=None if tier == "volume" else tier)
            flips = rank_flips(flips, by=rules["rank"])[:_ITEMS_PER_POLL]
        except Exception:  # noqa: BLE001
            self._report(source, False, "flip build failed (unexpected shape)")
            return []

        self._report(source, True, f"{len(flips)} flip(s)")
        return [Item(id=self._dedup_key(f), text=f.as_text(),
                     url=self._wiki_url(f.name), embed=self._embed(f, tier))
                for f in flips]

    # ── presentation ────────────────────────────────────────────────────
    @staticmethod
    def _dedup_key(f) -> str:
        """Re-alert when the PRICE moves, not on every poll — otherwise the
        same item reposts forever. Bucketing the margin means a genuinely
        new opportunity gets through while a static one stays quiet."""
        return f"osrs:{f.item_id}:{f.buy}:{f.sell}"

    @staticmethod
    def _wiki_url(name: str) -> str:
        from urllib.parse import quote
        return f"https://prices.runescape.wiki/osrs/item/{quote(name)}"

    @staticmethod
    def _embed(f, tier: str) -> dict:
        liq = ("⚡ very liquid" if f.volume_24h >= 100_000 else
               "✅ liquid" if f.volume_24h >= 5_000 else
               "🐌 slow — expect a wait")
        return {
            "title": f"{f.name}",
            "url": OsrsFlipFetcher._wiki_url(f.name),
            "color": 0xC9A227,
            "description": (f"**Buy** {f.buy:,} → **Sell** {f.sell:,}\n"
                            f"**+{f.margin:,} gp each** after 1% GE tax"),
            "fields": [
                {"name": "ROI", "value": f"{f.roi:.1f}%", "inline": True},
                {"name": "Buy limit", "value": f"{f.buy_limit:,}/4h",
                 "inline": True},
                {"name": "Max profit", "value": f"{f.max_profit:,} gp",
                 "inline": True},
                {"name": "24h volume", "value": f"{f.volume_24h:,}  {liq}",
                 "inline": False},
            ],
            "footer": {"text": f"OSRS · {tier} tier · prices.runescape.wiki"},
        }
