"""Tests for the reliability layer — fetchers, circuit breaker, durable
queue (retry/backoff/dead-letter/visibility), the durable drain path, and
the crash-isolated fleet manager. All deterministic, no real network/clock.
"""
from __future__ import annotations

import json

import pytest

from sovereign_agent.bot_projects import BotProject, save
from sovereign_agent.discord_runtime import (
    BotManager,
    BotRuntime,
    ChangeFetcher,
    CircuitBreaker,
    JobQueue,
    RedditFetcher,
    RssFetcher,
    ScrapeFetcher,
    Source,
    add_source,
    fetcher_for,
)
from sovereign_agent.discord_runtime.breaker import CLOSED, HALF_OPEN, OPEN
from sovereign_agent.discord_runtime.delivery import DeliveryResult
from sovereign_agent.discord_runtime.sources import HttpJsonFetcher, Item, NullFetcher


# ── fetchers ────────────────────────────────────────────────────────────────
class _Resp:
    def __init__(self, data: bytes): self._data = data
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def read(self): return self._data


def _opener(data: bytes):
    def op(url, timeout): return _Resp(data)
    return op


RSS = b"""<?xml version="1.0"?><rss><channel>
<item><title>PS5 restocked</title><guid>abc-1</guid></item>
<item><title>Switch restocked</title><link>http://x/2</link></item>
</channel></rss>"""

ATOM = b"""<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">
<entry><title>Release v2</title><id>tag:1</id></entry></feed>"""


def test_rss_fetcher_parses_rss():
    items = RssFetcher(opener=_opener(RSS)).fetch(Source(name="f", url="http://x", kind="rss"))
    assert [i.id for i in items] == ["abc-1", "http://x/2"]
    assert items[0].text == "PS5 restocked"


def test_rss_fetcher_parses_atom():
    items = RssFetcher(opener=_opener(ATOM)).fetch(Source(name="f", url="http://x", kind="rss"))
    assert items == [Item("tag:1", "Release v2")]


def test_rss_fetcher_survives_garbage():
    assert RssFetcher(opener=_opener(b"not xml")).fetch(Source(name="f", url="http://x")) == []


def test_change_fetcher_hashes_and_dedups_across_polls():
    src = Source(name="page", url="http://x", kind="change")
    a = ChangeFetcher(opener=_opener(b"in stock")).fetch(src)
    b = ChangeFetcher(opener=_opener(b"in stock")).fetch(src)
    c = ChangeFetcher(opener=_opener(b"SOLD OUT")).fetch(src)
    assert a[0].id == b[0].id and a[0].id != c[0].id   # same content → same id


def test_fetcher_for_picks_by_kind():
    assert isinstance(fetcher_for(Source(name="a", kind="rss")), RssFetcher)
    assert isinstance(fetcher_for(Source(name="a", kind="api")), HttpJsonFetcher)
    assert isinstance(fetcher_for(Source(name="a", kind="change")), ChangeFetcher)
    assert isinstance(fetcher_for(Source(name="a", kind="manual")), NullFetcher)


# ── reddit oauth fetcher (reddit-oauth-d, Kevin 2026-07-27: "no alerts yet") ─
def _fake_token_opener(url, headers, data, timeout):
    class _TokResp:
        status = 200
        def read(self): return b'{"access_token": "tok", "expires_in": 3600}'
        def __enter__(self): return self
        def __exit__(self, *a): return False
    return _TokResp()


REDDIT_JSON = json.dumps({"data": {"children": [
    {"data": {"name": "t3_abc", "title": "50% off widgets",
              "url": "https://store.example.com/widget",
              "permalink": "/r/deals/comments/abc/"}},
    {"data": {"name": "t3_def", "title": "just talking, no link",
              "url": "", "permalink": "/r/deals/comments/def/"}},
]}}).encode()


def test_fetcher_for_routes_reddit_rss_to_reddit_fetcher():
    assert isinstance(fetcher_for(Source(
        name="r", kind="rss", url="https://www.reddit.com/r/deals/new/.rss")),
        RedditFetcher)
    assert isinstance(fetcher_for(Source(
        name="s", kind="rss", url="https://slickdeals.net/x.rss")), RssFetcher)


