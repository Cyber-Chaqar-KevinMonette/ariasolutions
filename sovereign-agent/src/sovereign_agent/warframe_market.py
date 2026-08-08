"""warframe_market.py — Warframe Market flip-finder: intelligent
arbitrage detection against the real, official warframe.market API.

Kevin (2026-07-27): "add a warframe market scraper that is intelligent.
Finding us items we can flip. Use the best flipping strategies in mind."
Real, live-verified API (api.warframe.market, no auth, built explicitly
for third-party trading tools) — a completely different, much cleaner
situation than the Target/Best Buy/Pokémon Center scraping earlier this
session: no bot-wall, no ToS conflict, no stealth browser needed here.

Four item categories, each verified live against the real API:
  • Prime SETS    — fungible, real `setParts` relation (buy every part,
                    they auto-combine, sell the assembled set).
  • RELICS        — fungible, priced by refinement (`subtype`: intact/
                    exceptional/flawless/radiant) + a `vaulted` scarcity
                    flag. "Rare relics" (Kevin's words) = vaulted +
                    flawless/radiant.
  • ARCANES       — fungible, priced by `rank` (0-5).
  • RIVEN MODS    — NOT fungible (each is a unique rolled instance); a
                    separate auction endpoint, peer-compared by weapon +
                    disposition.

Pure logic only — no network, no Discord. `WarframeFlipFetcher`
(discord_runtime/fetchers.py) is the thin I/O wrapper around this module.
Every strategy shares one liquidity/recency filter and never claims a
flip exists without enough live peer data to say so honestly.
"""
from __future__ import annotations

import statistics
import time as _time
from dataclasses import dataclass

__all__ = [
    "Order",
    "RivenAuction",
    "FlipOpportunity",
    "SellTarget",
    "parse_orders",
    "parse_riven_auctions",
    "direct_arbitrage",
    "lowball_flip",
    "set_vs_parts_flip",
    "find_opportunities",
    "lookup_opportunities",
    "riven_opportunities",
    "compose_market_report",
    "LIVE_STATUSES",
]

_STALE_DAYS = 14.0
_LOWBALL_RATIO = 0.7
_LOWBALL_MIN_PEERS = 3
_LOWBALL_PEER_WINDOW = 5
_SET_MIN_MARGIN = 10
LIVE_STATUSES = ("online", "ingame")


def _parse_iso(ts: str) -> float:
    """'2026-07-26T16:53:40Z' -> unix timestamp. Never raises."""
    try:
        import datetime
        return datetime.datetime.fromisoformat(
            (ts or "").replace("Z", "+00:00")).timestamp()
    except Exception:  # noqa: BLE001
        return 0.0


@dataclass(frozen=True)
class Order:
    order_id: str
    kind: str             # "buy" | "sell"
    platinum: int
    visible: bool
    updated_at: float     # unix timestamp
    ingame_name: str
    status: str           # "online" | "ingame" | "offline"
    reputation: int = 0
    # unifies relic `subtype` (intact/exceptional/flawless/radiant) and
    # arcane `rank` (0-5, stringified) into one grouping key — "" for
    # items with neither (Prime sets), so an intact relic is never
    # compared against a radiant one, or a rank-0 arcane against rank-5.
    variant: str = ""


@dataclass(frozen=True)
class RivenAuction:
    auction_id: str
    weapon_slug: str
    buyout_platinum: int | None
    starting_platinum: int
    ingame_name: str
    status: str
    positive_stats: int
    negative_stats: int
    updated_at: float


@dataclass(frozen=True)
class SellTarget:
    """One real, live person to sell to — panel-d (Kevin, 2026-07-27):
    "present the item to buy plus the best people to sell it to. Like
    3-5 people I can sell it to." Ranked best (highest) price first."""
    ingame_name: str
    status: str            # "online" | "ingame" | "offline"
    platinum: int
    order_id: str


_MAX_SELL_TARGETS = 5


