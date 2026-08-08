"""Tests for scout.py — the flagship's pure brain."""
from __future__ import annotations

import json

from sovereign_agent.scout import (
    PING_MODE_BATCH,
    PING_MODE_LIVE,
    classify_lane,
    compose_scout_report,
    day_stats,
    lane_embed,
    latest_finds,
    link_for,
    live_ping_last_ts,
    load_area,
    load_ping_mode,
    load_ranks,
    mark_live_ping_checked,
    members_with_live_ping,
    nearby_finds,
    panel_embed,
    parse_area,
    rank_of,
    save_area,
    save_ping_mode,
    sort_by_value,
)


def _seed_runs(d, now=1_784_000_000.0):
    p = d / "bot_projects" / "tcg-scout"
    p.mkdir(parents=True)
    rows = [
        {"ts": now - 300, "new": [
            {"source": "slickdeals-tcg", "id": "https://sd.example/a",
             "text": "Pokemon TCG booster bundle $25 at Target"}]},
        {"ts": now - 200, "new": [
            {"source": "reddit-pkmntcgdeals", "id": "t3_abc123",
             "text": "Prismatic Evolutions ETB restock at Best Buy"}]},
        {"ts": now - 100, "new": [
            {"source": "slickdeals-etb", "id": "https://sd.example/b",
             "text": "random lego set deal"}]},
        "{broken json",
    ]
    (p / "runs.jsonl").write_text("\n".join(
        r if isinstance(r, str) else json.dumps(r) for r in rows) + "\n")
    return now


def test_ranks_greatest_to_least(tmp_path):
    ranks = load_ranks(tmp_path)
    assert (tmp_path / "bot_projects" / "tcg-scout" /
            "set_ranks.json").exists()          # seeded for Kevin to tune
    chase = rank_of("Prismatic Evolutions ETB", ranks)
    sealed = rank_of("random booster box", ranks)
    misc = rank_of("a lego set", ranks)
    assert chase < sealed < misc
    finds = [{"text": "lego", "ts": 3}, {"text": "prismatic etb", "ts": 1},
             {"text": "booster box", "ts": 2}]
    ordered = [f["text"] for f in sort_by_value(finds, ranks)]
    assert ordered == ["prismatic etb", "booster box", "lego"]


def test_lanes_and_links():
    assert classify_lane("slickdeals-tcg") == "deals"
    assert classify_lane("reddit-pkmntcgdeals") == "deals"
    assert classify_lane("bestbuy-api") == "online"
    assert classify_lane("target-local-42240") == "local"
    assert classify_lane("slickdeals-dollar-general") == "local"   # DG = go check the shelf
    assert classify_lane("reddit-dg-tcg") == "local"
    assert link_for({"id": "https://x.example/y"}) == "https://x.example/y"
    assert link_for({"id": "t3_abc"}) == "https://www.reddit.com/comments/abc"
    assert link_for({"id": "weird"}) == ""


def test_latest_finds_and_day_stats(tmp_path):
    now = _seed_runs(tmp_path)
    finds = latest_finds(tmp_path, limit=10)
    assert len(finds) == 3                      # corrupt line skipped
    assert finds[0]["text"].startswith("random lego")   # newest first
    assert all(f["lane"] == "deals" for f in finds)
    s = day_stats(tmp_path, now=now)
    assert s["total"] == 3 and s["per_lane"]["deals"] == 3
    assert "Prismatic" in s["hottest"]
    assert latest_finds(tmp_path / "nope") == []


def test_parse_area_kevins_formats():
    assert parse_area("42240") == {"zips": ["42240"], "radius_mi": None,
                                   "state": None}
    assert parse_area("42240 r50")["radius_mi"] == 50
    assert parse_area("42240, 37040")["zips"] == ["42240", "37040"]
    assert parse_area("KY")["state"] == "KY"
    assert parse_area("") is None
    assert parse_area("not an area") is None


def test_parse_area_radius_clamp_matches_kevins_comfort_range():
    """Kevin, 2026-07-26: "25 miles minimum maybe a few hundred or
    thousand maximum." """
    from sovereign_agent.scout import MAX_RADIUS_MI, MIN_RADIUS_MI

    assert MIN_RADIUS_MI == 25
    assert MAX_RADIUS_MI == 1000
    assert parse_area("42240 r10")["radius_mi"] == 25     # floored
    assert parse_area("42240 r1500")["radius_mi"] == 1000  # capped
    assert parse_area("42240 r999")["radius_mi"] == 999    # within range now