def test_reddit_fetcher_falls_back_to_rss_with_no_creds(monkeypatch):
    import sovereign_agent.discord_runtime.fetchers as fx
    monkeypatch.setattr(fx, "_REDDIT_TOKEN", {})
    monkeypatch.setattr("sovereign_agent.credentials.read_env", lambda *a, **k: {})
    src = Source(name="r-deals", url="https://www.reddit.com/r/deals/new/.rss", kind="rss")
    items = RedditFetcher(opener=_opener(RSS)).fetch(src)
    assert [i.id for i in items] == ["abc-1", "http://x/2"]   # fell back to RSS parse


def test_reddit_fetcher_uses_oauth_when_token_available(monkeypatch):
    import sovereign_agent.discord_runtime.fetchers as fx
    monkeypatch.setattr(fx, "_REDDIT_TOKEN", {})
    monkeypatch.setattr(
        "sovereign_agent.credentials.read_env",
        lambda *a, **k: {"REDDIT_CLIENT_ID": "cid", "REDDIT_CLIENT_SECRET": "sec"})
    seen = {}
    def opener(url, timeout):
        seen["url"] = url
        return _Resp(REDDIT_JSON)
    src = Source(name="r-deals", url="https://www.reddit.com/r/deals/new/.rss", kind="rss")
    items = RedditFetcher(opener=opener, token_opener=_fake_token_opener).fetch(src)
    assert [i.id for i in items] == ["t3_abc", "t3_def"]
    assert items[0].url == "https://store.example.com/widget"
    assert items[1].url == "https://www.reddit.com/r/deals/comments/def/"
    assert "oauth.reddit.com/r/deals/new" in seen["url"]


def test_reddit_fetcher_token_is_cached_across_fetches(monkeypatch):
    import sovereign_agent.discord_runtime.fetchers as fx
    monkeypatch.setattr(fx, "_REDDIT_TOKEN", {})
    monkeypatch.setattr(
        "sovereign_agent.credentials.read_env",
        lambda *a, **k: {"REDDIT_CLIENT_ID": "cid", "REDDIT_CLIENT_SECRET": "sec"})
    calls = {"token": 0}
    def token_opener(url, headers, data, timeout):
        calls["token"] += 1
        return _fake_token_opener(url, headers, data, timeout)
    src = Source(name="r-deals", url="https://www.reddit.com/r/deals/new/.rss", kind="rss")
    RedditFetcher(opener=_opener(REDDIT_JSON), token_opener=token_opener).fetch(src)
    RedditFetcher(opener=_opener(REDDIT_JSON), token_opener=token_opener).fetch(src)
    assert calls["token"] == 1                                 # cached, not re-fetched


def test_reddit_fetcher_falls_back_when_token_exchange_fails(monkeypatch):
    import sovereign_agent.discord_runtime.fetchers as fx
    monkeypatch.setattr(fx, "_REDDIT_TOKEN", {})
    monkeypatch.setattr(
        "sovereign_agent.credentials.read_env",
        lambda *a, **k: {"REDDIT_CLIENT_ID": "cid", "REDDIT_CLIENT_SECRET": "sec"})
    def bad_token_opener(url, headers, data, timeout):
        raise RuntimeError("network down")
    src = Source(name="r-deals", url="https://www.reddit.com/r/deals/new/.rss", kind="rss")
    items = RedditFetcher(opener=_opener(RSS), token_opener=bad_token_opener).fetch(src)
    assert [i.id for i in items] == ["abc-1", "http://x/2"]     # fell back to RSS parse


def test_reddit_fetcher_survives_garbage_json(monkeypatch):
    import sovereign_agent.discord_runtime.fetchers as fx
    monkeypatch.setattr(fx, "_REDDIT_TOKEN", {})
    monkeypatch.setattr(
        "sovereign_agent.credentials.read_env",
        lambda *a, **k: {"REDDIT_CLIENT_ID": "cid", "REDDIT_CLIENT_SECRET": "sec"})
    src = Source(name="r-deals", url="https://www.reddit.com/r/deals/new/.rss", kind="rss")
    items = RedditFetcher(opener=_opener(b"not json"),
                          token_opener=_fake_token_opener).fetch(src)
    assert items == []


