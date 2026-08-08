"""Tests for discord_runtime — the safe-by-construction live bot layer.

Covers: rate-limits as a structural gate, dry-run-by-default delivery,
env-var-only secrets, dedup, audit trail, and the injectable network paths
(fully tested without touching a real network).
"""
from __future__ import annotations

import json

import pytest

from sovereign_agent.bot_projects import BotProject
from sovereign_agent.discord_runtime import (
    Alert,
    BotRuntime,
    DryRunDelivery,
    RateContract,
    RateGate,
    Source,
    WebhookDelivery,
    add_source,
    build_runtime,
    list_sources,
    remove_source,
)
from sovereign_agent.discord_runtime.contracts import ContractViolation
from sovereign_agent.discord_runtime.delivery import build_delivery
from sovereign_agent.discord_runtime.sources import (
    MIN_ALLOWED_INTERVAL_S,
    HttpJsonFetcher,
    Item,
    NullFetcher,
)


# ── contracts: legitimate by construction ──────────────────────────────────
def test_contract_rejects_polling_faster_than_source_allows():
    c = RateContract(poll_interval_s=10)
    with pytest.raises(ContractViolation):
        c.validate_for_source(allowed_min_interval_s=60)


def test_contract_allows_polling_at_or_slower_than_source():
    c = RateContract(poll_interval_s=60)
    c.validate_for_source(60)   # equal is fine
    c.validate_for_source(30)   # slower than allowed is fine


def test_contract_rejects_nonpositive():
    with pytest.raises(ContractViolation):
        RateContract(poll_interval_s=0)
    with pytest.raises(ContractViolation):
        RateContract(max_sends_per_minute=0)


def test_rate_gate_poll_due_respects_interval():
    g = RateGate(RateContract(poll_interval_s=60))
    assert g.poll_due("s", now=1000.0) is True     # never polled
    g.record_poll("s", now=1000.0)
    assert g.poll_due("s", now=1030.0) is False    # too soon
    assert g.poll_due("s", now=1060.0) is True     # interval elapsed


def test_rate_gate_send_ceiling_is_a_rolling_minute():
    g = RateGate(RateContract(poll_interval_s=1, max_sends_per_minute=2))
    assert g.send_allowed(now=0.0)
    g.record_send(0.0)
    g.record_send(1.0)
    assert g.send_allowed(now=2.0) is False        # 2 in the last minute
    assert g.send_allowed(now=61.5) is True        # first one aged out


# ── sources: civility floor + store round-trip ─────────────────────────────
def test_source_clamps_below_civility_floor():
    s = Source(name="x", allowed_min_interval_s=1.0)
    assert s.allowed_min_interval_s == MIN_ALLOWED_INTERVAL_S


def test_source_store_round_trip(tmp_path):
    add_source(tmp_path, "Proj", Source(name="feed", url="http://x", allowed_min_interval_s=90))
    got = list_sources(tmp_path, "Proj")
    assert len(got) == 1 and got[0].name == "feed" and got[0].allowed_min_interval_s == 90


def test_add_source_replaces_same_name(tmp_path):
    add_source(tmp_path, "P", Source(name="a", url="http://1"))
    add_source(tmp_path, "P", Source(name="a", url="http://2"))
    got = list_sources(tmp_path, "P")
    assert len(got) == 1 and got[0].url == "http://2"


def test_remove_source(tmp_path):
    add_source(tmp_path, "P", Source(name="a"))
    assert remove_source(tmp_path, "P", "a") is True
    assert remove_source(tmp_path, "P", "a") is False
    assert list_sources(tmp_path, "P") == []


# ── source-toggle-d: an operator can turn any source on/off ─────────────────
def test_set_source_enabled_toggles_and_preserves_other_fields(tmp_path):
    from sovereign_agent.discord_runtime.sources import set_source_enabled
    add_source(tmp_path, "P", Source(name="a", url="http://x", allowed_min_interval_s=42))
    assert set_source_enabled(tmp_path, "P", "a", False) is True
    got = list_sources(tmp_path, "P")[0]
    assert got.enabled is False
    assert got.url == "http://x" and got.allowed_min_interval_s == 42
    assert set_source_enabled(tmp_path, "P", "a", True) is True
    assert list_sources(tmp_path, "P")[0].enabled is True


def test_set_source_enabled_unknown_source_returns_false(tmp_path):
    from sovereign_agent.discord_runtime.sources import set_source_enabled
    assert set_source_enabled(tmp_path, "P", "nope", False) is False


