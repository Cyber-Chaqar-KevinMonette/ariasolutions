"""warframe-flip-d (Kevin, 2026-07-27): "add a warframe market scraper
that is intelligent. Finding us items we can flip. Use the best
flipping strategies in mind." + riven/arcane/relic sections + a daily
"market texture" report. All four item categories verified live against
the real api.warframe.market API before this module was written; these
tests use synthetic data shaped exactly like those real responses.
"""
from __future__ import annotations

import time

from sovereign_agent.warframe_market import (
    Order,
    RivenAuction,
    compose_market_report,
    direct_arbitrage,
    find_opportunities,
    lookup_opportunities,
    lowball_flip,
    parse_orders,
    parse_riven_auctions,
    riven_opportunities,
    set_vs_parts_flip,
)

NOW = time.time()


def _order(kind, platinum, *, variant="", status="online", visible=True,
          age_days=0.0, order_id=None, name="Trader"):
    return Order(
        order_id=order_id or f"{kind}-{platinum}-{name}",
        kind=kind, platinum=platinum, visible=visible,
        updated_at=NOW - age_days * 86400.0,
        ingame_name=name, status=status, reputation=10, variant=variant)


# ── parsing ──────────────────────────────────────────────────────────────────
def test_parse_orders_matches_the_real_v2_shape():
    raw = [{
        "id": "605271ce182f5e04000808e4", "type": "buy", "platinum": 12,
        "quantity": 1, "visible": True,
        "updatedAt": "2026-05-15T21:23:32Z",
        "user": {"ingameName": "Outlaw505", "status": "offline", "reputation": 19},
    }]
    orders = parse_orders(raw)
    assert len(orders) == 1
    o = orders[0]
    assert o.order_id == "605271ce182f5e04000808e4"
    assert o.kind == "buy" and o.platinum == 12
    assert o.ingame_name == "Outlaw505" and o.status == "offline"
    assert o.variant == ""


def test_parse_orders_extracts_variant_via_callback():
    raw = [{"id": "1", "type": "sell", "platinum": 5, "visible": True,
           "updatedAt": "2026-07-01T00:00:00Z",
           "user": {"ingameName": "A", "status": "online"}, "subtype": "radiant"}]
    orders = parse_orders(raw, variant_of=lambda o: o.get("subtype", ""))
    assert orders[0].variant == "radiant"


def test_parse_riven_auctions_matches_the_real_v1_shape():
    raw = [{
        "id": "6a642bb824cd4004f9c2efe9", "starting_price": 20, "buyout_price": 20,
        "updated": "2026-07-25T03:21:28.000+00:00",
        "owner": {"ingame_name": "wasd23121", "status": "offline"},
        "item": {"weapon_url_name": "vectis",
                 "attributes": [{"positive": True, "url_name": "damage_vs_corpus"},
                               {"positive": False, "url_name": "critical_chance"}]},
    }]
    auctions = parse_riven_auctions(raw)
    assert len(auctions) == 1
    a = auctions[0]
    assert a.weapon_slug == "vectis" and a.buyout_platinum == 20
    assert a.ingame_name == "wasd23121"
    assert a.positive_stats == 1 and a.negative_stats == 1


# ── direct arbitrage ─────────────────────────────────────────────────────────
def test_direct_arbitrage_found_when_sell_is_cheaper_than_a_live_buy():
    orders = [
        _order("sell", 20, name="Chamner"),
        _order("buy", 30, name="Outlaw505"),
    ]
    hits = direct_arbitrage("Secura Dual Cestra", orders)
    assert len(hits) == 1
    h = hits[0]
    assert h.strategy == "arbitrage"
    assert h.buy_platinum == 20 and h.sell_platinum == 30 and h.profit == 10
    assert "Chamner" in h.buy_from and "Outlaw505" in h.sell_to


def test_direct_arbitrage_not_found_when_sell_exceeds_buy():
    orders = [_order("sell", 45, name="A"), _order("buy", 12, name="B")]
    assert direct_arbitrage("X", orders) == []


def test_direct_arbitrage_ignores_stale_and_invisible_orders():
    orders = [
        _order("sell", 5, name="Stale", age_days=30),      # too old
        _order("sell", 5, name="Hidden", visible=False),   # invisible
        _order("buy", 50, name="Buyer"),
    ]
    assert direct_arbitrage("X", orders) == []


