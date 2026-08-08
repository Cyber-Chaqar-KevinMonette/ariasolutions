"""F1 — signal vs noise: the post-intent gate (Kevin's retro-games fix)."""
from __future__ import annotations

from sovereign_agent.post_intent import (
    AVAILABLE, BUYING, EXPIRED, SELLING, SHOWCASE, UNKNOWN,
    classify, default_allowed, passes_intent)

# realistic titles from the actual tracker verticals
MATRIX = [
    # live deals — the ONLY thing tracker channels should carry
    ("Pokemon Prismatic ETB back in stock at Target $49.99", AVAILABLE),
    ("[Slickdeals] RTX 4070 Super price drop to $529 + free shipping", AVAILABLE),
    ("LEGO 10300 DeLorean 20% off, lowest price ever", AVAILABLE),
    ("Restock alert: PS5 Slim available now at Best Buy", AVAILABLE),
    # showcase — great vibes, zero leverage (Kevin: noise)
    ("Look what I got in the mail today!!", SHOWCASE),
    ("Finally got my grail — SNES mini after 2 years of hunting", SHOWCASE),
    ("My collection so far, started in January", SHOWCASE),
    ("Mail day! Just picked up these 3 sealed Genesis games", SHOWCASE),
    ("Today's pickup from the flea market, so happy with it", SHOWCASE),
    # marketplace people — networking lane, not deals
    ("[FS] CIB EarthBound, taking offers", SELLING),
    ("WTS my sealed N64 console, local only", SELLING),
    ("WTB: GameCube component cable, paying well", BUYING),
    ("ISO Chrono Trigger cart, anyone selling?", BUYING),
    # dead posts must never ship as deals
    ("RTX 4090 deal — EXPIRED, price is back up", EXPIRED),
    ("PS5 bundle at Walmart [DEAD] sold out in minutes", EXPIRED),
    # no signal → unknown (passes: never silence a possible live deal)
    ("Interesting thread about console modding", UNKNOWN),
]


def test_intent_matrix():
    for title, want in MATRIX:
        got = classify(title)
        assert got == want, f"{title!r}: got {got}, want {want}"


def test_precedence_dead_beats_available():
    # a post can say both "in stock" and "expired" — dead wins
    assert classify("was in stock, now EXPIRED sadly") == EXPIRED


def test_precedence_marketplace_beats_showcase():
    # "[FS] just picked up..." is a sale listing, not a showcase
    assert classify("[FS] just picked up a lot, selling my extras") == SELLING


def test_default_gate_passes_deals_blocks_noise():
    ok, intent = passes_intent("PS5 restock available now")
    assert ok and intent == AVAILABLE
    ok, intent = passes_intent("look what I got today!")
    assert not ok and intent == SHOWCASE
    ok, intent = passes_intent("totally neutral title")
    assert ok and intent == UNKNOWN                  # benefit of the doubt


def test_widened_lane_can_carry_marketplace():
    # a #marketplace-radar source names its intents explicitly
    allowed = frozenset({SELLING, BUYING})
    ok, intent = passes_intent("[FS] CIB EarthBound", allowed)
    assert ok and intent == SELLING


def test_poll_loop_wires_the_gate(tmp_path):
    """End to end through BotRuntime.poll_once: showcase suppressed +
    counted; the deal ships. Injected fetcher — no network."""
    from sovereign_agent.discord_runtime.runtime import BotRuntime
    from sovereign_agent.discord_runtime.sources import Source

    class _Item:
        def __init__(self, id, text):
            self.id, self.text, self.url = id, text, ""

    class _Fetcher:
        def fetch(self, source):
            return [_Item("1", "PS5 restock in stock at Target"),
                    _Item("2", "Look what I got in the mail today!")]

    src = Source(name="t", kind="manual", allowed_min_interval_s=60)
    rt = BotRuntime.__new__(BotRuntime)                # bare wiring
    rt.sources = [src]
    rt.live = False
    rt._seen = set()
    rt._fetcher_for = lambda s: _Fetcher()

    class _Gate:
        def poll_due(self, *a): return True
        def record_poll(self, *a): return None
        def send_allowed(self, *a): return False     # inline path: throttle
    rt.gate = _Gate()
    rt.queue = None
    rt._save_seen = lambda: None
    rt._audit = lambda *a: None

    class _P:
        slug = name = bot_name = project_name = "t"
    rt.project = _P()
    report = rt.poll_once(now=0.0)
    assert len(report.new_alerts) == 1
    assert "restock" in report.new_alerts[0].title
    assert report.intent_filtered == {"showcase": 1}
    assert "noise gate" in report.summary()