def test_set_sources_enabled_where_bulk_toggles_matching_only(tmp_path):
    from sovereign_agent.discord_runtime.sources import set_sources_enabled_where
    add_source(tmp_path, "P", Source(name="reddit-a", url="https://www.reddit.com/r/deals/new/.rss"))
    add_source(tmp_path, "P", Source(name="reddit-b", url="https://www.reddit.com/r/flipping/new/.rss"))
    add_source(tmp_path, "P", Source(name="slickdeals-a", url="https://slickdeals.net/x.rss"))
    n = set_sources_enabled_where(tmp_path, "P", lambda s: "reddit.com" in s.url, False)
    assert n == 2
    by_name = {s.name: s for s in list_sources(tmp_path, "P")}
    assert by_name["reddit-a"].enabled is False
    assert by_name["reddit-b"].enabled is False
    assert by_name["slickdeals-a"].enabled is True


def test_set_sources_enabled_where_reports_zero_when_already_in_that_state(tmp_path):
    from sovereign_agent.discord_runtime.sources import set_sources_enabled_where
    add_source(tmp_path, "P", Source(name="a", url="https://www.reddit.com/r/x/new/.rss"))
    assert set_sources_enabled_where(tmp_path, "P", lambda s: True, False) == 1
    assert set_sources_enabled_where(tmp_path, "P", lambda s: True, False) == 0  # already off


def test_set_reddit_sources_enabled_single_project(tmp_path):
    from sovereign_agent.discord_runtime.sources import set_reddit_sources_enabled
    add_source(tmp_path, "P", Source(name="r-a", url="https://www.reddit.com/r/deals/new/.rss"))
    add_source(tmp_path, "P", Source(name="sd-a", url="https://slickdeals.net/x.rss"))
    changed = set_reddit_sources_enabled(tmp_path, False, project_name="P")
    assert changed == {"P": 1}
    by_name = {s.name: s for s in list_sources(tmp_path, "P")}
    assert by_name["r-a"].enabled is False
    assert by_name["sd-a"].enabled is True


def test_set_reddit_sources_enabled_fleet_wide(tmp_path):
    from sovereign_agent import bot_projects
    from sovereign_agent.discord_runtime.sources import set_reddit_sources_enabled
    bot_projects.save(BotProject(project_name="ProjA", kind="restock-alert"), tmp_path)
    bot_projects.save(BotProject(project_name="ProjB", kind="restock-alert"), tmp_path)
    add_source(tmp_path, "ProjA", Source(name="r-a", url="https://www.reddit.com/r/a/new/.rss"))
    add_source(tmp_path, "ProjB", Source(name="r-b", url="https://www.reddit.com/r/b/new/.rss"))
    add_source(tmp_path, "ProjB", Source(name="sd-b", url="https://slickdeals.net/x.rss"))
    changed = set_reddit_sources_enabled(tmp_path, False)
    assert changed == {"ProjA": 1, "ProjB": 1}
    assert list_sources(tmp_path, "ProjA")[0].enabled is False
    by_name = {s.name: s for s in list_sources(tmp_path, "ProjB")}
    assert by_name["r-b"].enabled is False
    assert by_name["sd-b"].enabled is True


def test_disabled_source_is_skipped_by_the_poll_loop(tmp_path):
    """The real point: this isn't just a data flag — BotRuntime.poll_once
    already respects it, so toggling actually silences delivery."""
    from sovereign_agent.discord_runtime.runtime import BotRuntime
    from sovereign_agent.discord_runtime.sources import set_source_enabled

    add_source(tmp_path, "P", Source(name="a", url="http://x", allowed_min_interval_s=60))
    set_source_enabled(tmp_path, "P", "a", False)
    sources = list_sources(tmp_path, "P")

    class _P:
        slug = name = bot_name = project_name = "P"
    rt = BotRuntime(_P(), sources, data_dir=tmp_path)
    report = rt.poll_once(now=0.0)
    assert report.polled == []
    assert report.skipped_not_due == []   # not "not due" — just disabled, silently skipped


def test_null_fetcher_is_inert():
    assert NullFetcher().fetch(Source(name="x", url="http://x")) == []


# ── delivery: dry-run default, no stored secrets ───────────────────────────
def test_build_delivery_defaults_to_dry_run():
    d = build_delivery(live=False)
    r = d.send("hi")
    assert r.dry_run and not r.sent


def test_webhook_is_dry_run_when_not_armed(monkeypatch):
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "http://hook")
    d = WebhookDelivery("DISCORD_WEBHOOK_URL", live=False)
    r = d.send("hi")
    assert r.dry_run and not r.sent          # live=False → nothing sent