@dataclass(frozen=True)
class FlipOpportunity:
    category: str          # "set" | "relic" | "arcane" | "riven"
    item_name: str
    strategy: str           # "arbitrage" | "lowball" | "set-vs-parts" | "riven-underpriced"
    buy_platinum: int
    sell_platinum: int
    buy_from: str           # "IngameName (status)"
    sell_to: str = ""        # "" when there's no specific counterpart order
    # panel-d (Kevin, 2026-07-27): up to _MAX_SELL_TARGETS real, live
    # buyers, ranked best price first — empty when none are visible on
    # the market right now (see `sell_is_estimate`, the graceful
    # fallback: "if no buyers are visible on the market").
    sell_targets: tuple[SellTarget, ...] = ()
    # True when `sell_platinum` is a peer-median ESTIMATE (no real live
    # buyer exists for this item right now) rather than a real order's
    # price — never silently presented as a confirmed buyer.
    sell_is_estimate: bool = False
    detail: str = ""
    order_ids: tuple = ()    # for a stable Item.id in the fetcher layer

    @property
    def profit(self) -> int:
        return self.sell_platinum - self.buy_platinum


def parse_orders(raw: list[dict], *, variant_of=None) -> list[Order]:
    """`raw` is the v2 `/orders/item/<slug>` response's `data` list.
    `variant_of(order_dict) -> str`, if given, extracts the grouping
    variant (relic subtype / arcane rank); defaults to "" (Prime sets
    carry neither)."""
    out: list[Order] = []
    for o in raw or []:
        user = o.get("user") or {}
        variant = str(variant_of(o)) if variant_of else ""
        out.append(Order(
            order_id=str(o.get("id", "")),
            kind=str(o.get("type", "")),
            platinum=int(o.get("platinum", 0) or 0),
            visible=bool(o.get("visible", False)),
            updated_at=_parse_iso(o.get("updatedAt", "")),
            ingame_name=str(user.get("ingameName", "")),
            status=str(user.get("status", "")),
            reputation=int(user.get("reputation", 0) or 0),
            variant=variant,
        ))
    return out


def parse_riven_auctions(raw: list[dict]) -> list[RivenAuction]:
    """`raw` is the v1 `/auctions/search?type=riven` response's
    `payload.auctions` list."""
    out: list[RivenAuction] = []
    for a in raw or []:
        owner = a.get("owner") or {}
        item = a.get("item") or {}
        attrs = item.get("attributes") or []
        pos = sum(1 for x in attrs if x.get("positive"))
        neg = sum(1 for x in attrs if not x.get("positive"))
        out.append(RivenAuction(
            auction_id=str(a.get("id", "")),
            weapon_slug=str(item.get("weapon_url_name", "")),
            buyout_platinum=a.get("buyout_price"),
            starting_platinum=int(a.get("starting_price", 0) or 0),
            ingame_name=str(owner.get("ingame_name", "")),
            status=str(owner.get("status", "")),
            positive_stats=pos, negative_stats=neg,
            updated_at=_parse_iso(str(a.get("updated", ""))),
        ))
    return out


def _liquid(orders: list[Order], *, now: float | None = None,
           stale_days: float = _STALE_DAYS) -> list[Order]:
    """The shared liquidity/recency filter every strategy uses: visible,
    not stale, and online/ingame ONLY.

    warframe-online-only-d (Kevin, 2026-07-27): "we want online users
    only instead of offline users" — hard-excluded here, not just
    preferred (the old behavior sorted online first but still fell back
    to an offline trader when no online one existed; that fallback is
    gone — no online seller/buyer for an item now means no opportunity
    reported for it, same as if the item had no orders at all)."""
    now = _time.time() if now is None else now
    cutoff = now - stale_days * 86400.0
    return [o for o in orders if o.visible and o.updated_at >= cutoff
           and o.status in LIVE_STATUSES]


def _group_by_variant(orders: list[Order]) -> dict[str, list[Order]]:
    groups: dict[str, list[Order]] = {}
    for o in orders:
        groups.setdefault(o.variant, []).append(o)
    return groups


def _cheapest_sell(sells: list[Order]) -> Order | None:
    """Callers already pass `_liquid()`-filtered orders (online/ingame
    only), so this is a plain price sort — no status tiebreak needed
    anymore."""
    if not sells:
        return None
    return min(sells, key=lambda o: o.platinum)