def test_area_prefs_roundtrip_and_delete(tmp_path):
    area = parse_area("42240 r50 ky")
    save_area(tmp_path, "12345", area)
    assert load_area(tmp_path, "12345") == area
    save_area(tmp_path, "12345", None)          # their data, their call
    assert load_area(tmp_path, "12345") is None


# ── ping-mode-d: two ping modes, per member ─────────────────────────────────
def test_ping_mode_defaults_to_batch(tmp_path):
    assert load_ping_mode(tmp_path, "999") == PING_MODE_BATCH


def test_ping_mode_roundtrip(tmp_path):
    save_ping_mode(tmp_path, "999", PING_MODE_LIVE)
    assert load_ping_mode(tmp_path, "999") == PING_MODE_LIVE
    save_ping_mode(tmp_path, "999", PING_MODE_BATCH)
    assert load_ping_mode(tmp_path, "999") == PING_MODE_BATCH


def test_ping_mode_and_area_coexist_in_the_same_file(tmp_path):
    area = parse_area("42240 r50")
    save_area(tmp_path, "555", area)
    save_ping_mode(tmp_path, "555", PING_MODE_LIVE)
    assert load_area(tmp_path, "555") == area
    assert load_ping_mode(tmp_path, "555") == PING_MODE_LIVE


def test_ping_mode_garbage_input_falls_back_to_batch(tmp_path):
    save_ping_mode(tmp_path, "111", "not-a-real-mode")
    assert load_ping_mode(tmp_path, "111") == PING_MODE_BATCH


# ── live ping sweep bookkeeping ─────────────────────────────────────────────
def test_live_ping_last_ts_defaults_to_none(tmp_path):
    assert live_ping_last_ts(tmp_path, "222") is None


def test_mark_live_ping_checked_roundtrip(tmp_path):
    mark_live_ping_checked(tmp_path, "222", ts=1_784_000_000.0)
    assert live_ping_last_ts(tmp_path, "222") == 1_784_000_000.0


def test_members_with_live_ping_only_lists_live_mode_with_an_area(tmp_path):
    area = parse_area("42240 r50")
    save_area(tmp_path, "1", area)
    save_ping_mode(tmp_path, "1", PING_MODE_LIVE)
    save_area(tmp_path, "2", area)
    save_ping_mode(tmp_path, "2", PING_MODE_BATCH)     # batch — excluded
    save_ping_mode(tmp_path, "3", PING_MODE_LIVE)       # no area — excluded
    members = members_with_live_ping(tmp_path)
    assert [uid for uid, _ in members] == ["1"]
    assert members[0][1] == area


# ── location-filter-d: nearby_finds, the on-request report ─────────────────
_HOPKINSVILLE = (36.86561, -87.49117)
_CLARKSVILLE = (36.52981, -87.35944)
_NASHVILLE = (36.16589, -86.78444)


def _geo_fake_get(zip_to_point: dict):
    from urllib.parse import unquote

    def get(url: str) -> dict:
        decoded = unquote(url)
        for place, (lat, lon) in zip_to_point.items():
            if place in decoded:
                return {"results": [{"country_code": "US", "latitude": lat,
                                     "longitude": lon, "postcodes": [place]}]}
        return {"results": []}
    return get


def _seed_vertical_runs(tmp_path, project, now, rows):
    p = tmp_path / "bot_projects" / project
    p.mkdir(parents=True, exist_ok=True)
    (p / "runs.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n")


def test_nearby_finds_keeps_only_resolvable_matches_within_radius(tmp_path):
    now = 1_784_000_000.0
    # "sneakers" is a real channeled star vertical -> project scout-sneakers
    _seed_vertical_runs(tmp_path, "scout-sneakers", now, [
        {"ts": now - 100, "new": [
            {"source": "reddit-sneakers", "id": "t3_a",
             "text": "Dropped in Clarksville, TN today"}]},
        {"ts": now - 200, "new": [
            {"source": "reddit-sneakers", "id": "t3_b",
             "text": "Restocked in Nashville, TN today"}]},
        {"ts": now - 300, "new": [
            {"source": "reddit-sneakers", "id": "t3_c",
             "text": "just talking, no location named"}]},
    ])
    area = {"zips": ["42240"], "radius_mi": 50}
    get = _geo_fake_get({"42240": _HOPKINSVILLE, "Clarksville, TN": _CLARKSVILLE,
                         "Nashville, TN": _NASHVILLE})
    finds = nearby_finds(tmp_path, area, now=now, getter=get)
    assert len(finds) == 1
    assert "Clarksville" in finds[0]["text"]
    assert finds[0]["location"] == "Clarksville, TN"