def test_webhook_is_dry_run_when_env_unset(monkeypatch):
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    d = WebhookDelivery("DISCORD_WEBHOOK_URL", live=True)
    r = d.send("hi")
    assert r.dry_run and not r.sent          # armed but no target → still safe


def test_webhook_live_send_uses_injected_opener_and_alerts_human(monkeypatch):
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "http://hook")
    calls = {}
    alerts = []

    class _Resp:
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def fake_opener(url, data, timeout):
        calls["url"] = url
        calls["body"] = json.loads(data.decode("utf-8"))
        return _Resp()

    d = WebhookDelivery("DISCORD_WEBHOOK_URL", live=True, opener=fake_opener,
                        on_live_send=alerts.append)
    r = d.send("restock!")
    assert r.sent and not r.dry_run
    assert calls["url"] == "http://hook"
    # stamp-d: plain content gets a <t:unix:f> date-time mark appended
    assert calls["body"]["content"].startswith("restock!")
    assert "<t:" in calls["body"]["content"]
    assert alerts == ["restock!"]            # human alerted on every live send


def test_webhook_never_stores_the_secret_in_describe(monkeypatch):
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "http://super-secret-hook")
    d = WebhookDelivery("DISCORD_WEBHOOK_URL", live=True)
    assert "super-secret-hook" not in d.describe()   # only the env var NAME shows


def test_webhook_default_send_sets_user_agent(monkeypatch):
    """Regression: Discord's edge 403s the default Python-urllib agent
    (Cloudflare 1010). The real send path must set an identifying UA."""
    from sovereign_agent.discord_runtime.delivery import USER_AGENT

    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "http://hook")
    seen = {}

    class _FakeReq:
        def __init__(self, url, data=None, headers=None, method=None):
            seen["headers"] = headers or {}

    class _Resp:
        def __enter__(self): return self
        def __exit__(self, *a): return False

    # patch the lazily-imported urllib symbols the default opener uses
    import urllib.request as u
    monkeypatch.setattr(u, "Request", _FakeReq)
    monkeypatch.setattr(u, "urlopen", lambda req, timeout: _Resp())

    r = WebhookDelivery("DISCORD_WEBHOOK_URL", live=True).send("hi")
    assert r.sent
    assert seen["headers"].get("User-Agent") == USER_AGENT
    assert "aria" in USER_AGENT.lower()   # honest, identifying — never spoofed


def test_webhook_send_includes_embeds_and_username(monkeypatch):
    """Storefront cards: embeds + a display username reach the payload."""
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "http://hook")
    seen = {}

    class _Resp:
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def fake_opener(url, data, timeout):
        seen["body"] = json.loads(data.decode("utf-8"))
        return _Resp()

    embeds = [{"title": "Basic", "description": "$5/mo"}]
    r = WebhookDelivery("DISCORD_WEBHOOK_URL", live=True, opener=fake_opener).send(
        "", embeds=embeds, username="BigKev's Bot Shop")
    assert r.sent
    # stamp-d: every embed carries a timestamp (Discord renders it localized)
    sent_embeds = seen["body"]["embeds"]
    assert sent_embeds[0]["title"] == "Basic"
    assert sent_embeds[0]["description"] == "$5/mo"
    assert "timestamp" in sent_embeds[0]
    assert seen["body"]["username"] == "BigKev's Bot Shop"


def test_dryrun_delivery_accepts_embeds():
    from sovereign_agent.discord_runtime.delivery import DryRunDelivery
    r = DryRunDelivery().send("catalog", embeds=[{"title": "x"}])
    assert r.dry_run and "1 embed" in r.detail


# ── runtime: dedup, throttle, audit, safe assembly ─────────────────────────
class _StubFetcher:
    def __init__(self, items): self._items = items
    def fetch(self, source): return list(self._items)


def _project():
    return BotProject(project_name="Restocks", bot_name="Scout", kind="restock-alert")


def test_runtime_default_assembly_is_inert(tmp_path):
    add_source(tmp_path, "Restocks", Source(name="feed", url="http://x", allowed_min_interval_s=60))
    rt = build_runtime(_project(), tmp_path)          # no fetcher, no live
    rep = rt.poll_once(now=1000.0)
    assert rep.polled == ["feed"] and rep.new_alerts == []   # NullFetcher → nothing