# ── crawlee-hand-port-d: backoff-cooldown, UA rotation, robots.txt ──────────
def test_ua_pool_actually_rotates():
    from sovereign_agent.discord_runtime.fetchers import _UA_POOL, _pick_ua
    seen = {_pick_ua() for _ in range(60)}
    assert seen <= set(_UA_POOL)
    assert len(seen) > 1                     # not stuck picking the same one


def test_429_triggers_a_skip_cooldown_not_a_retry(monkeypatch):
    """Kevin: 'rate limit each channel also so we don't run into this
    again' — a host that 429s gets SKIPPED (not blockingly retried) for a
    growing window; the very next fetch attempt within that window never
    even calls the opener again."""
    import sovereign_agent.discord_runtime.fetchers as fx
    monkeypatch.setattr(fx, "_HOST_BACKOFF", {})
    monkeypatch.setattr(fx, "_HOST_COOLDOWN_UNTIL", {})
    monkeypatch.setattr(fx, "_HOST_LAST", {})

    class _Err429(Exception):
        code = 429

    calls = {"n": 0}
    def opener(url, timeout):
        calls["n"] += 1
        raise _Err429()

    src = Source(name="flaky", url="http://flaky-host.example/feed.rss", kind="rss")
    assert RssFetcher(opener=opener).fetch(src) == []
    assert calls["n"] == 1
    assert RssFetcher(opener=opener).fetch(src) == []
    assert calls["n"] == 1                   # cooldown skip — opener never called again


def test_backoff_grows_then_halves_on_success():
    import sovereign_agent.discord_runtime.fetchers as fx
    host = "flaky2.example"
    url = f"http://{host}/x"
    fx._HOST_BACKOFF.pop(host, None)
    fx._HOST_COOLDOWN_UNTIL.pop(host, None)
    fx._note_outcome(url, False, 429)
    assert fx._HOST_BACKOFF[host] == fx._BACKOFF_BASE_S
    fx._note_outcome(url, False, 429)
    assert fx._HOST_BACKOFF[host] == fx._BACKOFF_BASE_S * 2
    fx._HOST_COOLDOWN_UNTIL[host] = 0.0       # simulate the window having elapsed
    fx._note_outcome(url, True, None)
    assert fx._HOST_BACKOFF[host] == fx._BACKOFF_BASE_S      # halved, not reset


def test_change_fetcher_blocked_by_robots_disallow(monkeypatch):
    import sovereign_agent.discord_runtime.fetchers as fx
    monkeypatch.setattr(fx, "_ROBOTS_CACHE", {})
    robots = b"User-agent: *\nDisallow: /\n"
    src = Source(name="blocked", url="http://blocked.example/status", kind="change")
    items = ChangeFetcher(opener=_opener(b"page content"),
                          robots_opener=lambda url, timeout: _Resp(robots)).fetch(src)
    assert items == []


def test_change_fetcher_allowed_by_robots(monkeypatch):
    import sovereign_agent.discord_runtime.fetchers as fx
    monkeypatch.setattr(fx, "_ROBOTS_CACHE", {})
    robots = b"User-agent: *\nAllow: /\n"
    src = Source(name="ok", url="http://allowed.example/status", kind="change")
    items = ChangeFetcher(opener=_opener(b"page content"),
                          robots_opener=lambda url, timeout: _Resp(robots)).fetch(src)
    assert len(items) == 1


def test_change_fetcher_robots_fetch_failure_fails_open(monkeypatch):
    import sovereign_agent.discord_runtime.fetchers as fx
    monkeypatch.setattr(fx, "_ROBOTS_CACHE", {})
    def bad_robots_opener(url, timeout):
        raise RuntimeError("no robots.txt")
    src = Source(name="norobots", url="http://norobots.example/status", kind="change")
    items = ChangeFetcher(opener=_opener(b"page content"),
                          robots_opener=bad_robots_opener).fetch(src)
    assert len(items) == 1                   # fail open — still fetched