def _priciest_buy(buys: list[Order]) -> Order | None:
    if not buys:
        return None
    return max(buys, key=lambda o: o.platinum)


def _top_buyers(buys: list[Order], n: int = _MAX_SELL_TARGETS) -> list[SellTarget]:
    """panel-d: up to `n` real, live buyers, best (highest) price first."""
    ranked = sorted(buys, key=lambda o: -o.platinum)[:n]
    return [SellTarget(ingame_name=o.ingame_name, status=o.status,
                       platinum=o.platinum, order_id=o.order_id)
           for o in ranked]


def direct_arbitrage(item_name: str, orders: list[Order], *,
                     category: str = "set",
                     now: float | None = None) -> list[FlipOpportunity]:
    """Cheapest live SELL price is actually lower than the highest live
    BUY price for the same (item, variant) — rare, but a genuine
    buy-here-flip-there opportunity. panel-d (Kevin, 2026-07-27): carries
    up to 5 real live buyers, not just the single best one, so a member
    has real fallback options if the top buyer's gone quiet."""
    out: list[FlipOpportunity] = []
    for variant, group in _group_by_variant(_liquid(orders, now=now)).items():
        sell = _cheapest_sell([o for o in group if o.kind == "sell"])
        buys = [o for o in group if o.kind == "buy"]
        buy = _priciest_buy(buys)
        if sell is None or buy is None or sell.platinum >= buy.platinum:
            continue
        label = item_name + (f" ({variant})" if variant else "")
        # flip-kind-d (Kevin, 2026-07-27): a real bug caught live — the
        # TOP buyer clears `sell.platinum` (checked above), but buyers
        # 2-5 are cheaper and aren't guaranteed to; listing one that
        # doesn't would be a "sell to" option that's actually a loss.
        # Every target here must genuinely profit over the buy-in cost.
        targets = _top_buyers([o for o in buys if o.platinum > sell.platinum])
        out.append(FlipOpportunity(
            category=category, item_name=label, strategy="arbitrage",
            buy_platinum=sell.platinum, sell_platinum=buy.platinum,
            buy_from=f"{sell.ingame_name} ({sell.status})",
            sell_to=f"{buy.ingame_name} ({buy.status})",
            sell_targets=tuple(targets), sell_is_estimate=False,
            detail=f"buy from {sell.ingame_name} @ {sell.platinum}p, "
                   f"sell to {buy.ingame_name} @ {buy.platinum}p",
            order_ids=(sell.order_id, buy.order_id)))
    return out


def lowball_flip(item_name: str, orders: list[Order], *, category: str = "set",
                 ratio: float = _LOWBALL_RATIO, min_peers: int = _LOWBALL_MIN_PEERS,
                 now: float | None = None) -> list[FlipOpportunity]:
    """The cheapest live sell sits well below the median of its own
    peers — a real steal relative to its own market, never a guess (needs
    `min_peers` real peers before "median" means anything).

    panel-d (Kevin, 2026-07-27): "present the item to buy plus the best
    people to sell it to... with graceful fallback if no buyers are
    visible." A lowball find has no guaranteed buyer by construction (it
    only needs peer SELL listings), so real live BUY orders for the same
    (item, variant) are checked too — when any exist, up to 5 become
    `sell_targets` and `sell_platinum` becomes their real top price
    (never a guess once a real buyer exists). When none exist, the
    peer-median stays as an honestly-labeled ESTIMATE
    (`sell_is_estimate=True`), not a fabricated buyer."""
    out: list[FlipOpportunity] = []
    for variant, group in _group_by_variant(_liquid(orders, now=now)).items():
        sells = sorted((o for o in group if o.kind == "sell"),
                       key=lambda o: o.platinum)
        if len(sells) < min_peers + 1:
            continue
        cheapest = sells[0]
        peers = sells[1:1 + _LOWBALL_PEER_WINDOW]
        if len(peers) < min_peers:
            continue
        median_peer = statistics.median(o.platinum for o in peers)
        if median_peer <= 0 or cheapest.platinum > ratio * median_peer:
            continue
        label = item_name + (f" ({variant})" if variant else "")
        buys = [o for o in group if o.kind == "buy"]
        # flip-kind-d (Kevin, 2026-07-27): a real bug caught live — a
        # buy order can sit BELOW the cheapest sell (that's normal;
        # most items have bid < ask). Only buyers who'd actually pay
        # MORE than the buy-in cost count as a real, profitable target;
        # anything else is no different from having no buyer at all.
        targets = _top_buyers([o for o in buys if o.platinum > cheapest.platinum])
        if targets:
            sell_platinum = targets[0].platinum
            sell_is_estimate = False
            detail = (f"{cheapest.platinum}p vs {len(targets)} real live "
                     f"buyer(s), best @ {sell_platinum}p")
        else:
            sell_platinum = int(median_peer)
            sell_is_estimate = True
            detail = (f"{cheapest.platinum}p vs typical ~{median_peer:.0f}p "
                     f"among {len(peers)} peers (no live buyers right now — "
                     "estimate)")
        out.append(FlipOpportunity(
            category=category, item_name=label, strategy="lowball",
            buy_platinum=cheapest.platinum, sell_platinum=sell_platinum,
            buy_from=f"{cheapest.ingame_name} ({cheapest.status})",
            sell_to=(f"{targets[0].ingame_name} ({targets[0].status})"
                    if targets else ""),
            sell_targets=tuple(targets), sell_is_estimate=sell_is_estimate,
            detail=detail, order_ids=(cheapest.order_id,)))
    return out