def test_runtime_delivers_new_items_dry_run_and_dedups(tmp_path):
    src = Source(name="feed", url="http://x", allowed_min_interval_s=60)
    rt = BotRuntime(_project(), [src], fetcher=_StubFetcher([Item("1", "PS5 in stock")]),
                    data_dir=tmp_path)
    rep1 = rt.poll_once(now=1000.0)
    assert len(rep1.new_alerts) == 1
    assert rep1.deliveries[0].dry_run and not rep1.deliveries[0].sent
    # same item next cycle → deduped, no new alert
    rep2 = rt.poll_once(now=1100.0)
    assert rep2.new_alerts == []


def test_runtime_threads_item_embed_through_to_delivery_inline(tmp_path):
    # panel-d (Kevin, 2026-07-27): an Item's optional embed must reach
    # the delivery call, not just its plain text — inline (no-queue) path.
    src = Source(name="feed", url="http://x", allowed_min_interval_s=60)
    embed = {"title": "🔄 Arcane Energize", "fields": [{"name": "Buy", "value": "10p"}]}
    rt = BotRuntime(_project(), [src],
                    fetcher=_StubFetcher([Item("1", "short text", embed=embed)]),
                    data_dir=tmp_path)
    rep = rt.poll_once(now=1000.0)
    assert rep.new_alerts[0].embed == embed
    assert "1 embed" in rep.deliveries[0].detail


def test_runtime_threads_item_embed_through_the_durable_queue(tmp_path):
    # same, but the durable (queue + drain) path every real project uses
    from sovereign_agent.discord_runtime.queue import JobQueue

    src = Source(name="feed", url="http://x", allowed_min_interval_s=60)
    embed = {"title": "🔄 Arcane Energize"}
    queue = JobQueue(tmp_path / "queue")
    rt = BotRuntime(_project(), [src],
                    fetcher=_StubFetcher([Item("1", "short text", embed=embed)]),
                    data_dir=tmp_path, queue=queue)
    rep = rt.poll_once(now=1000.0)
    assert rep.queued == 1
    drain_rep = rt.drain(now=1000.0)
    assert drain_rep.dry_run == 1


def test_runtime_respects_send_ceiling(tmp_path):
    src = Source(name="feed", allowed_min_interval_s=60)
    items = [Item(str(i), f"item {i}") for i in range(10)]
    rt = BotRuntime(_project(), [src], fetcher=_StubFetcher(items), data_dir=tmp_path,
                    contract=RateContract(poll_interval_s=60, max_sends_per_minute=3))
    rep = rt.poll_once(now=1000.0)
    assert len(rep.new_alerts) == 10
    assert len(rep.deliveries) == 3 and rep.throttled == 7   # ceiling held


def test_runtime_refuses_contract_that_violates_source(tmp_path):
    src = Source(name="feed", allowed_min_interval_s=120)
    with pytest.raises(ContractViolation):
        BotRuntime(_project(), [src], data_dir=tmp_path,
                   contract=RateContract(poll_interval_s=30))


def test_runtime_writes_audit_trail(tmp_path):
    from sovereign_agent.bot_projects import projects_dir
    from sovereign_agent.discord_runtime.sources import slugify
    src = Source(name="feed", allowed_min_interval_s=60)
    rt = BotRuntime(_project(), [src], fetcher=_StubFetcher([Item("1", "x")]),
                    data_dir=tmp_path)
    rt.poll_once(now=1000.0)
    runs = projects_dir(tmp_path) / slugify("Restocks") / "runs.jsonl"
    assert runs.is_file()
    rec = json.loads(runs.read_text().splitlines()[0])
    assert rec["mode"] == "dry-run" and rec["polled"] == ["feed"]


def test_runtime_skips_not_due_sources(tmp_path):
    src = Source(name="feed", allowed_min_interval_s=60)
    rt = BotRuntime(_project(), [src], fetcher=_StubFetcher([Item("1", "x")]),
                    data_dir=tmp_path)
    rt.poll_once(now=1000.0)
    rep = rt.poll_once(now=1010.0)        # only 10s later, interval is 60
    assert rep.skipped_not_due == ["feed"] and rep.polled == []


def test_http_json_fetcher_with_injected_opener():
    class _Resp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return json.dumps([{"id": "a", "title": "Hello"}]).encode()

    def fake_opener(url, timeout): return _Resp()
    items = HttpJsonFetcher(opener=fake_opener).fetch(Source(name="s", url="http://x"))
    assert items == [Item("a", "Hello")]


def test_http_json_fetcher_swallows_errors():
    def boom(url, timeout): raise RuntimeError("network down")
    assert HttpJsonFetcher(opener=boom).fetch(Source(name="s", url="http://x")) == []