def test_direct_arbitrage_respects_variant_grouping():
    # an intact relic's cheap sell must never arbitrage against a
    # radiant relic's buy order — different real value entirely
    orders = [
        _order("sell", 3, variant="intact", name="A"),
        _order("buy", 40, variant="radiant", name="B"),
    ]
    assert direct_arbitrage("Relic", orders, category="relic") == []


# ── panel-d (Kevin, 2026-07-27): "present the item to buy plus the best
# people to sell it to. Like 3-5 people I can sell it to." ─────────────
def test_direct_arbitrage_carries_up_to_five_real_buyers_ranked_by_price():
    orders = [_order("sell", 10, name="Seller")] + [
        _order("buy", 20 + i, name=f"Buyer{i}") for i in range(7)]
    hits = direct_arbitrage("X", orders)
    assert len(hits) == 1
    targets = hits[0].sell_targets
    assert len(targets) == 5                     # capped at 5, not all 7
    assert [t.platinum for t in targets] == sorted(
        (t.platinum for t in targets), reverse=True)
    assert targets[0].platinum == 26              # the highest of the 7
    assert hits[0].sell_is_estimate is False
    assert targets[0].ingame_name == "Buyer6"


def test_direct_arbitrage_never_lists_a_buyer_priced_below_the_buy_in():
    # flip-kind-d (Kevin, 2026-07-27): live-caught real bug — a
    # "-30p profit" opportunity got posted as a Quick Flip. Buyers 2-5
    # (lower than the top one) can sit BELOW the cost basis (buy < ask
    # is normal); every listed sell_target must genuinely profit.
    orders = [
        _order("sell", 20, name="Seller"),
        _order("buy", 30, name="RealBuyer"),       # profitable — 10p profit
        _order("buy", 15, name="LosingBuyer"),     # below buy-in — must NEVER appear
        _order("buy", 5, name="BigLosingBuyer"),   # below buy-in — must NEVER appear
    ]
    hits = direct_arbitrage("X", orders)
    assert len(hits) == 1
    names = [t.ingame_name for t in hits[0].sell_targets]
    assert names == ["RealBuyer"]
    assert "LosingBuyer" not in names and "BigLosingBuyer" not in names
    assert all(t.platinum > hits[0].buy_platinum for t in hits[0].sell_targets)


def test_direct_arbitrage_sell_target_carries_real_status():
    orders = [
        _order("sell", 10, name="Seller"),
        _order("buy", 30, name="Buyer", status="ingame"),
    ]
    hits = direct_arbitrage("X", orders)
    assert hits[0].sell_targets[0].status == "ingame"


# ── warframe-online-only-d (Kevin, 2026-07-27): "we want online users
# only instead of offline users" — offline traders are hard-excluded
# now, not just deprioritized. ─────────────────────────────────────────
def test_offline_orders_are_hard_excluded_not_just_deprioritized():
    orders = [
        _order("sell", 5, status="offline", name="Sleeping"),   # cheapest, but offline
        _order("sell", 25, status="online", name="Awake"),
        _order("buy", 40, status="ingame", name="Buyer"),
    ]
    hits = direct_arbitrage("X", orders)
    assert len(hits) == 1
    # the offline seller's lower price is never used — the online one is
    assert hits[0].buy_platinum == 25 and "Awake" in hits[0].buy_from
    assert "Sleeping" not in hits[0].buy_from


def test_no_opportunity_when_only_offline_orders_exist():
    # old behavior fell back to an offline trader when no online one
    # existed; that fallback is gone — no online orders = no opportunity
    orders = [
        _order("sell", 5, status="offline", name="A"),
        _order("buy", 40, status="offline", name="B"),
    ]
    assert direct_arbitrage("X", orders) == []


# ── lowball ──────────────────────────────────────────────────────────────────
def test_lowball_flip_found_for_a_real_underpriced_listing():
    orders = [_order("sell", 10, name="Lowballer")] + [
        _order("sell", 40 + i, name=f"Peer{i}") for i in range(5)]
    hits = lowball_flip("Item", orders)
    assert len(hits) == 1
    assert hits[0].buy_platinum == 10 and hits[0].strategy == "lowball"
    assert "Lowballer" in hits[0].buy_from