def test_nearby_finds_empty_without_an_area():
    assert nearby_finds("/nonexistent", None) == []


def test_nearby_finds_since_ts_overrides_days_window(tmp_path):
    now = 1_784_000_000.0
    _seed_vertical_runs(tmp_path, "scout-sneakers", now, [
        {"ts": now - 60, "new": [
            {"source": "reddit-sneakers", "id": "t3_new",
             "text": "Fresh find in Clarksville, TN"}]},
        {"ts": now - 120, "new": [
            {"source": "reddit-sneakers", "id": "t3_older",
             "text": "Older find in Clarksville, TN"}]},
    ])
    area = {"zips": ["42240"], "radius_mi": 50}
    get = _geo_fake_get({"42240": _HOPKINSVILLE, "Clarksville, TN": _CLARKSVILLE})
    finds = nearby_finds(tmp_path, area, now=now, since_ts=now - 90, getter=get)
    assert len(finds) == 1
    assert "Fresh" in finds[0]["text"]


def test_nearby_finds_respects_recency_window(tmp_path):
    now = 1_784_000_000.0
    _seed_vertical_runs(tmp_path, "scout-sneakers", now, [
        {"ts": now - (10 * 86_400), "new": [
            {"source": "reddit-sneakers", "id": "t3_old",
             "text": "Old find in Clarksville, TN"}]},
    ])
    area = {"zips": ["42240"], "radius_mi": 50}
    get = _geo_fake_get({"42240": _HOPKINSVILLE, "Clarksville, TN": _CLARKSVILLE})
    assert nearby_finds(tmp_path, area, days=3.0, now=now, getter=get) == []


def test_embeds_carry_the_funnel_and_stay_clamped(tmp_path):
    _seed_runs(tmp_path)
    e = lane_embed(tmp_path, "deals")
    assert "Deals" in e["title"]
    assert "#storefront" in e["footer"]["text"]
    assert "Prismatic" in e["description"]
    # local lane empty → honest + inviting, never fake data
    local = lane_embed(tmp_path, "local")
    assert "My Area" in local["description"]
    p = panel_embed(tmp_path)
    assert "TCG Scout" in p["title"] and "today:" in p["description"]


def test_flex_caps_and_never_repeats(tmp_path, monkeypatch):
    import time as _t
    from sovereign_agent.scout import FLEX_DAILY_CAP, maybe_flex
    sent = []

    class FakeDelivery:
        def __init__(self, env, live=False):
            assert env == "DISCORD_DEMO_WEBHOOK_URL"

        def send(self, text, username=""):
            sent.append(text)

    import sovereign_agent.discord_runtime.delivery as dmod
    monkeypatch.setattr(dmod, "WebhookDelivery", FakeDelivery)
    now = _t.time()
    _seed_runs(tmp_path, now=now)               # Prismatic find is fresh
    line = maybe_flex(tmp_path, live=True, now=now)
    assert line and "Prismatic" in line
    # the same find never flexes twice
    assert maybe_flex(tmp_path, live=True, now=now) is None
    # cap is structural
    from sovereign_agent.scout import _load_voice_state
    import time as _time
    day = _time.strftime("%Y-%m-%d", _time.gmtime(now))
    st = _load_voice_state(tmp_path, day)
    assert st["count"] == 1 <= FLEX_DAILY_CAP


def test_scout_report_composes_and_posts_once(tmp_path, monkeypatch):
    import time as _t
    from sovereign_agent.scout import compose_scout_report, publish_scout_report
    now = _t.time()
    _seed_runs(tmp_path, now=now)
    rep = compose_scout_report(tmp_path, now=now)
    assert "Scout Report" in rep and "Prismatic" in rep
    assert "#storefront" in rep                 # the funnel rides everywhere
    sent = []

    class FakeDelivery:
        def __init__(self, env, live=False):
            pass

        def send(self, text, username=""):
            sent.append(text)

    import sovereign_agent.discord_runtime.delivery as dmod
    monkeypatch.setattr(dmod, "WebhookDelivery", FakeDelivery)
    publish_scout_report(tmp_path, live=True, now=now)
    assert len(sent) >= 1
    n = len(sent)
    publish_scout_report(tmp_path, live=True, now=now)   # once per day
    assert len(sent) == n


