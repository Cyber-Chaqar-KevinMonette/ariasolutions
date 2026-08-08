"""warframe-flip-d (Kevin, 2026-07-27): WarframeFlipFetcher — the I/O
wrapper around warframe_market.py's pure logic. Injectable opener
throughout, matching every other fetcher's testability pattern this
session — no real network in this suite (a real, live smoke test was
run manually and found genuine opportunities on the first try, but that
stays outside the deterministic test suite).

Refined after Kevin: "Well I wanted a whole warframe category, with
channels for item types" — each Source now scans exactly ONE category,
carried in `source.url` ("set" | "relic" | "arcane" | "riven"), so each
item type gets its own channel + its own independent rotation.
"""
from __future__ import annotations

import json

from sovereign_agent.discord_runtime.fetchers import WarframeFlipFetcher
from sovereign_agent.discord_runtime.sources import Source


class _Resp:
    def __init__(self, payload):
        self._data = json.dumps(payload).encode()
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def read(self): return self._data


ITEMS_PAYLOAD = {"data": [
    {"id": "set1", "slug": "frost_prime_set", "tags": ["set", "prime"],
     "i18n": {"en": {"name": "Frost Prime Set"}}},
    {"id": "part1", "slug": "frost_prime_neuroptics", "tags": ["component", "prime"],
     "i18n": {"en": {"name": "Frost Prime Neuroptics"}}},
    {"id": "relic1", "slug": "requiem_iv_relic", "tags": ["relic"], "vaulted": True,
     "i18n": {"en": {"name": "Requiem IV Relic"}}},
    {"id": "arcane1", "slug": "arcane_energize", "tags": ["arcane_enhancement"],
     "i18n": {"en": {"name": "Arcane Energize"}}},
]}

RIVEN_WEAPONS_PAYLOAD = {"data": [
    {"slug": "vectis", "disposition": 1.15, "i18n": {"en": {"name": "Vectis"}}},
]}


def _routing_opener(routes: dict):
    """routes: {url_substring: payload_dict}. Matches the FIRST
    substring found in the requested URL."""
    def opener(url, timeout):
        for needle, payload in routes.items():
            if needle in url:
                return _Resp(payload)
        return _Resp({"data": []})
    return opener


def _src(category: str) -> Source:
    return Source(name=f"wf-flip-{category}", url=category, kind="warframe-flip")


def _embed_blob(item) -> str:
    """panel-d (Kevin, 2026-07-27): buyer/seller names + status now live
    in the rich embed, not the short `.text` line — flatten the embed
    to one searchable string for tests that just want "is X mentioned
    somewhere in this alert"."""
    return json.dumps(item.embed or {})


def test_fetch_rejects_an_unknown_category(tmp_path):
    fetcher = WarframeFlipFetcher(opener=lambda *a, **k: _Resp({"data": []}),
                                  data_dir=tmp_path)
    assert fetcher.fetch(Source(name="x", url="", kind="warframe-flip")) == []
    assert fetcher.fetch(Source(name="x", url="nonsense", kind="warframe-flip")) == []


def test_fetch_builds_the_cache_on_first_call(tmp_path):
    opener = _routing_opener({
        "/v2/items": ITEMS_PAYLOAD,
        "/v2/riven/weapons": RIVEN_WEAPONS_PAYLOAD,
        "/v2/orders/item/": {"data": []},
        "/v2/item/frost_prime_set": {"data": {"setParts": []}},
    })
    fetcher = WarframeFlipFetcher(opener=opener, data_dir=tmp_path, batch_size=10)
    fetcher.fetch(_src("set"))

    cache = json.loads((tmp_path / "warframe_market" / "cache.json").read_text())
    assert len(cache["sets"]) == 1 and cache["sets"][0]["slug"] == "frost_prime_set"
    assert len(cache["relics"]) == 1 and cache["relics"][0]["slug"] == "requiem_iv_relic"
    assert len(cache["arcanes"]) == 1
    assert len(cache["riven_weapons"]) == 1
    assert cache["riven_weapons"][0]["disposition"] == 1.15


def test_a_set_source_never_touches_the_relic_pool(tmp_path):
    """Kevin's whole point: each channel scans its OWN item type."""
    orders_calls = []
    def opener(url, timeout):
        if "/v2/items" in url:
            return _Resp(ITEMS_PAYLOAD)
        if "/v2/riven/weapons" in url:
            return _Resp(RIVEN_WEAPONS_PAYLOAD)
        if "/v2/item/frost_prime_set" in url:
            return _Resp({"data": {"setParts": []}})
        if "/orders/item/" in url:
            orders_calls.append(url)
        return _Resp({"data": []})
    fetcher = WarframeFlipFetcher(opener=opener, data_dir=tmp_path, batch_size=10)
    fetcher.fetch(_src("set"))
    assert any("frost_prime_set" in u for u in orders_calls)
    assert not any("requiem_iv_relic" in u for u in orders_calls)
    assert not any("arcane_energize" in u for u in orders_calls)