def set_vs_parts_flip(set_name: str, set_orders: list[Order],
                      part_orders_by_id: dict[str, list[Order]], *,
                      min_margin: int = _SET_MIN_MARGIN,
                      now: float | None = None) -> FlipOpportunity | None:
    """Sum of every real `setParts` member's cheapest live sell vs. the
    set's own cheapest live sell — buy every part (they auto-combine),
    sell the assembled set. Only fires when EVERY part has a live sell
    (an incomplete part market means the flip isn't actually completable
    today).

    panel-d (Kevin, 2026-07-27): checks `set_orders` for real live BUY
    orders on the ASSEMBLED set too — when any exist, up to 5 become
    `sell_targets` (a real buyer beats listing it yourself). When none
    exist, the set's own live asking price is the honest fallback
    estimate (`sell_is_estimate=True`) — "list it yourself at this
    price," never a fabricated buyer."""
    liquid_set = _liquid(set_orders, now=now)
    set_cheapest = _cheapest_sell([o for o in liquid_set if o.kind == "sell"])
    if set_cheapest is None or not part_orders_by_id:
        return None
    total_parts = 0
    part_sellers: list[tuple[str, Order]] = []
    for part_id, part_orders in part_orders_by_id.items():
        cheapest_part = _cheapest_sell(
            [o for o in _liquid(part_orders, now=now) if o.kind == "sell"])
        if cheapest_part is None:
            return None
        total_parts += cheapest_part.platinum
        part_sellers.append((part_id, cheapest_part))
    # flip-kind-d (Kevin, 2026-07-27): same fix as direct_arbitrage/
    # lowball_flip — only a buyer who'd pay MORE than the parts cost is
    # a real, profitable "sell to" option; a cheaper buy order is no
    # different from having no buyer for this flip's purposes.
    targets = _top_buyers([o for o in liquid_set
                          if o.kind == "buy" and o.platinum > total_parts])
    sell_platinum = targets[0].platinum if targets else set_cheapest.platinum
    margin = sell_platinum - total_parts
    if margin < min_margin:
        return None
    detail = ("buy parts (" +
             ", ".join(f"{c.ingame_name} @ {c.platinum}p" for _, c in part_sellers) +
             f") = {total_parts}p total, set " +
             (f"sells for {sell_platinum}p"
              if not targets else f"has a live buyer @ {sell_platinum}p"))
    return FlipOpportunity(
        category="set", item_name=set_name, strategy="set-vs-parts",
        buy_platinum=total_parts, sell_platinum=sell_platinum,
        buy_from=", ".join(c.ingame_name for _, c in part_sellers),
        sell_to=(f"{targets[0].ingame_name} ({targets[0].status})"
                if targets else ""),
        sell_targets=tuple(targets), sell_is_estimate=not targets,
        detail=detail, order_ids=tuple(c.order_id for _, c in part_sellers))