def test_every_find_answers_what_where_how_much(tmp_path):
    """Kevin (2026-07-17, screenshot): 'I need to know where and what and
    how much.' Structural across the surfaces."""
    from sovereign_agent.scout import price_of
    assert price_of("Prismatic ETB $59.99 at Target") == "$59.99"
    assert price_of("no price here") == ""
    _seed_runs(tmp_path)
    e = lane_embed(tmp_path, "deals")
    assert "💵 $25" in e["description"]              # how much
    assert "https://sd.example/a" in e["description"]  # where (link)
    assert "via slickdeals-tcg" in e["description"]    # where (source)
    rep_ = __import__("sovereign_agent.scout", fromlist=["compose_scout_report"])
    rep = rep_.compose_scout_report(tmp_path)
    assert "<https://sd.example/a>" in rep and "💵 $25" in rep


def test_alert_format_carries_link_and_price():
    from sovereign_agent.bot_projects import BotProject
    from sovereign_agent.discord_runtime.runtime import _format_alert
    from sovereign_agent.discord_runtime.sources import Item, Source
    p = BotProject("tcg-scout", bot_name="Aria TCG Scout")
    s = Source(name="slickdeals-tcg", url="x", kind="rss")
    out = _format_alert(p, s, Item(id="https://deal.example/x",
                                   text="151 Booster Bundle $24.99"))
    assert "🔎 151 Booster Bundle" in out
    assert "💵 $24.99" in out
    assert "🔗 https://deal.example/x" in out
    out2 = _format_alert(p, s, Item(id="t3_zz9", text="ETB restock"))
    assert "reddit.com/comments/zz9" in out2


# ── affiliate-links-d — FTC disclosure only appears when a link was really tagged ──
def _seed_amazon_find(d, now=1_784_000_000.0):
    p = d / "bot_projects" / "tcg-scout"
    p.mkdir(parents=True)
    rows = [{"ts": now - 100, "new": [
        {"source": "slickdeals-tcg", "id": "https://www.amazon.com/dp/B0X",
         "text": "Pokemon TCG booster bundle $25 on Amazon"}]}]
    (p / "runs.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n")
    return now


def test_no_disclosure_when_amazon_tag_not_configured(tmp_path, monkeypatch):
    monkeypatch.setenv("ARIA_KEYS_FILE", str(tmp_path / "shop.env"))
    now = _seed_amazon_find(tmp_path)
    e = lane_embed(tmp_path, "deals", now=now)
    assert "Amazon Associate" not in e["footer"]["text"]
    rep = compose_scout_report(tmp_path, now=now)
    assert "Amazon Associate" not in rep


def test_disclosure_appears_when_a_link_is_actually_tagged(tmp_path, monkeypatch):
    from sovereign_agent.credentials import set_secret
    vault = tmp_path / "shop.env"
    monkeypatch.setenv("ARIA_KEYS_FILE", str(vault))
    set_secret("AMAZON_ASSOCIATE_TAG", "ariashop-20", vault)

    now = _seed_amazon_find(tmp_path)
    e = lane_embed(tmp_path, "deals", now=now)
    assert "tag=ariashop-20" in e["description"]
    assert "As an Amazon Associate" in e["footer"]["text"]

    rep = compose_scout_report(tmp_path, now=now)
    assert "tag=ariashop-20" in rep
    assert "As an Amazon Associate" in rep


def test_disclosure_absent_for_a_non_amazon_deal(tmp_path, monkeypatch):
    from sovereign_agent.credentials import set_secret
    vault = tmp_path / "shop.env"
    monkeypatch.setenv("ARIA_KEYS_FILE", str(vault))
    set_secret("AMAZON_ASSOCIATE_TAG", "ariashop-20", vault)

    now = _seed_runs(tmp_path)  # the other fixture — no amazon.* links
    e = lane_embed(tmp_path, "deals", now=now)
    assert "As an Amazon Associate" not in e["footer"]["text"]