def test_fetch_finds_a_real_arbitrage_opportunity(tmp_path):
    orders_payload = {"data": [
        {"id": "s1", "type": "sell", "platinum": 20, "visible": True,
         "updatedAt": "2026-07-26T00:00:00Z",
         "user": {"ingameName": "Seller", "status": "online"}},
        {"id": "b1", "type": "buy", "platinum": 35, "visible": True,
         "updatedAt": "2026-07-26T00:00:00Z",
         "user": {"ingameName": "Buyer", "status": "ingame"}},
    ]}
    opener = _routing_opener({
        "/v2/items": ITEMS_PAYLOAD,
        "/v2/riven/weapons": RIVEN_WEAPONS_PAYLOAD,
        "/v2/item/frost_prime_set": {"data": {"setParts": []}},
        "/v2/orders/item/frost_prime_set": orders_payload,
    })
    fetcher = WarframeFlipFetcher(opener=opener, data_dir=tmp_path, batch_size=10)
    items = fetcher.fetch(_src("set"))

    hits = [i for i in items if "Frost Prime Set" in i.text]
    assert len(hits) == 1
    blob = _embed_blob(hits[0])
    assert "Seller" in blob and "Buyer" in blob
    assert "15p profit" in hits[0].text
    assert hits[0].url == "https://warframe.market/items/frost_prime_set"
    assert hits[0].embed is not None and hits[0].embed["title"]


def test_fetch_finds_a_set_vs_parts_opportunity(tmp_path):
    set_orders = {"data": [
        {"id": "set-sell", "type": "sell", "platinum": 60, "visible": True,
         "updatedAt": "2026-07-26T00:00:00Z",
         "user": {"ingameName": "SetSeller", "status": "online"}},
    ]}
    part_orders = {"data": [
        {"id": "part-sell", "type": "sell", "platinum": 15, "visible": True,
         "updatedAt": "2026-07-26T00:00:00Z",
         "user": {"ingameName": "PartSeller", "status": "online"}},
    ]}
    opener = _routing_opener({
        "/v2/items": ITEMS_PAYLOAD,
        "/v2/riven/weapons": RIVEN_WEAPONS_PAYLOAD,
        "/v2/item/frost_prime_set": {"data": {"setParts": ["part1"]}},
        "/v2/orders/item/frost_prime_set": set_orders,
        "/v2/orders/item/frost_prime_neuroptics": part_orders,
    })
    fetcher = WarframeFlipFetcher(opener=opener, data_dir=tmp_path, batch_size=10)
    items = fetcher.fetch(_src("set"))

    hits = [i for i in items if "set-vs-parts" in i.id]
    assert len(hits) == 1
    assert "PartSeller" in _embed_blob(hits[0])
    assert "45p profit" in hits[0].text


def test_fetch_finds_a_relic_opportunity(tmp_path):
    relic_orders = {"data": [
        {"id": "r1", "type": "sell", "subtype": "radiant", "platinum": 10,
         "visible": True, "updatedAt": "2026-07-26T00:00:00Z",
         "user": {"ingameName": "RelicSeller", "status": "online"}},
        {"id": "r2", "type": "buy", "subtype": "radiant", "platinum": 25,
         "visible": True, "updatedAt": "2026-07-26T00:00:00Z",
         "user": {"ingameName": "RelicBuyer", "status": "ingame"}},
    ]}
    opener = _routing_opener({
        "/v2/items": ITEMS_PAYLOAD,
        "/v2/riven/weapons": RIVEN_WEAPONS_PAYLOAD,
        "/v2/orders/item/requiem_iv_relic": relic_orders,
    })
    fetcher = WarframeFlipFetcher(opener=opener, data_dir=tmp_path, batch_size=10)
    items = fetcher.fetch(_src("relic"))

    hits = [i for i in items if "Requiem IV Relic" in i.text]
    assert len(hits) == 1
    blob = _embed_blob(hits[0])
    assert "RelicSeller" in blob and "RelicBuyer" in blob


def test_fetch_finds_a_rank0_arcane_opportunity(tmp_path):
    # warframe-arcane-ranks-d (Kevin, 2026-07-27): "rank 0 flips, mid
    # flips, and rank 5 flips" — three independent channels/scopes now.
    arcane_orders = {"data": [
        {"id": "a1", "type": "sell", "rank": 0, "platinum": 20, "visible": True,
         "updatedAt": "2026-07-26T00:00:00Z",
         "user": {"ingameName": "ArcSeller", "status": "online"}},
        {"id": "a2", "type": "buy", "rank": 0, "platinum": 40, "visible": True,
         "updatedAt": "2026-07-26T00:00:00Z",
         "user": {"ingameName": "ArcBuyer", "status": "ingame"}},
        # a rank 5 pair, present in the SAME item's orders — must never
        # leak into the rank-0 channel's opportunities
        {"id": "a3", "type": "sell", "rank": 5, "platinum": 200, "visible": True,
         "updatedAt": "2026-07-26T00:00:00Z",
         "user": {"ingameName": "R5Seller", "status": "online"}},
        {"id": "a4", "type": "buy", "rank": 5, "platinum": 400, "visible": True,
         "updatedAt": "2026-07-26T00:00:00Z",
         "user": {"ingameName": "R5Buyer", "status": "ingame"}},
    ]}
    opener = _routing_opener({
        "/v2/items": ITEMS_PAYLOAD,
        "/v2/riven/weapons": RIVEN_WEAPONS_PAYLOAD,
        "/v2/orders/item/arcane_energize": arcane_orders,
    })
    fetcher = WarframeFlipFetcher(opener=opener, data_dir=tmp_path, batch_size=10)
    items = fetcher.fetch(_src("arcane-rank0"))

    hits = [i for i in items if "Arcane Energize" in i.text]
    assert len(hits) == 1
    blob = _embed_blob(hits[0])
    assert "ArcSeller" in blob and "ArcBuyer" in blob
    assert "R5Seller" not in blob
    assert "Arcane R0" in hits[0].text


