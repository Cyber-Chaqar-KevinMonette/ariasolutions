"""R5 tests — source-health telemetry, credential probes, ledger, compaction."""
from __future__ import annotations

import json
import time

from sovereign_agent.bot_projects import BotProject, projects_dir, save, slugify
from sovereign_agent.discord_runtime.bookkeeping import (
    FAILING_THRESHOLD,
    compact_all_projects,
    compact_runs,
    make_outcome_recorder,
    read_ledger,
    read_source_health,
    record_fetch_outcome,
    update_ledger,
)
from sovereign_agent.discord_runtime.sources import Source


# ── 5a: source-health telemetry ─────────────────────────────────────────────
def test_fetch_outcomes_accumulate_and_reset(tmp_path):
    record_fetch_outcome(tmp_path, "P", "feed", False, "HTTP 404", now=100)
    record_fetch_outcome(tmp_path, "P", "feed", False, "HTTP 404", now=160)
    h = read_source_health(tmp_path, "P")["feed"]
    assert h["consecutive_failures"] == 2 and h["last_error"] == "HTTP 404"
    record_fetch_outcome(tmp_path, "P", "feed", True, "3 item(s)", now=220)
    h = read_source_health(tmp_path, "P")["feed"]
    assert h["consecutive_failures"] == 0 and h["total_failures"] == 2
    assert h["last_ok_ts"] == 220


def test_fetchers_report_outcomes_via_hook():
    from sovereign_agent.discord_runtime.fetchers import ChangeFetcher, RssFetcher
    seen = []

    def hook(name, ok, detail):
        seen.append((name, ok, detail))

    class _Err404(Exception):
        code = 404

    def opener_404(url, timeout):
        raise _Err404()

    RssFetcher(opener=opener_404, on_outcome=hook).fetch(Source(name="s", url="http://x"))
    assert seen[-1] == ("s", False, "HTTP 404")

    class _Resp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b"page content"

    ChangeFetcher(opener=lambda u, timeout: _Resp(), on_outcome=hook).fetch(
        Source(name="s2", url="http://x"))
    assert seen[-1][0] == "s2" and seen[-1][1] is True


def test_bot_health_flags_dead_link(tmp_path):
    from sovereign_agent.bot_health import NEEDS_ATTENTION, assess_bot
    from sovereign_agent.discord_runtime.sources import add_source
    add_source(tmp_path, "P", Source(name="feed", url="http://x",
                                     allowed_min_interval_s=60))
    for i in range(FAILING_THRESHOLD):
        record_fetch_outcome(tmp_path, "P", "feed", False, "HTTP 404", now=100 + i)
    a = assess_bot(tmp_path, BotProject(project_name="P", kind="notification-feed"),
                   now=1000)
    assert a.level == NEEDS_ATTENTION
    assert any("looks dead" in r for r in a.reasons)


def test_runtime_records_health_through_build_runtime(tmp_path):
    """End-to-end: a dead URL polled via the real factory lands in telemetry."""
    from sovereign_agent.discord_runtime.runtime import build_runtime
    from sovereign_agent.discord_runtime.sources import add_source
    save(BotProject(project_name="P", kind="notification-feed"), tmp_path)
    add_source(tmp_path, "P", Source(name="feed", url="http://127.0.0.1:1/dead",
                                     kind="rss", allowed_min_interval_s=60))
    rt = build_runtime(BotProject(project_name="P", kind="notification-feed"),
                       tmp_path)
    rt.poll_once(now=1000.0)     # URLError → recorded, never raises
    h = read_source_health(tmp_path, "P")["feed"]
    assert h["consecutive_failures"] == 1 and h["last_error"]


# ── 5b: credential probes (injected openers, no network) ────────────────────
def test_probe_webhook_alive_and_dead(tmp_path):
    from sovereign_agent.credentials import probe_webhook

    class _Resp:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *a): return False

    ok, detail = probe_webhook("https://discord.com/api/webhooks/1/x",
                               opener=lambda u, timeout: _Resp())
    assert ok and "200" in detail

    class _Err404(Exception):
        code = 404

    def dead(u, timeout):
        raise _Err404()

    ok, detail = probe_webhook("https://discord.com/api/webhooks/1/x", opener=dead)
    assert not ok and "deleted" in detail


def test_probe_bot_token_invalid():
    from sovereign_agent.credentials import probe_bot_token

    class _Err401(Exception):
        code = 401

    def bad(url, headers, timeout):
        assert headers["Authorization"].startswith("Bot ")
        raise _Err401()

    ok, detail = probe_bot_token("token-value", opener=bad)
    assert not ok and "401" in detail


def test_check_all_skips_unset_and_never_leaks(tmp_path, monkeypatch):
    from sovereign_agent.credentials import check_all, set_secret
    vault = tmp_path / "v.env"
    secret_url = "https://discord.com/api/webhooks/1/SECRETPART"
    set_secret("DISCORD_WEBHOOK_URL", secret_url, vault)

    class _Resp:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *a): return False

    results = check_all(vault, webhook_opener=lambda u, timeout: _Resp())
    by = {r["name"]: r for r in results}
    assert by["DISCORD_WEBHOOK_URL"]["ok"] is True
    assert by["DISCORD_BOT_TOKEN"]["checked"] is False        # unset → skipped
    assert "SECRETPART" not in json.dumps(results)            # never the value