class _FakeSession:
    def __init__(self, html: str = "<html>ok</html>", status: int = 200):
        self.html, self.status = html, status
        self.calls = 0

    def visit(self, url, **kw):
        self.calls += 1
        return self.html, self.status


def test_fetcher_for_routes_scrape_kind_to_scrape_fetcher():
    assert isinstance(fetcher_for(Source(
        name="target", kind="scrape", url="https://www.target.com/s?gpu")),
        ScrapeFetcher)


def test_scrape_fetcher_uses_default_parser_when_none_registered(monkeypatch):
    import sovereign_agent.discord_runtime.fetchers as fx
    monkeypatch.setattr(fx, "_HOST_BACKOFF", {})
    monkeypatch.setattr(fx, "_HOST_COOLDOWN_UNTIL", {})
    monkeypatch.setattr(fx, "_SCRAPE_PARSERS", {})
    session = _FakeSession(html="<html><body>RTX 4070 in stock</body></html>")
    src = Source(name="unregistered", url="https://unregistered.example/page",
                kind="scrape")
    items = ScrapeFetcher(session=session).fetch(src)
    assert len(items) == 1
    assert items[0].url == src.url
    assert "unregistered.example" in items[0].text


def test_scrape_fetcher_uses_registered_parser_for_the_hostname(monkeypatch):
    import sovereign_agent.discord_runtime.fetchers as fx
    from sovereign_agent.discord_runtime.fetchers import register_scrape_parser
    from sovereign_agent.discord_runtime.sources import Item
    monkeypatch.setattr(fx, "_HOST_BACKOFF", {})
    monkeypatch.setattr(fx, "_HOST_COOLDOWN_UNTIL", {})
    monkeypatch.setattr(fx, "_SCRAPE_PARSERS", {})

    def fake_target_parser(html, url):
        return [Item(id="t1", text="RTX 4070 Super - $529.99", url=url)]

    register_scrape_parser("www.target.example", fake_target_parser)
    session = _FakeSession(html="<html>whatever</html>")
    src = Source(name="target-gpu", url="https://www.target.example/s?gpu",
                kind="scrape")
    items = ScrapeFetcher(session=session).fetch(src)
    assert len(items) == 1 and items[0].id == "t1"
    assert "$529.99" in items[0].text


def test_scrape_fetcher_detects_a_block_and_suppresses_the_item(monkeypatch):
    import sovereign_agent.discord_runtime.fetchers as fx
    monkeypatch.setattr(fx, "_HOST_BACKOFF", {})
    monkeypatch.setattr(fx, "_HOST_COOLDOWN_UNTIL", {})
    session = _FakeSession(html="<html>Checking your browser before accessing...</html>",
                          status=200)
    src = Source(name="blocked-retailer", url="https://blocked-retailer.example/page",
                kind="scrape")
    items = ScrapeFetcher(session=session).fetch(src)
    assert items == []


def test_scrape_fetcher_block_triggers_cooldown_skip_on_next_call(monkeypatch):
    """Same protection as the Reddit/RSS 429 cooldown — a detected block
    is treated identically, so no retry-storm against a site that's
    actively challenging us."""
    import sovereign_agent.discord_runtime.fetchers as fx
    monkeypatch.setattr(fx, "_HOST_BACKOFF", {})
    monkeypatch.setattr(fx, "_HOST_COOLDOWN_UNTIL", {})
    session = _FakeSession(html="<div class='cf-browser-verification'>...</div>",
                          status=200)
    src = Source(name="cf-retailer", url="https://cf-retailer.example/page", kind="scrape")
    assert ScrapeFetcher(session=session).fetch(src) == []
    assert session.calls == 1
    assert ScrapeFetcher(session=session).fetch(src) == []
    assert session.calls == 1                        # cooldown skip — session.visit not called again