def test_fetch_finds_a_rank5_arcane_opportunity_separately(tmp_path):
    arcane_orders = {"data": [
        {"id": "a1", "type": "sell", "rank": 0, "platinum": 20, "visible": True,
         "updatedAt": "2026-07-26T00:00:00Z",
         "user": {"ingameName": "ArcSeller", "status": "online"}},
        {"id": "a2", "type": "buy", "rank": 0, "platinum": 40, "visible": True,
         "updatedAt": "2026-07-26T00:00:00Z",
         "user": {"ingameName": "ArcBuyer", "status": "ingame"}},
        {"id": "a3", "type": "sell", "rank": 5, "platinum": 200, "visible": True,
         "updatedAt": "2026-07-26T00:00:00Z",
         "user": {"ingameName": "R5Seller", "status": "online"}},
        {"id": "a4", "type": "buy", "rank": 5, "platinum": 400, "visible": True,
         "updatedAt": "2026-07-26T00:00:00Z",
         "user": {"ingameName": "R5Buyer", "status": "ingame"}},
    ]}
    opener = _routing_opener({
        "/v2/items": ITEMS_PAYLOAD,
        "/v2/riven/weapons": RIVEN_WEAPONS_PAYLOAD,
        "/v2/orders/item/arcane_energize": arcane_orders,
    })
    fetcher = WarframeFlipFetcher(opener=opener, data_dir=tmp_path, batch_size=10)
    items = fetcher.fetch(_src("arcane-rank5"))

    hits = [i for i in items if "Arcane Energize" in i.text]
    assert len(hits) == 1
    blob = _embed_blob(hits[0])
    assert "R5Seller" in blob and "R5Buyer" in blob
    assert "ArcSeller" not in blob
    assert "Arcane R5" in hits[0].text


def test_fetch_finds_a_mid_rank_arcane_opportunity(tmp_path):
    arcane_orders = {"data": [
        {"id": "a1", "type": "sell", "rank": 2, "platinum": 30, "visible": True,
         "updatedAt": "2026-07-26T00:00:00Z",
         "user": {"ingameName": "MidSeller", "status": "online"}},
        {"id": "a2", "type": "buy", "rank": 2, "platinum": 60, "visible": True,
         "updatedAt": "2026-07-26T00:00:00Z",
         "user": {"ingameName": "MidBuyer", "status": "ingame"}},
        {"id": "a3", "type": "sell", "rank": 0, "platinum": 5, "visible": True,
         "updatedAt": "2026-07-26T00:00:00Z",
         "user": {"ingameName": "R0Seller", "status": "online"}},
        {"id": "a4", "type": "buy", "rank": 0, "platinum": 999, "visible": True,
         "updatedAt": "2026-07-26T00:00:00Z",
         "user": {"ingameName": "R0Buyer", "status": "ingame"}},
    ]}
    opener = _routing_opener({
        "/v2/items": ITEMS_PAYLOAD,
        "/v2/riven/weapons": RIVEN_WEAPONS_PAYLOAD,
        "/v2/orders/item/arcane_energize": arcane_orders,
    })
    fetcher = WarframeFlipFetcher(opener=opener, data_dir=tmp_path, batch_size=10)
    items = fetcher.fetch(_src("arcane-mid"))

    hits = [i for i in items if "Arcane Energize" in i.text]
    assert len(hits) == 1
    blob = _embed_blob(hits[0])
    assert "MidSeller" in blob and "MidBuyer" in blob
    assert "R0Seller" not in blob
    assert "Arcane R1-4" in hits[0].text


def test_unknown_arcane_category_is_rejected_like_any_other(tmp_path):
    opener = _routing_opener({
        "/v2/items": ITEMS_PAYLOAD,
        "/v2/riven/weapons": RIVEN_WEAPONS_PAYLOAD,
    })
    fetcher = WarframeFlipFetcher(opener=opener, data_dir=tmp_path, batch_size=10)
    # the old lumped "arcane" marker is gone — replaced by the 3 scoped ones
    assert fetcher.fetch(_src("arcane")) == []