def find_opportunities(item_name: str, orders: list[Order], *, category: str,
                       set_parts_orders: dict[str, list[Order]] | None = None,
                       now: float | None = None) -> list[FlipOpportunity]:
    """Runs every strategy that applies to `category` for one item."""
    out = list(direct_arbitrage(item_name, orders, category=category, now=now))
    out += lowball_flip(item_name, orders, category=category, now=now)
    if category == "set" and set_parts_orders:
        hit = set_vs_parts_flip(item_name, orders, set_parts_orders, now=now)
        if hit is not None:
            out.append(hit)
    return out


_LOOKUP_MAX_SELL_TARGETS = 15


def lookup_opportunities(item_name: str, orders: list[Order], *,
                         category: str = "lookup",
                         now: float | None = None) -> list[FlipOpportunity]:
    """middleman-lookup-d (Kevin, 2026-07-27): "type in items I want to
    sell... find all active buyers and list them from highest profit to
    lowest. Like a middle man loop up wizard." One result per variant
    actually present (intact vs. radiant, rank 0 vs. rank 5 never
    mixed) — unlike the auto-flip strategies above, this ALWAYS reports
    what's really there (no profitability/liquidity bar to clear): the
    whole point of an on-demand lookup is "show me the real picture for
    THIS item," not "is this good enough to alert on." Reuses the same
    real-buyer ranking + honest-estimate-fallback as every push alert,
    just with more buyers shown (15, not 5 — a single on-demand query
    isn't channel-flooding the way a background alert would be)."""
    out: list[FlipOpportunity] = []
    for variant, group in _group_by_variant(_liquid(orders, now=now)).items():
        sells = [o for o in group if o.kind == "sell"]
        cheapest = _cheapest_sell(sells)
        if cheapest is None:
            continue      # nothing to buy at all for this variant
        buys = [o for o in group if o.kind == "buy"]
        targets = _top_buyers([o for o in buys if o.platinum > cheapest.platinum],
                              n=_LOOKUP_MAX_SELL_TARGETS)
        peers = [o.platinum for o in sells if o.order_id != cheapest.order_id]
        if targets:
            sell_platinum = targets[0].platinum
            sell_is_estimate = False
            detail = f"{len(targets)} real live buyer(s) beat the {cheapest.platinum}p buy-in"
        elif peers:
            sell_platinum = int(statistics.median(peers))
            sell_is_estimate = True
            detail = (f"no live buyers right now — typical resell ~{sell_platinum}p "
                     f"among {len(peers)} other live sell(s)")
        else:
            sell_platinum = cheapest.platinum
            sell_is_estimate = True
            detail = "no live buyers and no other live sells to estimate from"
        label = item_name + (f" ({variant})" if variant else "")
        out.append(FlipOpportunity(
            category=category, item_name=label, strategy="lookup",
            buy_platinum=cheapest.platinum, sell_platinum=sell_platinum,
            buy_from=f"{cheapest.ingame_name} ({cheapest.status})",
            sell_to=(f"{targets[0].ingame_name} ({targets[0].status})"
                    if targets else ""),
            sell_targets=tuple(targets), sell_is_estimate=sell_is_estimate,
            detail=detail, order_ids=(cheapest.order_id,)))
    return out


def _riven_price(a: RivenAuction) -> int | None:
    return a.buyout_platinum if a.buyout_platinum is not None else (
        a.starting_platinum or None)


