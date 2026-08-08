"""Tests for osrs_market — real API shapes, real trading edge cases."""
from __future__ import annotations

from sovereign_agent.osrs_flips.osrs_market import (
    build_average_flips,
    GE_TAX_CAP, build_flips, capital_tier, ge_tax, max_profit_per_window,
    net_margin, rank_flips, roi_pct)

NOW = 1_785_811_621.0
FRESH = NOW - 60          # quoted a minute ago
STALE = NOW - 7 * 3600    # quoted 7 hours ago


def _mapping(**kw):
    base = {"id": 2, "name": "Cannonball", "limit": 11_000, "members": True,
            "icon": "Cannonball.png"}
    base.update(kw)
    return [base]


def _latest(low=285, high=288, t=FRESH, iid=2):
    return {"data": {str(iid): {"high": high, "highTime": t,
                                "low": low, "lowTime": t}}}


def _vol(hi=23_427_954, lo=10_707_337, iid=2):
    return {"data": {str(iid): {"highPriceVolume": hi, "lowPriceVolume": lo}}}


# ── tax ────────────────────────────────────────────────────────────────
def test_tax_exempt_under_threshold():
    assert ge_tax(49) == 0


def test_tax_is_one_percent():
    assert ge_tax(1_000) == 10


def test_tax_is_capped():
    assert ge_tax(10_000_000_000) == GE_TAX_CAP


def test_net_margin_subtracts_tax():
    # naive margin is 100; tax on a 1000gp sale is 10, so real profit is 90
    assert net_margin(900, 1000) == 90


def test_margin_can_go_negative_after_tax():
    """A 'profitable' flip that tax turns into a loss must report the loss,
    not be clamped to zero — that lie is the whole reason this exists."""
    assert net_margin(999, 1000) < 0


# ── ranking inputs ─────────────────────────────────────────────────────
def test_roi_favours_cheap_items():
    assert roi_pct(100, 120) > roi_pct(100_000, 100_500)


def test_max_profit_folds_in_buy_limit():
    # sell 1,100,000 → tax 11,000 → margin 89,000 → ×8 limit = 712,000
    assert max_profit_per_window(1_000_000, 1_100_000, 8) == 712_000
    # sell 110 → tax 1 → margin 9 → ×11,000 limit = 99,000
    assert max_profit_per_window(100, 110, 11_000) == 99_000


def test_capital_tiers():
    assert capital_tier(500) == "starter"
    assert capital_tier(50_000) == "mid"
    assert capital_tier(5_000_000) == "high"


# ── the pipeline ───────────────────────────────────────────────────────
def test_builds_a_real_flip():
    flips = build_flips(_mapping(), _latest(), _vol(), now=NOW)
    assert len(flips) == 1
    f = flips[0]
    assert f.name == "Cannonball"
    assert f.buy == 285 and f.sell == 288
    assert f.buy_limit == 11_000
    assert f.max_profit == f.margin * 11_000


def test_stale_quotes_are_refused():
    """A margin quoted 7 hours ago is not tradeable information."""
    assert build_flips(_mapping(), _latest(t=STALE), _vol(), now=NOW) == []


def test_illiquid_items_are_refused():
    """Both sides must move — you have to be able to buy AND sell."""
    flips = build_flips(_mapping(), _latest(), _vol(hi=9_000_000, lo=3),
                        now=NOW, min_volume=100)
    assert flips == []


def test_volume_uses_the_worse_side():
    """High buy volume with no sell volume is a trap, not liquidity."""
    flips = build_flips(_mapping(), _latest(), _vol(hi=5_000_000, lo=42),
                        now=NOW)
    assert flips[0].volume_24h == 42


def test_fantasy_spread_is_rejected():
    """The real one Kevin caught: Rosemary seed, buy 11 → sell 100, 800%
    ROI, decent volume. Nobody trades at 11; the buy offer never fills."""
    mapping = _mapping(id=5097, name="Rosemary seed", limit=600)
    latest = _latest(low=11, high=100, iid=5097)
    vol = _vol(hi=6_938, lo=6_938, iid=5097)
    # without the guard it sails through every other filter
    assert len(build_flips(mapping, latest, vol, now=NOW)) == 1
    # with it, gone
    assert build_flips(mapping, latest, vol, now=NOW,
                       max_spread_ratio=2.0) == []


def test_sane_spread_still_passes():
    """The guard must not eat ordinary flips — 288/285 is a 1.01 ratio."""
    flips = build_flips(_mapping(), _latest(), _vol(), now=NOW,
                        max_spread_ratio=2.0)
    assert len(flips) == 1


def test_spread_guard_is_off_by_default():
    """None = no ceiling, so existing callers behave exactly as before."""
    mapping = _mapping(id=5097, name="Rosemary seed", limit=600)
    assert len(build_flips(mapping, _latest(low=11, high=100, iid=5097),
                           _vol(iid=5097), now=NOW)) == 1


# ── the cheap-item (average) engine ────────────────────────────────────
# Real Rosemary seed (id 5097) data pulled live 2026-08-03.
_ROSEMARY_MAP = [{"id": 5097, "name": "Rosemary seed", "limit": 600}]
_ROSEMARY_LATEST = {"data": {"5097": {"high": 100, "highTime": FRESH,
                                      "low": 10, "lowTime": FRESH}}}
