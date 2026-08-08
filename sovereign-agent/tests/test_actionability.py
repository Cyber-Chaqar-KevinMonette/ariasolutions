"""actionability-d (Kevin, 2026-07-27): "reddit is a very noisy place
that doesn't give direct purchase links or locations. Which we want post
with either a purchase link or a location per post." """
from __future__ import annotations

from sovereign_agent.actionability import (
    extract_location,
    has_location_signal,
    has_purchase_link,
    is_actionable,
)


def test_has_purchase_link_true_for_a_real_merchant_url():
    assert has_purchase_link("https://www.target.com/p/some-item/-/A-12345")
    assert has_purchase_link("https://www.bestbuy.com/site/deal/12345")


def test_has_purchase_link_false_for_bare_discussion_permalinks():
    assert not has_purchase_link("https://www.reddit.com/r/deals/comments/abc/")
    assert not has_purchase_link("https://old.reddit.com/r/deals/comments/abc/")
    assert not has_purchase_link("https://slickdeals.net/f/12345-some-thread")


def test_has_purchase_link_false_for_empty_or_non_http():
    assert not has_purchase_link("")
    assert not has_purchase_link("not-a-url")


def test_has_location_signal_zip_code():
    assert has_location_signal("Local pickup only, zip 42240")
    assert has_location_signal("Found a stack at the store near 90210-1234")


def test_has_location_signal_city_state_or_phrase():
    assert has_location_signal("Available in Clarksville, TN this week")
    assert has_location_signal("Local pickup only, no shipping")
    assert has_location_signal("near me at the Target on 5th")


def test_has_location_signal_false_for_plain_discussion():
    assert not has_location_signal("Interesting thread about console modding")
    assert not has_location_signal("just talking about prices going up")


def test_is_actionable_requires_at_least_one_signal():
    assert is_actionable("just talking", "https://www.target.com/p/x")
    assert is_actionable("Local pickup only in Clarksville, TN", "")
    assert not is_actionable("just talking, no link, no location",
                            "https://www.reddit.com/r/deals/comments/abc/")
    assert not is_actionable("", "")


def test_a_dollar_amount_alone_is_not_a_location_or_link():
    # a pure "$50 off!" discussion post with no real link and no place
    # named is still noise — price alone isn't actionable per Kevin's ask
    assert not is_actionable("50% off everything today!!", "")


# ── location-filter-d: extract_location, the geocodable half of a find ──────
def test_extract_location_prefers_zip_code():
    assert extract_location("Local pickup only, zip 42240") == "42240"
    assert extract_location("stack at the store near 90210-1234") == "90210"


def test_extract_location_falls_back_to_city_state():
    loc = extract_location("Available in Clarksville, TN this week")
    assert loc == "Clarksville, TN"


def test_extract_location_none_for_bare_phrase_or_plain_text():
    # "near me"/"local pickup" are real location SIGNALS (has_location_signal)
    # but have nothing a map can geocode — intentionally excluded here
    assert extract_location("Local pickup only, no shipping") is None
    assert extract_location("just talking about prices") is None
    assert extract_location("") is None


def test_poll_loop_wires_the_gate_for_rss_sources_only():
    """End to end through BotRuntime.poll_once: an rss item with neither
    a real link nor a location is suppressed + counted; a change/api item
    with the same bare text still ships (already inherently actionable)."""
    from sovereign_agent.discord_runtime.runtime import BotRuntime
    from sovereign_agent.discord_runtime.sources import Source

    class _Item:
        def __init__(self, id, text, url=""):
            self.id, self.text, self.url = id, text, url

    class _Fetcher:
        def fetch(self, source):
            return [
                _Item("1", "PS5 restock available now",
                     "https://www.bestbuy.com/site/deal/1"),
                _Item("2", "just talking about it, no link, no place named",
                     "https://www.reddit.com/r/deals/comments/abc/"),
            ]

    src = Source(name="r-deals", kind="rss", allowed_min_interval_s=60)
    rt = BotRuntime.__new__(BotRuntime)
    rt.sources = [src]
    rt.live = False
    rt._seen = set()
    rt._fetcher_for = lambda s: _Fetcher()

    class _Gate:
        def poll_due(self, *a): return True
        def record_poll(self, *a): return None
        def send_allowed(self, *a): return False
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
    assert report.no_signal_filtered == 1
    assert "no-link/no-location" in report.summary()


def test_change_kind_items_are_never_gated_by_actionability():
    """A ChangeFetcher/api item IS the deal itself — no purchase-link-or-
    location check applies, even with a bare synthetic text and no url."""
    from sovereign_agent.discord_runtime.runtime import BotRuntime
    from sovereign_agent.discord_runtime.sources import Source

    class _Item:
        def __init__(self, id, text, url=""):
            self.id, self.text, self.url = id, text, url

    class _Fetcher:
        def fetch(self, source):
            return [_Item("1", "restock-page changed (#abc123)", "")]

    src = Source(name="page", kind="change", allowed_min_interval_s=60)
    rt = BotRuntime.__new__(BotRuntime)
    rt.sources = [src]
    rt.live = False
    rt._seen = set()
    rt._fetcher_for = lambda s: _Fetcher()

    class _Gate:
        def poll_due(self, *a): return True
        def record_poll(self, *a): return None
        def send_allowed(self, *a): return False
    rt.gate = _Gate()
    rt.queue = None
    rt._save_seen = lambda: None
    rt._audit = lambda *a: None

    class _P:
        slug = name = bot_name = project_name = "t"
    rt.project = _P()
    report = rt.poll_once(now=0.0)
    assert len(report.new_alerts) == 1
    assert report.no_signal_filtered == 0