def test_scrape_fetcher_respects_cooldown_from_a_different_source_kind(monkeypatch):
    """The cooldown mechanism is shared per-host across ALL fetcher kinds
    (this was originally built for the Reddit/RSS path) — a scrape
    source sharing a host with a fetcher already in cooldown must also
    skip."""
    import sovereign_agent.discord_runtime.fetchers as fx
    monkeypatch.setattr(fx, "_HOST_BACKOFF", {})
    monkeypatch.setattr(fx, "_HOST_COOLDOWN_UNTIL", {})
    fx._note_outcome("https://shared-host.example/anything", False, 429)
    session = _FakeSession()
    src = Source(name="s", url="https://shared-host.example/page", kind="scrape")
    assert ScrapeFetcher(session=session).fetch(src) == []
    assert session.calls == 0                         # never even attempted


def test_robots_check_is_cached_per_host(monkeypatch):
    import sovereign_agent.discord_runtime.fetchers as fx
    monkeypatch.setattr(fx, "_ROBOTS_CACHE", {})
    calls = {"n": 0}
    def robots_opener(url, timeout):
        calls["n"] += 1
        return _Resp(b"User-agent: *\nAllow: /\n")
    src1 = Source(name="a", url="http://same-host.example/1", kind="change")
    src2 = Source(name="b", url="http://same-host.example/2", kind="change")
    ChangeFetcher(opener=_opener(b"x"), robots_opener=robots_opener).fetch(src1)
    ChangeFetcher(opener=_opener(b"y"), robots_opener=robots_opener).fetch(src2)
    assert calls["n"] == 1                   # same host — robots.txt fetched once


# ── circuit breaker ─────────────────────────────────────────────────────────
def test_breaker_opens_after_threshold():
    b = CircuitBreaker(fail_threshold=3, cooldown_s=60)
    assert b.allow(now=0)
    for t in range(3):
        b.record_failure(now=t)
    assert b.state == OPEN
    assert b.allow(now=10) is False        # still open within cooldown


def test_breaker_half_opens_then_closes_on_success():
    b = CircuitBreaker(fail_threshold=2, cooldown_s=30)
    b.record_failure(0); b.record_failure(1)
    assert b.state == OPEN
    assert b.allow(now=40) is True         # cooldown elapsed → one probe
    assert b.state == HALF_OPEN
    assert b.allow(now=41) is False        # only one probe at a time
    b.record_success(now=42)
    assert b.state == CLOSED and b.allow(now=43)


def test_breaker_reopens_on_probe_failure():
    b = CircuitBreaker(fail_threshold=1, cooldown_s=10)
    b.record_failure(0)
    assert b.allow(now=20) is True         # probe
    b.record_failure(now=21)
    assert b.state == OPEN


# ── durable queue ───────────────────────────────────────────────────────────
def test_queue_enqueue_is_idempotent(tmp_path):
    q = JobQueue(tmp_path)
    assert q.enqueue("hi", key="k1", now=0) is not None
    assert q.enqueue("hi", key="k1", now=0) is None    # dedup
    assert q.pending_count() == 1


def test_queue_lease_complete(tmp_path):
    q = JobQueue(tmp_path)
    q.enqueue("a", key="k", now=0)
    leased = q.lease(now=0)
    assert len(leased) == 1 and q.inflight_count() == 1
    q.complete(leased[0].id)
    assert q.pending_count() == 0 and q.inflight_count() == 0


def test_queue_retry_with_backoff(tmp_path):
    q = JobQueue(tmp_path, base_backoff_s=30, max_attempts=5)
    q.enqueue("a", key="k", now=0)
    job = q.lease(now=0)[0]
    assert q.fail(job.id, now=0, error="boom") == "retry"
    assert q.lease(now=5) == []            # backed off, not due yet
    due = q.lease(now=31)                  # 30s backoff elapsed
    assert len(due) == 1 and due[0].attempts == 1


def test_queue_dead_letters_after_max_attempts(tmp_path):
    q = JobQueue(tmp_path, base_backoff_s=1, max_attempts=3)
    q.enqueue("a", key="k", now=0)
    now = 0.0
    outcome = ""
    for _ in range(3):
        job = q.lease(now=now)[0]
        outcome = q.fail(job.id, now=now, error="x")
        now += 100
    assert outcome == "dead"
    assert q.pending_count() == 0 and len(q.dead_letter()) == 1