_ROSEMARY_1H = {"data": {"5097": {"avgHighPrice": 40, "highPriceVolume": 86,
                                  "avgLowPrice": 20, "lowPriceVolume": 542}}}
_ROSEMARY_24H = {"data": {"5097": {"avgHighPrice": 25,
                                   "highPriceVolume": 6938,
                                   "avgLowPrice": 9,
                                   "lowPriceVolume": 11331}}}


def test_average_engine_quotes_the_hourly_average_not_the_outlier():
    """The whole point: /latest says sell at 100 (one freak trade), the
    hourly average says 40. Quote the 40."""
    f = build_average_flips(_ROSEMARY_MAP, _ROSEMARY_1H, _ROSEMARY_24H)[0]
    assert (f.buy, f.sell) == (20, 40)      # NOT (10, 100)


def test_average_engine_rejects_when_live_quote_disagrees_wildly():
    """latest.high=100 vs avg 40 is a 2.5x disagreement — the item is being
    whipsawed, so it's volatility rather than a stable margin."""
    assert build_average_flips(_ROSEMARY_MAP, _ROSEMARY_1H, _ROSEMARY_24H,
                               latest=_ROSEMARY_LATEST,
                               max_outlier_ratio=2.0) == []


def test_average_engine_accepts_when_live_quote_agrees():
    calm = {"data": {"5097": {"high": 42, "highTime": FRESH,
                              "low": 21, "lowTime": FRESH}}}
    assert len(build_average_flips(_ROSEMARY_MAP, _ROSEMARY_1H,
                                   _ROSEMARY_24H, latest=calm,
                                   max_outlier_ratio=2.0)) == 1


def test_average_engine_skips_items_that_didnt_trade_this_hour():
    assert build_average_flips(_ROSEMARY_MAP, {"data": {}},
                               _ROSEMARY_24H) == []


def test_average_engine_requires_both_sides_to_move():
    one_sided = {"data": {"5097": {"avgHighPrice": 40, "highPriceVolume": 86,
                                   "avgLowPrice": None,
                                   "lowPriceVolume": 0}}}
    assert build_average_flips(_ROSEMARY_MAP, one_sided, _ROSEMARY_24H) == []


def test_average_engine_respects_max_price():
    pricey = [{"id": 5097, "name": "Not cheap", "limit": 600}]
    hourly = {"data": {"5097": {"avgHighPrice": 90_000,
                                "highPriceVolume": 500,
                                "avgLowPrice": 50_000,
                                "lowPriceVolume": 500}}}
    assert build_average_flips(pricey, hourly, _ROSEMARY_24H,
                               max_price=10_000) == []


def test_average_engine_reports_24h_volume_for_liquidity():
    f = build_average_flips(_ROSEMARY_MAP, _ROSEMARY_1H, _ROSEMARY_24H)[0]
    assert f.volume_24h == 6938        # the worse 24h side


def test_average_engine_garbage_never_raises():
    for bad in (None, {}, {"data": None}):
        assert build_average_flips(_ROSEMARY_MAP, bad, bad) == []


def test_min_roi_filter():
    assert build_flips(_mapping(), _latest(), _vol(), now=NOW,
                       min_roi=99.0) == []


def test_tier_filter_segments_by_bankroll():
    cheap = build_flips(_mapping(), _latest(), _vol(), now=NOW, tier="starter")
    assert len(cheap) == 1
    assert build_flips(_mapping(), _latest(), _vol(), now=NOW,
                       tier="high") == []


def test_missing_quote_is_skipped_not_crashed():
    assert build_flips(_mapping(), {"data": {}}, _vol(), now=NOW) == []


def test_garbage_never_raises():
    for bad in (None, {}, {"data": None}):
        assert build_flips(_mapping(), bad, bad, now=NOW) == []
    assert build_flips(None, _latest(), _vol(), now=NOW) == []


def test_rank_by_max_profit_beats_fat_thin_margin():
    mapping = [{"id": 1, "name": "Whale", "limit": 8},
               {"id": 2, "name": "Minnow", "limit": 11_000}]
    latest = {"data": {"1": {"high": 1_100_000, "highTime": FRESH,
                             "low": 1_000_000, "lowTime": FRESH},
                       # Minnow: margin 29 on a 100gp buy = 29% ROI,
                       # far better per-gp than Whale's 8.9%
                       "2": {"high": 130, "highTime": FRESH,
                             "low": 100, "lowTime": FRESH}}}
    vol = {"data": {"1": {"highPriceVolume": 500, "lowPriceVolume": 500},
                    "2": {"highPriceVolume": 9_000_000,
                          "lowPriceVolume": 9_000_000}}}
    ranked = rank_flips(build_flips(mapping, latest, vol, now=NOW))
    assert ranked[0].name == "Whale"
    # for a small bankroll, ROI flips the order
    assert rank_flips(build_flips(mapping, latest, vol, now=NOW),
                      by="roi")[0].name == "Minnow"