def test_lowball_flip_not_found_without_enough_peers():
    orders = [_order("sell", 10, name="A"), _order("sell", 40, name="B")]
    assert lowball_flip("Item", orders) == []


def test_lowball_flip_not_found_when_price_is_reasonable():
    orders = [_order("sell", 38, name="A")] + [
        _order("sell", 40 + i, name=f"Peer{i}") for i in range(5)]
    assert lowball_flip("Item", orders) == []


def test_lowball_flip_uses_real_buyers_when_visible_on_the_market():
    # panel-d: a lowball find with REAL live buyers should never present
    # the peer-median as a guess — it's a real price from a real person
    orders = ([_order("sell", 10, name="Lowballer")]
             + [_order("sell", 40 + i, name=f"Peer{i}") for i in range(5)]
             + [_order("buy", 25, name="RealBuyer")])
    hits = lowball_flip("Item", orders)
    assert len(hits) == 1
    assert hits[0].sell_is_estimate is False
    assert hits[0].sell_platinum == 25            # the real buyer's price
    assert len(hits[0].sell_targets) == 1
    assert hits[0].sell_targets[0].ingame_name == "RealBuyer"
    assert "RealBuyer" in hits[0].sell_to


def test_lowball_flip_falls_back_to_peer_estimate_when_no_buyers_visible():
    # graceful fallback (Kevin, 2026-07-27): "if no buyers are visible
    # on the market" — never fabricates a buyer, labels it an estimate
    orders = [_order("sell", 10, name="Lowballer")] + [
        _order("sell", 40 + i, name=f"Peer{i}") for i in range(5)]
    hits = lowball_flip("Item", orders)
    assert len(hits) == 1
    assert hits[0].sell_is_estimate is True
    assert hits[0].sell_targets == ()
    assert hits[0].sell_to == ""
    assert "estimate" in hits[0].detail.lower()


def test_lowball_flip_falls_back_to_estimate_when_only_unprofitable_buyers_exist():
    # flip-kind-d: real bug — a buy order below the buy-in cost is
    # normal (bid < ask), and must never be presented as a real sell
    # target or used as sell_platinum. When that's ALL that exists,
    # this degrades to the honest peer-median estimate, not a loss.
    orders = ([_order("sell", 10, name="Lowballer")]
             + [_order("sell", 40 + i, name=f"Peer{i}") for i in range(5)]
             + [_order("buy", 8, name="LosingBuyer")])   # below the 10p buy-in
    hits = lowball_flip("Item", orders)
    assert len(hits) == 1
    assert hits[0].sell_is_estimate is True
    assert hits[0].sell_targets == ()
    assert "LosingBuyer" not in hits[0].sell_to
    assert hits[0].profit > 0


# ── set-vs-parts ─────────────────────────────────────────────────────────────
def test_set_vs_parts_flip_found_when_parts_are_cheaper_than_the_set():
    set_orders = [_order("sell", 60, name="SetSeller")]
    parts = {
        "part-a": [_order("sell", 15, name="A")],
        "part-b": [_order("sell", 12, name="B")],
        "part-c": [_order("sell", 10, name="C")],
    }
    hit = set_vs_parts_flip("Frost Prime Set", set_orders, parts)
    assert hit is not None
    assert hit.buy_platinum == 37 and hit.sell_platinum == 60
    assert hit.profit == 23
    assert "A" in hit.buy_from and "B" in hit.buy_from and "C" in hit.buy_from


def test_set_vs_parts_flip_none_when_margin_too_small():
    set_orders = [_order("sell", 40, name="SetSeller")]
    parts = {"part-a": [_order("sell", 39, name="A")]}
    assert set_vs_parts_flip("Set", set_orders, parts) is None


def test_set_vs_parts_flip_none_when_a_part_has_no_live_market():
    set_orders = [_order("sell", 100, name="SetSeller")]
    parts = {"part-a": [_order("sell", 10, name="A")], "part-b": []}
    assert set_vs_parts_flip("Set", set_orders, parts) is None


def test_set_vs_parts_flip_prefers_a_real_live_buyer_of_the_assembled_set():
    # panel-d: a real buyer of the ASSEMBLED set beats "list it yourself"
    set_orders = [_order("sell", 60, name="SetSeller"),
                 _order("buy", 70, name="SetBuyer")]
    parts = {"part-a": [_order("sell", 15, name="A")],
            "part-b": [_order("sell", 12, name="B")]}
    hit = set_vs_parts_flip("Set", set_orders, parts)
    assert hit is not None
    assert hit.sell_platinum == 70 and hit.sell_is_estimate is False
    assert hit.sell_targets[0].ingame_name == "SetBuyer"