def test_queue_reclaims_expired_lease(tmp_path):
    q = JobQueue(tmp_path, lease_ttl_s=120)
    q.enqueue("a", key="k", now=0)
    q.lease(now=0)                          # inflight, lease_until=120
    assert q.reclaim(now=60) == 0          # not yet expired
    assert q.reclaim(now=200) == 1         # crash-recovery: back to pending
    assert q.pending_count() == 1


def test_queue_survives_reload(tmp_path):
    JobQueue(tmp_path).enqueue("persist me", key="k", now=0)
    fresh = JobQueue(tmp_path)             # new instance, same dir
    assert fresh.pending_count() == 1


def test_queue_requeue_dead(tmp_path):
    q = JobQueue(tmp_path, base_backoff_s=1, max_attempts=1)
    q.enqueue("a", key="k", now=0)
    job = q.lease(now=0)[0]
    q.fail(job.id, now=0)                   # max_attempts=1 → dead immediately
    assert len(q.dead_letter()) == 1
    assert q.requeue_dead(now=0) == 1
    assert q.pending_count() == 1 and q.dead_letter() == []


# ── durable drain path on the runtime ───────────────────────────────────────
class _StubFetcher:
    def __init__(self, items): self._items = items
    def fetch(self, source): return list(self._items)


class _FlakyDelivery:
    """Fails the first `fail_n` sends, then succeeds."""
    def __init__(self, fail_n): self.fail_n = fail_n; self.calls = 0
    def send(self, content):
        self.calls += 1
        if self.calls <= self.fail_n:
            return DeliveryResult(sent=False, dry_run=False, detail="500")
        return DeliveryResult(sent=True, dry_run=False, detail="ok")
    def describe(self): return "flaky"


def _project():
    return BotProject(project_name="Restocks", bot_name="Scout", kind="restock-alert")


def test_runtime_queues_then_drains(tmp_path):
    q = JobQueue(tmp_path / "q")
    rt = BotRuntime(_project(), [Source(name="feed", allowed_min_interval_s=60)],
                    fetcher=_StubFetcher([Item("1", "PS5")]), data_dir=tmp_path, queue=q)
    cyc = rt.poll_once(now=0)
    assert cyc.queued == 1 and cyc.deliveries == []    # queued, not inline
    drain = rt.drain(now=0)
    assert drain.dry_run == 1 and q.pending_count() == 0


def test_drain_retries_transient_failure_then_delivers(tmp_path):
    q = JobQueue(tmp_path / "q", base_backoff_s=10, max_attempts=5)
    rt = BotRuntime(_project(), [Source(name="feed", allowed_min_interval_s=60)],
                    fetcher=_StubFetcher([Item("1", "PS5")]), data_dir=tmp_path,
                    queue=q, delivery=_FlakyDelivery(fail_n=1),
                    delivery_breaker=CircuitBreaker(fail_threshold=5))
    rt.poll_once(now=0)
    d1 = rt.drain(now=0)                    # first attempt fails → retry scheduled
    assert d1.retried == 1 and q.pending_count() == 1
    d2 = rt.drain(now=20)                   # backoff elapsed → succeeds
    assert d2.sent == 1 and q.pending_count() == 0


def test_drain_stops_when_circuit_opens(tmp_path):
    q = JobQueue(tmp_path / "q", base_backoff_s=1, max_attempts=99)
    rt = BotRuntime(_project(), [Source(name="feed", allowed_min_interval_s=60)],
                    fetcher=_StubFetcher([Item(str(i), f"i{i}") for i in range(5)]),
                    data_dir=tmp_path, queue=q, delivery=_FlakyDelivery(fail_n=99),
                    delivery_breaker=CircuitBreaker(fail_threshold=2, cooldown_s=60))
    rt.poll_once(now=0)
    rt.drain(now=0); rt.drain(now=2)        # two failures → breaker opens
    capped = rt.drain(now=3)
    assert capped.circuit_open is True      # backs off instead of hammering


