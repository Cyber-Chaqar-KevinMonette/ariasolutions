"""osrs_market — Grand Exchange flip finder (pure logic, no I/O).

osrs-flips-d (Kevin, 2026-08-03): "add the runescape apis and design a cool
and advanced system people will enjoy to be present with and use."

Same shape as warframe_market.py: the thinking lives here (pure, injectable,
testable with no network), the I/O wrapper lives in fetchers.py.

Why this isn't naive `high - low`:

  1. **GE tax.** Since the 2021 update the seller pays a tax on each sale.
     A flip tool that ignores it reports margins that don't exist — the
     single most common way these tools lie. Rates are named constants
     below precisely because they are game rules that CHANGE; correct
     them in one place when Jagex tunes them.
  2. **Buy limits.** A 500gp margin on an item you may buy 8 of per 4
     hours is 4k, not a living. `max_profit_per_window` is what actually
     matters, and it's what we rank on.
  3. **Staleness.** `/latest` returns the last trade *whenever it
     happened*. A juicy margin quoted from 9 hours ago is fiction. Quotes
     older than MAX_QUOTE_AGE_S are refused.
  4. **Liquidity.** A huge margin with 3 trades a day is a trap — you'll
     sit on it. Both sides need real 24h volume.

Data source: prices.runescape.wiki (the RuneLite-affiliated wiki API).
Their policy requires an identifying User-Agent — honoured in the fetcher,
never spoofed.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

__all__ = [
    "Flip", "GE_TAX_RATE", "GE_TAX_EXEMPT_UNDER", "GE_TAX_CAP",
    "MAX_QUOTE_AGE_S", "TIERS",
    "ge_tax", "net_margin", "roi_pct", "max_profit_per_window",
    "capital_tier", "build_flips", "build_average_flips", "rank_flips",
]

# ── game rules (verify against the live game when Jagex tunes them) ──────
GE_TAX_RATE = 0.01            # 1% of the sale price, paid by the seller
GE_TAX_EXEMPT_UNDER = 50      # sales below this are not taxed
GE_TAX_CAP = 5_000_000        # tax never exceeds this per item

# a quote older than this is not tradeable information any more
MAX_QUOTE_AGE_S = 3600.0

# capital tiers, keyed on what ONE unit costs to buy — the real constraint
# on a player. A new account cannot flip Twisted Bows; segmenting by
# bankroll is the difference between a useful feed and a taunting one.
TIERS: dict[str, tuple[int, int]] = {
    "starter": (0, 10_000),
    "mid": (10_000, 1_000_000),
    "high": (1_000_000, 10**12),
}


def ge_tax(sale_price: int) -> int:
    """Tax the seller pays on one unit sold at `sale_price`."""
    if sale_price < GE_TAX_EXEMPT_UNDER:
        return 0
    return min(int(sale_price * GE_TAX_RATE), GE_TAX_CAP)


def net_margin(buy: int, sell: int) -> int:
    """Profit per unit after tax. Can be negative — that's real, not a bug."""
    return (sell - ge_tax(sell)) - buy


def roi_pct(buy: int, sell: int) -> float:
    """Return on capital per flip. For a small bankroll this matters far
    more than raw margin: 10% on 1k beats 0.1% on 100k when you only
    have 50k to work with."""
    if buy <= 0:
        return 0.0
    return (net_margin(buy, sell) / buy) * 100.0


def max_profit_per_window(buy: int, sell: int, buy_limit: int) -> int:
    """What this flip is actually worth per 4-hour GE window."""
    return net_margin(buy, sell) * max(0, int(buy_limit or 0))


def capital_tier(buy: int) -> str:
    for name, (lo, hi) in TIERS.items():
        if lo <= buy < hi:
            return name
    return "high"


@dataclass(frozen=True)
class Flip:
    item_id: int
    name: str
    buy: int                 # instant-sell price — what you place a buy offer at
    sell: int                # instant-buy price — what you place a sell offer at
    buy_limit: int
    volume_24h: int
    margin: int              # after tax
    roi: float
    max_profit: int
    tier: str
    members: bool = False
    icon: str = ""

    def as_text(self) -> str:
        return (f"{self.name} · buy {self.buy:,} → sell {self.sell:,} "
                f"(+{self.margin:,} after tax) · ROI {self.roi:.1f}% · "
                f"limit {self.buy_limit:,}/4h · up to {self.max_profit:,} gp")