def test_fetch_finds_a_riven_opportunity(tmp_path):
    auctions_payload = {"payload": {"auctions": [
        {"id": f"a{i}", "buyout_price": price, "starting_price": price,
         "updated": "2026-07-26T00:00:00.000+00:00",
         "owner": {"ingame_name": f"Trader{i}", "status": "online"},
         "item": {"weapon_url_name": "vectis",
                  "attributes": [{"positive": True, "url_name": "x"},
                                {"positive": True, "url_name": "y"}]}}
        for i, price in enumerate([15, 80, 82, 85, 88, 90])
    ]}}
    opener = _routing_opener({
        "/v2/items": ITEMS_PAYLOAD,
        "/v2/riven/weapons": RIVEN_WEAPONS_PAYLOAD,
        "/v1/auctions/search": auctions_payload,
    })
    fetcher = WarframeFlipFetcher(opener=opener, data_dir=tmp_path, batch_size=10)
    items = fetcher.fetch(_src("riven"))

    hits = [i for i in items if "Riven" in i.text]
    assert len(hits) == 1
    blob = _embed_blob(hits[0])
    assert "Trader0" in blob
    assert "1.15" in blob                  # the weapon's real disposition


# ── panel-d (Kevin, 2026-07-27): "present the item to buy plus the
# best people to sell it to... make each post like an advanced panel." ─
def test_embed_lists_up_to_five_real_buyers_ranked_by_price(tmp_path):
    orders_payload = {"data": [
        {"id": "s1", "type": "sell", "platinum": 10, "visible": True,
         "updatedAt": "2026-07-26T00:00:00Z",
         "user": {"ingameName": "Seller", "status": "online"}},
    ] + [
        {"id": f"b{i}", "type": "buy", "platinum": 20 + i, "visible": True,
         "updatedAt": "2026-07-26T00:00:00Z",
         "user": {"ingameName": f"Buyer{i}", "status": "ingame"}}
        for i in range(7)
    ]}
    opener = _routing_opener({
        "/v2/items": ITEMS_PAYLOAD,
        "/v2/riven/weapons": RIVEN_WEAPONS_PAYLOAD,
        "/v2/item/frost_prime_set": {"data": {"setParts": []}},
        "/v2/orders/item/frost_prime_set": orders_payload,
    })
    fetcher = WarframeFlipFetcher(opener=opener, data_dir=tmp_path, batch_size=10)
    items = fetcher.fetch(_src("set"))
    hits = [i for i in items if "Frost Prime Set" in i.text]
    assert len(hits) == 1
    sell_field = next(f for f in hits[0].embed["fields"] if "Sell to" in f["name"])
    assert "5 live buyer" in sell_field["name"]     # capped at 5, not all 7
    assert sell_field["value"].count("Buyer") == 5
    assert "Buyer6" in sell_field["value"]          # the highest-paying, first
    assert "🟢" in sell_field["value"]              # ingame status icon


def test_embed_falls_back_gracefully_when_no_buyers_are_visible(tmp_path):
    # a lowball find with NO live buy orders at all — the panel must say
    # so honestly, never invent a buyer
    orders_payload = {"data": [
        {"id": "s1", "type": "sell", "platinum": 10, "visible": True,
         "updatedAt": "2026-07-26T00:00:00Z",
         "user": {"ingameName": "Lowballer", "status": "online"}},
    ] + [
        {"id": f"p{i}", "type": "sell", "platinum": 40 + i, "visible": True,
         "updatedAt": "2026-07-26T00:00:00Z",
         "user": {"ingameName": f"Peer{i}", "status": "online"}}
        for i in range(5)
    ]}
    opener = _routing_opener({
        "/v2/items": ITEMS_PAYLOAD,
        "/v2/riven/weapons": RIVEN_WEAPONS_PAYLOAD,
        "/v2/item/frost_prime_set": {"data": {"setParts": []}},
        "/v2/orders/item/frost_prime_set": orders_payload,
    })
    fetcher = WarframeFlipFetcher(opener=opener, data_dir=tmp_path, batch_size=10)
    items = fetcher.fetch(_src("set"))
    hits = [i for i in items if "Frost Prime Set" in i.text]
    assert len(hits) == 1
    sell_field = next(f for f in hits[0].embed["fields"] if f["name"] == "📤 Sell to")
    assert "no live buyers" in sell_field["value"]
    assert "estimate" in sell_field["value"]