def test_set_vs_parts_flip_estimates_from_asking_price_without_a_buyer():
    set_orders = [_order("sell", 60, name="SetSeller")]   # no buy order
    parts = {"part-a": [_order("sell", 15, name="A")],
            "part-b": [_order("sell", 12, name="B")]}
    hit = set_vs_parts_flip("Set", set_orders, parts)
    assert hit is not None
    assert hit.sell_platinum == 60 and hit.sell_is_estimate is True
    assert hit.sell_targets == ()


def test_set_vs_parts_flip_ignores_a_buyer_priced_below_parts_cost():
    # flip-kind-d: same real bug — a buy order for the set that's
    # cheaper than the parts cost must never be a "sell to" option
    set_orders = [_order("sell", 60, name="SetSeller"),
                 _order("buy", 20, name="LosingBuyer")]   # below the 27p parts cost
    parts = {"part-a": [_order("sell", 15, name="A")],
            "part-b": [_order("sell", 12, name="B")]}
    hit = set_vs_parts_flip("Set", set_orders, parts)
    assert hit is not None
    assert hit.sell_is_estimate is True and hit.sell_targets == ()
    assert hit.sell_platinum == 60             # falls back to asking price
    assert "LosingBuyer" not in hit.sell_to


# ── find_opportunities dispatcher ────────────────────────────────────────────
def test_find_opportunities_runs_set_vs_parts_only_for_sets():
    orders = [_order("sell", 60, name="S")]
    parts = {"p": [_order("sell", 5, name="P")]}
    set_hits = find_opportunities("Set", orders, category="set", set_parts_orders=parts)
    assert any(h.strategy == "set-vs-parts" for h in set_hits)
    relic_hits = find_opportunities("Relic", orders, category="relic", set_parts_orders=parts)
    assert not any(h.strategy == "set-vs-parts" for h in relic_hits)


# ── riven ────────────────────────────────────────────────────────────────────
def _riven(price, pos, neg, *, name="Trader", status="online", age_days=0.0):
    return RivenAuction(
        auction_id=f"a-{price}-{name}", weapon_slug="vectis",
        buyout_platinum=price, starting_platinum=price,
        ingame_name=name, status=status,
        positive_stats=pos, negative_stats=neg,
        updated_at=NOW - age_days * 86400.0)


def test_riven_opportunities_found_for_an_underpriced_good_roll():
    auctions = [_riven(20, pos=3, neg=1, name="Cheap")] + [
        _riven(80 + i, pos=3, neg=1, name=f"Peer{i}") for i in range(5)]
    hits = riven_opportunities("Vectis", auctions, disposition=1.15)
    assert len(hits) == 1
    assert hits[0].category == "riven" and hits[0].buy_platinum == 20
    assert "Cheap" in hits[0].buy_from
    assert "1.15" in hits[0].detail
    # panel-d (Kevin, 2026-07-27): rivens have no WTB-matching order
    # type — always an honest estimate, never a fabricated buyer
    assert hits[0].sell_is_estimate is True
    assert hits[0].sell_targets == ()


def test_riven_opportunities_ignores_peers_of_worse_quality():
    # the cheapest roll is the BEST-quality one on offer — there's no
    # real same-or-better-quality peer to compare it against, so this
    # must not fire (comparing it to worse rolls would be dishonest)
    auctions = [_riven(5, pos=4, neg=0, name="BestRoll")] + [
        _riven(50 + i, pos=0, neg=2, name=f"WorsePeer{i}") for i in range(5)]
    assert riven_opportunities("Vectis", auctions) == []


def test_riven_opportunities_needs_enough_peers():
    auctions = [_riven(10, pos=2, neg=0), _riven(50, pos=2, neg=0, name="B")]
    assert riven_opportunities("Vectis", auctions) == []