def build_flips(mapping, latest, volumes, *, now: float | None = None,
                min_margin: int = 1, min_roi: float = 0.0,
                min_volume: int = 0,
                max_quote_age_s: float = MAX_QUOTE_AGE_S,
                max_spread_ratio: float | None = None,
                tier: str | None = None) -> list[Flip]:
    """Turn the three wiki endpoints into ranked, *tradeable* flips.

    mapping — /mapping   (list of item dicts: id, name, limit, members, icon)
    latest  — /latest    ({"data": {id: {high, highTime, low, lowTime}}})
    volumes — /24h       ({"data": {id: {highPriceVolume, lowPriceVolume}}})

    Every rejection below is a real trading reason, not defensive noise:
    a flip that survives this is one a human can actually execute.
    """
    now = time.time() if now is None else now
    latest_data = (latest or {}).get("data", {}) or {}
    vol_data = (volumes or {}).get("data", {}) or {}

    out: list[Flip] = []
    for meta in mapping or []:
        try:
            iid = int(meta.get("id"))
        except (TypeError, ValueError):
            continue
        quote = latest_data.get(str(iid)) or latest_data.get(iid)
        if not quote:
            continue
        buy, sell = quote.get("low"), quote.get("high")
        if not buy or not sell:
            continue

        # staleness — a margin quoted from hours ago is not tradeable
        oldest = min(float(quote.get("lowTime") or 0),
                     float(quote.get("highTime") or 0))
        if oldest <= 0 or (now - oldest) > max_quote_age_s:
            continue

        # fantasy-spread guard (Kevin, 2026-08-03): "Rosemary seed, buy 11
        # sell 100, ROI 800%" — a spread that wide means nobody is actually
        # trading at 11; your buy offer sits unfilled while the real volume
        # changes hands near 90. `volume` can't catch this on its own,
        # because it counts trades at ANY price, not at YOUR price. A ratio
        # far outside the item's working range is a quote artifact, not an
        # opportunity, and posting it wastes the reader's time.
        if max_spread_ratio is not None and int(buy) > 0:
            if (int(sell) / int(buy)) > max_spread_ratio:
                continue

        margin = net_margin(int(buy), int(sell))
        if margin < min_margin:
            continue
        roi = roi_pct(int(buy), int(sell))
        if roi < min_roi:
            continue

        v = vol_data.get(str(iid)) or vol_data.get(iid) or {}
        # both sides must move: you have to be able to buy AND sell
        volume = min(int(v.get("highPriceVolume") or 0),
                     int(v.get("lowPriceVolume") or 0))
        if volume < min_volume:
            continue

        t = capital_tier(int(buy))
        if tier and t != tier:
            continue

        limit = int(meta.get("limit") or 0)
        out.append(Flip(
            item_id=iid, name=str(meta.get("name") or f"item {iid}"),
            buy=int(buy), sell=int(sell), buy_limit=limit, volume_24h=volume,
            margin=margin, roi=roi,
            max_profit=max_profit_per_window(int(buy), int(sell), limit),
            tier=t, members=bool(meta.get("members")),
            icon=str(meta.get("icon") or "")))
    return out


def build_average_flips(mapping, hourly, daily, *, latest=None,
                        min_margin: int = 1, min_roi: float = 0.0,
                        min_volume: int = 0,
                        max_outlier_ratio: float = 2.5,
                        max_price: int | None = None) -> list[Flip]:
    """The CHEAP-ITEM engine (Kevin, 2026-08-03: "make another system for
    cheap items").

    `build_flips` reads /latest — the single most recent trade on each
    side. For an expensive, heavily-traded item that's fine. For a 10gp
    seed it's actively misleading: one person overpaying once sets `high`
    for hours. Measured live on Rosemary seed (id 5097):

        /latest  → high 100, low 10   (10x spread, "800% ROI")
        /1h avg  → high  40, low 20   (2x)
        /24h avg → high  25, low  9

    The 100 was ONE trade. So this engine quotes from the volume-weighted
    HOURLY AVERAGE instead, which no single sale can move, and treats the
    1h window itself as the freshness guarantee (an item absent from /1h
    simply hasn't traded this hour — skipped, not guessed at).

    Two extra guards on top:
      • both sides must have real volume IN THAT HOUR — a one-sided hour
        means you can buy but not sell, or the reverse.
      • `latest`, when supplied, must agree with the average within
        `max_outlier_ratio`. Wild disagreement means the item is being
        yanked around right now; that's volatility, not opportunity.
    """
    hourly_data = (hourly or {}).get("data", {}) or {}
    daily_data = (daily or {}).get("data", {}) or {}
    latest_data = (latest or {}).get("data", {}) or {}

    out: list[Flip] = []
    for meta in mapping or []:
        try:
            iid = int(meta.get("id"))
        except (TypeError, ValueError):
            continue
        h = hourly_data.get(str(iid)) or hourly_data.get(iid)
        if not h:
            continue                       # didn't trade this hour
        buy, sell = h.get("avgLowPrice"), h.get("avgHighPrice")
        if not buy or not sell:
            continue                       # one-sided hour
        buy, sell = int(buy), int(sell)
        if max_price is not None and buy > max_price:
            continue

        # both sides must actually have moved this hour
        volume = min(int(h.get("highPriceVolume") or 0),
                     int(h.get("lowPriceVolume") or 0))
        if volume < min_volume:
            continue

        # sanity-check the average against the live quote: if they disagree
        # wildly the item is being whipsawed right now, not sitting still
        q = latest_data.get(str(iid)) or latest_data.get(iid)
        if q and q.get("high"):
            live_high = int(q["high"])
            hi, lo = max(live_high, sell), min(live_high, sell)
            if lo > 0 and (hi / lo) > max_outlier_ratio:
                continue

        margin = net_margin(buy, sell)
        if margin < min_margin:
            continue
        roi = roi_pct(buy, sell)
        if roi < min_roi:
            continue

        d = daily_data.get(str(iid)) or daily_data.get(iid) or {}
        day_vol = min(int(d.get("highPriceVolume") or 0),
                      int(d.get("lowPriceVolume") or 0))

        limit = int(meta.get("limit") or 0)
        out.append(Flip(
            item_id=iid, name=str(meta.get("name") or f"item {iid}"),
            buy=buy, sell=sell, buy_limit=limit,
            volume_24h=day_vol or volume, margin=margin, roi=roi,
            max_profit=max_profit_per_window(buy, sell, limit),
            tier=capital_tier(buy), members=bool(meta.get("members")),
            icon=str(meta.get("icon") or "")))
    return out


def rank_flips(flips: list[Flip], *, by: str = "max_profit") -> list[Flip]:
    """Best first. `max_profit` is the honest default — it already folds in
    the buy limit, so it can't be gamed by a fat margin on an item you may
    only buy eight of. `roi` is the right lens for a small bankroll."""
    key = {"max_profit": lambda f: f.max_profit,
           "roi": lambda f: f.roi,
           "margin": lambda f: f.margin,
           "volume": lambda f: f.volume_24h}.get(by, lambda f: f.max_profit)
    return sorted(flips, key=key, reverse=True)