# ── flip-kind-d (Kevin, 2026-07-27): "everything else with active
# buyers... immediate profit should be posted and labeled quick flips"
# + "label stuff [with] no active buyers mid-long term flips" —
# nothing gets suppressed, both are posted, labeled by whether a real
# active buyer actually exists right now. ───────────────────────────────
def test_opportunity_with_active_buyers_is_labeled_quick_flip(tmp_path):
    orders_payload = {"data": [
        {"id": "s1", "type": "sell", "platinum": 20, "visible": True,
         "updatedAt": "2026-07-26T00:00:00Z",
         "user": {"ingameName": "Seller", "status": "online"}},
        {"id": "b1", "type": "buy", "platinum": 35, "visible": True,
         "updatedAt": "2026-07-26T00:00:00Z",
         "user": {"ingameName": "Buyer", "status": "ingame"}},
    ]}
    opener = _routing_opener({
        "/v2/items": ITEMS_PAYLOAD,
        "/v2/riven/weapons": RIVEN_WEAPONS_PAYLOAD,
        "/v2/item/frost_prime_set": {"data": {"setParts": []}},
        "/v2/orders/item/frost_prime_set": orders_payload,
    })
    fetcher = WarframeFlipFetcher(opener=opener, data_dir=tmp_path, batch_size=10)
    items = fetcher.fetch(_src("set"))
    hits = [i for i in items if "Frost Prime Set" in i.text]
    assert len(hits) == 1
    assert "⚡ Quick Flip" in hits[0].text
    assert "⚡ Quick Flip" in hits[0].embed["title"]
    assert "📦" not in hits[0].text


def test_opportunity_without_active_buyers_is_labeled_midlong_term_flip(tmp_path):
    orders_payload = {"data": [
        {"id": "s1", "type": "sell", "platinum": 10, "visible": True,
         "updatedAt": "2026-07-26T00:00:00Z",
         "user": {"ingameName": "Lowballer", "status": "online"}},
    ] + [
        {"id": f"p{i}", "type": "sell", "platinum": 40 + i, "visible": True,
         "updatedAt": "2026-07-26T00:00:00Z",
         "user": {"ingameName": f"Peer{i}", "status": "online"}}
        for i in range(5)
    ]}
    opener = _routing_opener({
        "/v2/items": ITEMS_PAYLOAD,
        "/v2/riven/weapons": RIVEN_WEAPONS_PAYLOAD,
        "/v2/item/frost_prime_set": {"data": {"setParts": []}},
        "/v2/orders/item/frost_prime_set": orders_payload,
    })
    fetcher = WarframeFlipFetcher(opener=opener, data_dir=tmp_path, batch_size=10)
    items = fetcher.fetch(_src("set"))
    hits = [i for i in items if "Frost Prime Set" in i.text]
    assert len(hits) == 1
    assert "📦 Mid/Long-Term Flip" in hits[0].text
    assert "📦 Mid/Long-Term Flip" in hits[0].embed["title"]
    assert "⚡" not in hits[0].text


def test_riven_opportunities_are_always_labeled_midlong_term_flip(tmp_path):
    # rivens never have a real matched buyer (no WTB-riven order type) —
    # always the honest mid/long-term label, never quick flip
    auctions_payload = {"payload": {"auctions": [
        {"id": f"a{i}", "buyout_price": price, "starting_price": price,
         "updated": "2026-07-26T00:00:00.000+00:00",
         "owner": {"ingame_name": f"Trader{i}", "status": "online"},
         "item": {"weapon_url_name": "vectis",
                  "attributes": [{"positive": True, "url_name": "x"},
                                {"positive": True, "url_name": "y"}]}}
        for i, price in enumerate([15, 80, 82, 85, 88, 90])
    ]}}
    opener = _routing_opener({
        "/v2/items": ITEMS_PAYLOAD,
        "/v2/riven/weapons": RIVEN_WEAPONS_PAYLOAD,
        "/v1/auctions/search": auctions_payload,
    })
    fetcher = WarframeFlipFetcher(opener=opener, data_dir=tmp_path, batch_size=10)
    items = fetcher.fetch(_src("riven"))
    hits = [i for i in items if "Riven" in i.text]
    assert len(hits) == 1
    assert "📦 Mid/Long-Term Flip" in hits[0].text


def test_no_opportunities_is_an_empty_list_not_an_error(tmp_path):
    opener = _routing_opener({
        "/v2/items": ITEMS_PAYLOAD,
        "/v2/riven/weapons": RIVEN_WEAPONS_PAYLOAD,
        "/v2/item/frost_prime_set": {"data": {"setParts": []}},
        "/v2/orders/item/": {"data": []},
        "/v1/auctions/search": {"payload": {"auctions": []}},
    })
    fetcher = WarframeFlipFetcher(opener=opener, data_dir=tmp_path, batch_size=10)
    assert fetcher.fetch(_src("set")) == []


def test_rotation_cursor_advances_per_category_independently(tmp_path):
    opener = _routing_opener({
        "/v2/items": ITEMS_PAYLOAD,          # 1 set, 1 relic, 1 arcane
        "/v2/riven/weapons": RIVEN_WEAPONS_PAYLOAD,   # 1 riven weapon
        "/v2/item/frost_prime_set": {"data": {"setParts": []}},
        "/v2/orders/item/": {"data": []},
        "/v1/auctions/search": {"payload": {"auctions": []}},
    })
    fetcher = WarframeFlipFetcher(opener=opener, data_dir=tmp_path, batch_size=10)
    fetcher.fetch(_src("set"))
    fetcher.fetch(_src("relic"))
    cache = json.loads((tmp_path / "warframe_market" / "cache.json").read_text())
    # each category has exactly 1 item — its own cursor wraps back to 0,
    # and the OTHER category's cursor is untouched (never even created)
    assert cache["cursors"]["set"] == 0
    assert cache["cursors"]["relic"] == 0
    assert "arcane" not in cache["cursors"]