def test_riven_opportunities_excludes_offline_sellers():
    # an offline cheap roll must never be the reported "cheapest" —
    # warframe-online-only-d (Kevin, 2026-07-27)
    auctions = [_riven(5, pos=3, neg=1, name="Sleeping", status="offline")] + [
        _riven(20, pos=3, neg=1, name="Awake")] + [
        _riven(80 + i, pos=3, neg=1, name=f"Peer{i}") for i in range(5)]
    hits = riven_opportunities("Vectis", auctions, disposition=1.15)
    assert len(hits) == 1
    assert hits[0].buy_platinum == 20 and "Awake" in hits[0].buy_from


# ── middleman-lookup-d (Kevin, 2026-07-27): "type in items I want to
# sell... find all active buyers and list them from highest profit to
# lowest. Like a middle man loop up wizard." ────────────────────────────
def test_lookup_always_reports_even_without_clearing_a_profitability_bar():
    # unlike lowball_flip, a lookup isn't gated on being underpriced —
    # it just needs a real live sell to report against
    orders = [_order("sell", 40, name="OnlySeller")]
    hits = lookup_opportunities("Item", orders)
    assert len(hits) == 1
    assert hits[0].buy_platinum == 40
    assert hits[0].sell_is_estimate is True    # no peers, no buyers — honest


def test_lookup_ranks_real_buyers_highest_profit_first():
    orders = [_order("sell", 10, name="Seller")] + [
        _order("buy", 20 + i, name=f"Buyer{i}") for i in range(20)]
    hits = lookup_opportunities("Item", orders)
    assert len(hits) == 1
    targets = hits[0].sell_targets
    assert len(targets) == 15                  # capped at 15 for lookups, not 5
    assert [t.platinum for t in targets] == sorted(
        (t.platinum for t in targets), reverse=True)
    assert targets[0].ingame_name == "Buyer19"  # the highest of the 20
    assert hits[0].sell_is_estimate is False


def test_lookup_never_lists_a_buyer_priced_below_the_buy_in():
    orders = [
        _order("sell", 20, name="Seller"),
        _order("buy", 30, name="RealBuyer"),
        _order("buy", 5, name="LosingBuyer"),   # below buy-in — never listed
    ]
    hits = lookup_opportunities("Item", orders)
    names = [t.ingame_name for t in hits[0].sell_targets]
    assert "LosingBuyer" not in names


def test_lookup_estimates_from_peer_sells_when_no_buyers_exist():
    orders = [_order("sell", 10, name="Cheapest")] + [
        _order("sell", 30 + i, name=f"Peer{i}") for i in range(3)]
    hits = lookup_opportunities("Item", orders)
    assert len(hits) == 1
    assert hits[0].sell_is_estimate is True
    assert hits[0].sell_targets == ()
    assert hits[0].sell_platinum == 31          # median of the 3 peers (30,31,32)


def test_lookup_reports_each_variant_separately():
    # relics/arcanes: intact vs radiant, rank 0 vs rank 5, never mixed
    orders = [
        _order("sell", 10, variant="intact", name="A"),
        _order("sell", 50, variant="radiant", name="B"),
    ]
    hits = lookup_opportunities("Relic", orders)
    assert len(hits) == 2
    variants = {h.item_name for h in hits}
    assert variants == {"Relic (intact)", "Relic (radiant)"}


def test_lookup_reports_nothing_for_a_variant_with_no_live_sell():
    orders = [_order("buy", 50, name="Buyer")]     # a buy order, no sell at all
    assert lookup_opportunities("Item", orders) == []


# ── market report ────────────────────────────────────────────────────────────
def test_compose_market_report_ranks_most_to_least_expensive():
    arcanes = {"Arcane Energize": 90, "Arcane Ice": 5, "Arcane Guardian": 40}
    rivens = {"Vectis": 300, "Braton": 20}
    embeds = compose_market_report(arcanes, rivens)
    arcane_embed = next(e for e in embeds if "Arcanes" in e["title"])
    assert arcane_embed["description"].index("Arcane Energize") < \
        arcane_embed["description"].index("Arcane Ice")
    riven_embed = next(e for e in embeds if "Riven" in e["title"])
    assert riven_embed["description"].index("Vectis") < riven_embed["description"].index("Braton")
    texture = next(e for e in embeds if "texture" in e["title"].lower())
    assert "3 arcane" in texture["description"] and "2 riven" in texture["description"]


def test_compose_market_report_empty_inputs_still_gives_a_texture_line():
    embeds = compose_market_report({}, {})
    assert len(embeds) == 1
    assert "0 arcane" in embeds[0]["description"]