def test_probe_stripe_key_matrix():
    from sovereign_agent.credentials import probe_stripe_key

    class _Resp:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def alive(url, headers, timeout):
        assert headers["Authorization"] == "Bearer rk_live_abc"
        assert "api.stripe.com" in url
        return _Resp()

    ok, detail = probe_stripe_key("rk_live_abc", opener=alive)
    assert ok and "LIVE" in detail

    class _Err401(Exception):
        code = 401

    def dead(url, headers, timeout):
        raise _Err401()

    ok, detail = probe_stripe_key("sk_live_dead", opener=dead)
    assert not ok and "revoked" in detail

    class _Err403(Exception):
        code = 403

    def restricted(url, headers, timeout):
        raise _Err403()

    # restricted-from-Account-read still proves the key is alive
    ok, detail = probe_stripe_key("rk_live_narrow", opener=restricted)
    assert ok and "ALIVE" in detail

    assert probe_stripe_key("")[1] == "not set"


def test_check_all_probes_stripe_and_never_leaks(tmp_path):
    from sovereign_agent.credentials import check_all, set_secret
    vault = tmp_path / "v.env"
    set_secret("STRIPE_SECRET_KEY", "rk_live_SUPERSECRET", vault)

    class _Resp:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *a): return False

    results = check_all(vault, stripe_opener=lambda u, h, t: _Resp())
    by = {r["name"]: r for r in results}
    assert by["STRIPE_SECRET_KEY"]["ok"] is True
    assert "SUPERSECRET" not in json.dumps(results)


def test_stripe_key_validation_warns_right():
    from sovereign_agent.credentials import validate_value
    assert validate_value("STRIPE_SECRET_KEY", "rk_live_good") == []
    assert validate_value("STRIPE_SECRET_KEY", "sk_live_good") == []
    assert any("TEST-mode" in w for w in
               validate_value("STRIPE_SECRET_KEY", "sk_test_oops"))
    assert any("PUBLISHABLE" in w for w in
               validate_value("STRIPE_SECRET_KEY", "pk_live_wrong"))
    assert any("start with" in w for w in
               validate_value("STRIPE_SECRET_KEY", "whoops"))


# ── 5c: ledger + compaction ─────────────────────────────────────────────────
def test_ledger_accumulates_totals(tmp_path):
    update_ledger(tmp_path, "P", lifetime_alerts=3)
    update_ledger(tmp_path, "P", lifetime_alerts=2, notes="restock watcher",
                  capabilities={"rss": "v1"})
    led = read_ledger(tmp_path, "P")
    assert led["lifetime_alerts"] == 5 and led["notes"] == "restock watcher"
    assert led["capabilities"] == {"rss": "v1"} and led["created_at"]


def _run_line(ts, sent=1, failed=0):
    return json.dumps({"ts": ts, "polled": ["s"],
                       "deliveries": [{"sent": True, "dry_run": False}] * sent
                       + [{"sent": False, "dry_run": False}] * failed})


def test_compact_rolls_old_lines_into_monthly_summaries(tmp_path):
    d = projects_dir(tmp_path) / slugify("P")
    d.mkdir(parents=True)
    now = time.time()
    old1 = now - 90 * 86400          # ~3 months ago
    old2 = now - 60 * 86400          # ~2 months ago
    fresh = now - 3600               # 1h ago
    (d / "runs.jsonl").write_text("\n".join([
        _run_line(old1, sent=2), _run_line(old1 + 60, sent=1, failed=1),
        _run_line(old2, sent=3), _run_line(fresh, sent=1)]) + "\n",
        encoding="utf-8")
    r = compact_runs(tmp_path, "P", keep_days=30, now=now)
    assert r["compacted"] == 3 and r["kept"] == 1
    lines = [json.loads(x) for x in (d / "runs.jsonl").read_text().splitlines()]
    rollups = [x for x in lines if x.get("rollup")]
    assert len(rollups) == 2                                   # two months
    assert sum(x["alerts"] for x in rollups) == 6
    assert sum(x["failures"] for x in rollups) == 1
    # lifetime totals landed in the ledger
    led = read_ledger(tmp_path, "P")
    assert led["lifetime_alerts"] == 6 and led["lifetime_failures"] == 1
    # idempotent: nothing further to compact
    assert compact_runs(tmp_path, "P", keep_days=30, now=now)["compacted"] == 0


def test_compaction_keeps_windowed_stats_truthful(tmp_path):
    """Rollups (old ts) fall outside the 30-day stats window naturally."""
    from sovereign_agent.shop_stats import bot_stats
    d = projects_dir(tmp_path) / slugify("P")
    d.mkdir(parents=True)
    now = time.time()
    (d / "runs.jsonl").write_text(
        _run_line(now - 90 * 86400, sent=5) + "\n" + _run_line(now - 60, sent=2) + "\n",
        encoding="utf-8")
    compact_runs(tmp_path, "P", keep_days=30, now=now)
    st = bot_stats(tmp_path, "P", window_days=30, now=now)
    assert st.delivered == 2                                   # only the fresh line


def test_compact_all_projects(tmp_path):
    save(BotProject(project_name="A", kind="notification-feed"), tmp_path)
    save(BotProject(project_name="B", kind="restock-alert"), tmp_path)
    results = compact_all_projects(tmp_path)
    assert set(results) == {"A", "B"}


def test_outcome_recorder_hook(tmp_path):
    rec = make_outcome_recorder(tmp_path, "P")
    rec("feed", False, "Timeout")
    assert read_source_health(tmp_path, "P")["feed"]["last_error"] == "Timeout"