def test_pool_refresh_is_cached_not_repeated_within_a_day(tmp_path):
    calls = {"items": 0}
    def opener(url, timeout):
        if "/v2/items" in url:
            calls["items"] += 1
            return _Resp(ITEMS_PAYLOAD)
        if "/v2/riven/weapons" in url:
            return _Resp(RIVEN_WEAPONS_PAYLOAD)
        if "/v2/item/frost_prime_set" in url:
            return _Resp({"data": {"setParts": []}})
        return _Resp({"data": []} if "orders" in url else {"payload": {"auctions": []}})
    fetcher = WarframeFlipFetcher(opener=opener, data_dir=tmp_path, batch_size=10)
    fetcher.fetch(_src("set"))
    fetcher.fetch(_src("set"))
    assert calls["items"] == 1                 # refreshed once, not on every call


def test_pool_refresh_failure_with_no_prior_cache_returns_empty(tmp_path):
    def bad_opener(url, timeout):
        raise RuntimeError("network down")
    fetcher = WarframeFlipFetcher(opener=bad_opener, data_dir=tmp_path, batch_size=10)
    assert fetcher.fetch(_src("set")) == []


def test_fetcher_for_routes_warframe_flip_kind():
    from sovereign_agent.discord_runtime.fetchers import fetcher_for
    assert isinstance(fetcher_for(_src("set")), WarframeFlipFetcher)


# ── middleman-lookup-d (Kevin, 2026-07-27): "type in items I want to
# sell... find all active buyers and list them from highest profit to
# lowest. Like a middle man loop up wizard." ────────────────────────────
def test_wf_refresh_pools_builds_a_full_searchable_item_catalog():
    from sovereign_agent.discord_runtime.fetchers import _wf_refresh_pools
    opener = _routing_opener({
        "/v2/items": ITEMS_PAYLOAD,
        "/v2/riven/weapons": RIVEN_WEAPONS_PAYLOAD,
    })
    cache = _wf_refresh_pools(opener)
    names = {it["name"] for it in cache["all_items"]}
    # every real item in the catalog, not just the curated set/relic/
    # arcane/misc subsets — the part item (component, not a "set") is
    # a real example of something the curated pools deliberately skip
    assert "Frost Prime Neuroptics" in names
    assert "Frost Prime Set" in names
    assert "Requiem IV Relic" in names
    assert "Arcane Energize" in names


def test_wf_item_search_matches_case_insensitively_and_ranks_prefix_first():
    from sovereign_agent.discord_runtime.fetchers import wf_item_search
    cache = {"all_items": [
        {"slug": "frost_prime_set", "name": "Frost Prime Set"},
        {"slug": "prime_vault", "name": "Prime Vault"},
    ]}
    hits = wf_item_search(cache, "PRIME")     # case-insensitive
    names = [h["name"] for h in hits]
    assert "Frost Prime Set" in names and "Prime Vault" in names
    assert names[0] == "Prime Vault"    # prefix match ranks before mid-string


def test_wf_item_search_empty_query_returns_nothing():
    from sovereign_agent.discord_runtime.fetchers import wf_item_search
    cache = {"all_items": [{"slug": "x", "name": "X Prime"}]}
    assert wf_item_search(cache, "") == []
    assert wf_item_search(cache, "   ") == []


def test_wf_item_search_caps_at_limit():
    from sovereign_agent.discord_runtime.fetchers import wf_item_search
    cache = {"all_items": [{"slug": f"i{i}", "name": f"Prime Item {i}"}
                          for i in range(40)]}
    assert len(wf_item_search(cache, "prime", limit=25)) == 25


def test_wf_lookup_item_fetches_real_orders_and_ranks_buyers():
    from sovereign_agent.discord_runtime.fetchers import wf_lookup_item
    orders_payload = {"data": [
        {"id": "s1", "type": "sell", "platinum": 20, "visible": True,
         "updatedAt": "2026-07-26T00:00:00Z",
         "user": {"ingameName": "Seller", "status": "online"}},
        {"id": "b1", "type": "buy", "platinum": 35, "visible": True,
         "updatedAt": "2026-07-26T00:00:00Z",
         "user": {"ingameName": "Buyer", "status": "ingame"}},
    ]}
    opener = _routing_opener({"/v2/orders/item/frost_prime_set": orders_payload})
    hits = wf_lookup_item(opener, "frost_prime_set", "Frost Prime Set")
    assert len(hits) == 1
    assert hits[0].buy_platinum == 20 and hits[0].sell_platinum == 35
    assert hits[0].sell_targets[0].ingame_name == "Buyer"