def riven_opportunities(weapon_name: str, auctions: list[RivenAuction], *,
                        disposition: float = 1.0, ratio: float = _LOWBALL_RATIO,
                        min_peers: int = _LOWBALL_MIN_PEERS,
                        now: float | None = None) -> list[FlipOpportunity]:
    """Each riven is a unique rolled instance, not a fungible order-book
    item — peer-compares one weapon's live auctions against EACH OTHER,
    restricted to rolls of similar-or-better quality than the cheapest
    one (an honest net positive-vs-negative stat-count proxy, not a
    claimed full community pricing model). Weighted context via the
    weapon's real `disposition` (how sought-after its rivens generally
    are) — included in the alert, not silently discarded.

    panel-d (Kevin, 2026-07-27): stays estimate-only (`sell_is_estimate
    =True`, no `sell_targets`) by design — rivens are unique rolled
    instances, and warframe.market has no "WTB a riven with these exact
    stats" order type to match real buyers against the way sets/relics/
    arcanes' fungible order books allow. The peer median is the honest
    ceiling here, not a placeholder for something more real."""
    now = _time.time() if now is None else now
    cutoff = now - _STALE_DAYS * 86400.0
    # warframe-online-only-d (Kevin, 2026-07-27): "we want online users
    # only instead of offline users" — same hard exclusion as _liquid().
    live = [a for a in auctions if a.updated_at >= cutoff
           and a.status in LIVE_STATUSES and _riven_price(a) is not None]
    if len(live) < min_peers + 1:
        return []
    priced = sorted(live, key=lambda a: _riven_price(a))
    cheapest = priced[0]
    cheapest_quality = cheapest.positive_stats - cheapest.negative_stats
    peers = [a for a in priced[1:]
            if (a.positive_stats - a.negative_stats) >= cheapest_quality
            ][:_LOWBALL_PEER_WINDOW]
    if len(peers) < min_peers:
        return []
    median_peer = statistics.median(_riven_price(a) for a in peers)
    cheapest_price = _riven_price(cheapest)
    if median_peer <= 0 or cheapest_price > ratio * median_peer:
        return []
    return [FlipOpportunity(
        category="riven", item_name=f"{weapon_name} Riven",
        strategy="riven-underpriced",
        buy_platinum=cheapest_price, sell_platinum=int(median_peer),
        buy_from=f"{cheapest.ingame_name} ({cheapest.status})", sell_to="",
        sell_is_estimate=True,
        detail=f"{cheapest_price}p vs typical ~{median_peer:.0f}p among "
               f"{len(peers)} similar-or-better rolls (disposition "
               f"{disposition:.2f})",
        order_ids=(cheapest.auction_id,))]


def compose_market_report(arcane_prices: dict[str, int],
                          riven_prices: dict[str, int], *,
                          top_n: int = 10) -> list[dict]:
    """Discord-embed-shaped dicts, same convention as
    `shop.storefront_embeds()`. Pure: the caller resolves current prices
    from its own cache (`{display name: current price}` — cheapest live
    sell for arcanes, today's highest live buyout for rivens); this only
    ranks and formats. Kevin: "most expensive arcanes to least expensive
    ... daily most expensive rivens to least ... feel the texture of the
    market today." """
    def _rank_block(prices: dict[str, int]) -> tuple[list[tuple[str, int]],
                                                      list[tuple[str, int]]]:
        ranked = sorted(prices.items(), key=lambda kv: kv[1], reverse=True)
        highs = ranked[:top_n]
        lows = list(reversed(ranked[-top_n:])) if len(ranked) > top_n else []
        return highs, lows

    def _fmt(pairs: list[tuple[str, int]]) -> str:
        return "\n".join(f"  {i + 1}. {n} — {p}p" for i, (n, p) in enumerate(pairs))

    embeds: list[dict] = []
    if arcane_prices:
        highs, lows = _rank_block(arcane_prices)
        desc = "Most expensive:\n" + _fmt(highs)
        if lows:
            desc += "\nLeast expensive:\n" + _fmt(lows)
        embeds.append({"title": "🔷 Arcanes — today's market",
                       "description": desc, "color": 0x3FD0C9})
    if riven_prices:
        highs, lows = _rank_block(riven_prices)
        desc = "Most expensive:\n" + _fmt(highs)
        if lows:
            desc += "\nLeast expensive:\n" + _fmt(lows)
        embeds.append({"title": "🗡 Riven Mods — today's market",
                       "description": desc, "color": 0x9B59B6})
    total = len(arcane_prices) + len(riven_prices)
    embeds.append({
        "title": "🌐 Market texture",
        "description": (f"Tracking {len(arcane_prices)} arcane(s) and "
                        f"{len(riven_prices)} riven weapon(s) today — "
                        f"{total} price point(s) sampled."),
        "color": 0x95A5A6})
    return embeds