# ── fleet manager: crash isolation ──────────────────────────────────────────
def test_manager_isolates_a_crashing_bot(tmp_path):
    save(BotProject(project_name="Good", kind="notification-feed"), tmp_path)
    save(BotProject(project_name="Bad", kind="notification-feed"), tmp_path)
    add_source(tmp_path, "Good", Source(name="feed", url="http://x", allowed_min_interval_s=60))
    add_source(tmp_path, "Bad", Source(name="feed", url="http://x", allowed_min_interval_s=60))

    mgr = BotManager(tmp_path, live=False)
    mgr.load()
    # sabotage one runtime so its poll raises
    class _Boom:
        def fetch(self, source): raise RuntimeError("kaboom")
    mgr._runtimes["Bad"]._fetcher_factory = lambda s: _Boom()

    tick = mgr.tick(now=0)
    by = {b.project: b for b in tick.bots}
    assert by["Bad"].error and "kaboom" in by["Bad"].error   # crash recorded
    assert by["Good"].error == ""                            # other bot fine
    assert len(tick.errors) == 1


def test_manager_dry_run_sends_nothing(tmp_path):
    save(BotProject(project_name="P", kind="notification-feed"), tmp_path)
    add_source(tmp_path, "P", Source(name="feed", url="http://x", allowed_min_interval_s=60))
    mgr = BotManager(tmp_path, live=False)
    ticks = mgr.run(ticks=2, now=0, step_s=60)
    assert all(b.sent == 0 for t in ticks for b in t.bots)   # nothing sent in dry-run


def test_manager_status_reports_fleet(tmp_path):
    save(BotProject(project_name="P", kind="analytics-stats"), tmp_path)
    add_source(tmp_path, "P", Source(name="s", allowed_min_interval_s=60))
    rows = BotManager(tmp_path).status(now=0)
    assert len(rows) == 1 and rows[0].project == "P" and rows[0].sources == 1
    assert rows[0].breaker == "closed"


# ── tracker-toggle-d — a paused/retired project is genuinely skipped ────────
def test_manager_load_skips_paused_projects(tmp_path):
    """Kevin, 2026-07-25: "a way for me to turn channels on and maybe turn
    some channels off." status="paused" already existed as a value but
    did nothing — every project loaded and polled regardless."""
    save(BotProject(project_name="Live", kind="notification-feed", status="live"), tmp_path)
    save(BotProject(project_name="Paused", kind="notification-feed", status="paused"), tmp_path)
    add_source(tmp_path, "Live", Source(name="feed", url="http://x", allowed_min_interval_s=60))
    add_source(tmp_path, "Paused", Source(name="feed", url="http://x", allowed_min_interval_s=60))

    mgr = BotManager(tmp_path, live=False)
    loaded = mgr.load()
    assert {p.project_name for p in loaded} == {"Live"}
    assert "Paused" not in mgr._runtimes
    assert "Live" in mgr._runtimes


def test_manager_skips_retired_projects_too(tmp_path):
    save(BotProject(project_name="Retired", kind="notification-feed", status="retired"), tmp_path)
    add_source(tmp_path, "Retired", Source(name="feed", url="http://x", allowed_min_interval_s=60))

    mgr = BotManager(tmp_path, live=False)
    mgr.load()
    assert mgr._runtimes == {}


def test_manager_tick_never_polls_a_paused_project(tmp_path):
    save(BotProject(project_name="Paused", kind="notification-feed", status="paused"), tmp_path)
    add_source(tmp_path, "Paused", Source(name="feed", url="http://x", allowed_min_interval_s=60))

    mgr = BotManager(tmp_path, live=False)
    tick = mgr.tick(now=0)
    assert tick.bots == []          # never even shows up in the tick, no noise

    # building (the default status BEFORE it's marked live) is NOT paused —
    # confirm it's the pause value specifically that gates this, not every
    # non-"live" status.
    save(BotProject(project_name="Building", kind="notification-feed", status="building"), tmp_path)
    add_source(tmp_path, "Building", Source(name="feed", url="http://x", allowed_min_interval_s=60))
    mgr2 = BotManager(tmp_path, live=False)
    tick2 = mgr2.tick(now=0)
    assert any(b.project == "Building" for b in tick2.bots)