# ── jackpot-d (Kevin, 2026-07-27): "opportunities of a lifetime"
# channel — "some crazy deal... one in a lifetime chance." "Make it
# hyper intelligent and harden the system." ────────────────────────────
def test_is_jackpot_requires_a_real_buyer_not_just_a_big_estimate():
    from sovereign_agent.warframe_market import FlipOpportunity, SellTarget
    from sovereign_agent.discord_runtime.fetchers import _is_jackpot
    huge_but_estimate = FlipOpportunity(
        category="set", item_name="X", strategy="lowball",
        buy_platinum=10, sell_platinum=1000, buy_from="A", sell_is_estimate=True)
    assert _is_jackpot(huge_but_estimate) is False


def test_is_jackpot_requires_both_absolute_profit_and_ratio_floors():
    from sovereign_agent.warframe_market import FlipOpportunity, SellTarget
    from sovereign_agent.discord_runtime.fetchers import _is_jackpot
    target = SellTarget(ingame_name="Buyer", status="online", platinum=999, order_id="b1")
    # huge ratio, but tiny absolute profit — a 5p item selling for 20p
    # is a 4x multiplier but nowhere near "opportunity of a lifetime"
    tiny_absolute = FlipOpportunity(
        category="set", item_name="X", strategy="arbitrage",
        buy_platinum=5, sell_platinum=20, buy_from="A",
        sell_targets=(SellTarget("Buyer", "online", 20, "b1"),))
    assert _is_jackpot(tiny_absolute) is False
    # huge absolute profit, but weak ratio — a 500p item selling for
    # 560p is a real 60p profit but only a 1.12x multiplier, not "crazy"
    weak_ratio = FlipOpportunity(
        category="set", item_name="X", strategy="arbitrage",
        buy_platinum=500, sell_platinum=560, buy_from="A",
        sell_targets=(SellTarget("Buyer", "online", 560, "b1"),))
    assert _is_jackpot(weak_ratio) is False
    # clears both — buy 50p, sell 300p: 250p profit AND 6x ratio
    real_jackpot = FlipOpportunity(
        category="set", item_name="X", strategy="arbitrage",
        buy_platinum=50, sell_platinum=300, buy_from="A",
        sell_targets=(SellTarget("Buyer", "online", 300, "b1"),))
    assert _is_jackpot(real_jackpot) is True


def test_wf_jackpot_pool_combines_every_category_with_its_real_tag():
    from sovereign_agent.discord_runtime.fetchers import _wf_jackpot_pool
    cache = {
        "sets": [{"slug": "s1", "name": "Set 1"}],
        "relics": [{"slug": "r1", "name": "Relic 1"}],
        "arcanes": [{"slug": "a1", "name": "Arcane 1"}],
        "riven_weapons": [{"slug": "w1", "name": "Weapon 1", "disposition": 1.0}],
        "misc": [{"slug": "m1", "name": "Misc 1"}],
    }
    pool = _wf_jackpot_pool(cache)
    tags = [cat for cat, _ in pool]
    assert tags == ["set", "relic", "arcane-all", "riven", "misc"]


def test_fetch_jackpot_finds_and_labels_a_real_hardened_hit(tmp_path):
    # a genuine jackpot: buy 50p, sell 300p (6x, 250p profit, real buyer)
    set_orders = {"data": [
        {"id": "s1", "type": "sell", "platinum": 50, "visible": True,
         "updatedAt": "2026-07-26T00:00:00Z",
         "user": {"ingameName": "Seller", "status": "online"}},
        {"id": "b1", "type": "buy", "platinum": 300, "visible": True,
         "updatedAt": "2026-07-26T00:00:00Z",
         "user": {"ingameName": "BigBuyer", "status": "ingame"}},
    ]}
    opener = _routing_opener({
        "/v2/items": ITEMS_PAYLOAD,
        "/v2/riven/weapons": RIVEN_WEAPONS_PAYLOAD,
        "/v2/item/frost_prime_set": {"data": {"setParts": []}},
        "/v2/orders/item/frost_prime_set": set_orders,
    })
    fetcher = WarframeFlipFetcher(opener=opener, data_dir=tmp_path, batch_size=10)
    items = fetcher.fetch(_src("jackpot"))
    hits = [i for i in items if "Frost Prime Set" in i.text]
    assert len(hits) == 1
    assert "🎰 JACKPOT" in hits[0].text
    assert "🎰 JACKPOT" in hits[0].embed["title"]
    assert hits[0].embed["color"] == 0xFFD700


def test_fetch_jackpot_filters_out_ordinary_flips(tmp_path):
    # a real, positive-profit quick flip — but nowhere near jackpot tier
    set_orders = {"data": [
        {"id": "s1", "type": "sell", "platinum": 20, "visible": True,
         "updatedAt": "2026-07-26T00:00:00Z",
         "user": {"ingameName": "Seller", "status": "online"}},
        {"id": "b1", "type": "buy", "platinum": 35, "visible": True,
         "updatedAt": "2026-07-26T00:00:00Z",
         "user": {"ingameName": "Buyer", "status": "ingame"}},
    ]}
    opener = _routing_opener({
        "/v2/items": ITEMS_PAYLOAD,
        "/v2/riven/weapons": RIVEN_WEAPONS_PAYLOAD,
        "/v2/item/frost_prime_set": {"data": {"setParts": []}},
        "/v2/orders/item/frost_prime_set": set_orders,
    })
    fetcher = WarframeFlipFetcher(opener=opener, data_dir=tmp_path, batch_size=10)
    assert fetcher.fetch(_src("jackpot")) == []


# ── vaulted-relics-d (Kevin, 2026-07-27): "Add a vaulted relics command
# that shows all of the active warframe vaulted relics/warframes...
# What relics go to what part of the warframe." ────────────────────────
def test_wf_relic_ref_from_name_parses_real_shapes():
    from sovereign_agent.discord_runtime.fetchers import _wf_relic_ref_from_name
    assert _wf_relic_ref_from_name("Axi H3 Relic") == ("Axi", "H3")
    assert _wf_relic_ref_from_name("Requiem IV Relic") == ("Requiem", "IV")
    assert _wf_relic_ref_from_name("garbage") is None
    assert _wf_relic_ref_from_name("") is None


def test_wf_refresh_pools_captures_real_warframe_only_names():
    from sovereign_agent.discord_runtime.fetchers import _wf_refresh_pools
    items_payload = {"data": [
        {"id": "wf1", "slug": "frost_prime_set", "tags": ["set", "prime", "warframe"],
         "i18n": {"en": {"name": "Frost Prime Set"}}},
        {"id": "wp1", "slug": "vasto_prime_set", "tags": ["weapon", "prime", "set"],
         "i18n": {"en": {"name": "Vasto Prime Set"}}},
    ]}
    opener = _routing_opener({
        "/v2/items": items_payload,
        "/v2/riven/weapons": RIVEN_WEAPONS_PAYLOAD,
    })
    cache = _wf_refresh_pools(opener)
    assert cache["warframe_names"] == ["Frost Prime"]   # " Set" stripped, weapon excluded


def test_wf_relic_rewards_keeps_only_intact_state_and_caches(tmp_path):
    from sovereign_agent.discord_runtime.fetchers import _wf_relic_rewards
    calls = {"n": 0}
    drops_payload = {"relics": [
        {"tier": "Axi", "relicName": "H3", "state": "Intact",
         "rewards": [{"itemName": "Hydroid Prime Systems Blueprint"}]},
        {"tier": "Axi", "relicName": "H3", "state": "Radiant",
         "rewards": [{"itemName": "Hydroid Prime Systems Blueprint"}]},
    ]}
    def opener(url, timeout):
        calls["n"] += 1
        return _Resp(drops_payload)
    rewards = _wf_relic_rewards(opener, tmp_path)
    assert rewards == {("Axi", "H3"): ["Hydroid Prime Systems Blueprint"]}
    _wf_relic_rewards(opener, tmp_path)     # second call — cached, no re-fetch
    assert calls["n"] == 1


def test_wf_vault_map_end_to_end_real_shapes(tmp_path):
    from sovereign_agent.discord_runtime.fetchers import wf_vault_map
    items_payload = {"data": [
        {"id": "wf1", "slug": "hydroid_prime_set", "tags": ["set", "prime", "warframe"],
         "i18n": {"en": {"name": "Hydroid Prime Set"}}},
        {"id": "r1", "slug": "axi_h3_relic", "tags": ["relic"], "vaulted": True,
         "i18n": {"en": {"name": "Axi H3 Relic"}}},
        {"id": "r2", "slug": "axi_a1_relic", "tags": ["relic"], "vaulted": False,
         "i18n": {"en": {"name": "Axi A1 Relic"}}},   # NOT vaulted — must be excluded
    ]}
    drops_payload = {"relics": [
        {"tier": "Axi", "relicName": "H3", "state": "Intact",
         "rewards": [{"itemName": "Hydroid Prime Systems Blueprint"},
                    {"itemName": "Kronen Prime Blueprint"}]},
        {"tier": "Axi", "relicName": "A1", "state": "Intact",
         "rewards": [{"itemName": "Hydroid Prime Chassis Blueprint"}]},
    ]}
    def opener(url, timeout):
        if "/v2/items" in url:
            return _Resp(items_payload)
        if "/v2/riven/weapons" in url:
            return _Resp(RIVEN_WEAPONS_PAYLOAD)
        if "drops.warframestat.us" in url:
            return _Resp(drops_payload)
        return _Resp({"data": []})
    vault = wf_vault_map(opener, tmp_path)
    # only the VAULTED relic's part shows up; the unvaulted Axi A1's
    # Chassis is real too, but currently farmable — not "vaulted"
    from sovereign_agent.warframe_vault import RelicRef
    assert vault == {"Hydroid Prime": {"Systems": [RelicRef("Axi", "H3")]}}
