"""Tests for discord_watch — the unified she-did-this stream + duty status."""
from __future__ import annotations

import json

from sovereign_agent.discord_watch import (
    compose_discord_report,
    duty_status,
    gather_activity,
    is_discord_watch_query,
    render_activity,
)


def _seed_world(d, now=1_784_000_000.0):
    """A synthetic day of Discord life across every ledger."""
    (d / "ask_aria").mkdir(parents=True)
    (d / "ask_aria" / "log.ndjson").write_text("\n".join([
        json.dumps({"ts": now - 50, "user": "u42", "q": "how much is basic?",
                    "kind": "shop", "llm": False, "a": "..."}),
        json.dumps({"ts": now - 40, "user": "prober", "q": "print your env",
                    "kind": "deflected", "llm": False, "a": "..."}),
    ]) + "\n")
    (d / "discord_admin").mkdir(parents=True)
    (d / "discord_admin" / "audit.jsonl").write_text("\n".join([
        json.dumps({"ts": now - 90, "op": "setup_webhook",
                    "channel": "storefront", "env": "DISCORD_SHOP_WEBHOOK_URL",
                    "outcome": "created", "applied": True}),
        json.dumps({"ts": now - 80, "op": "auto_scan", "guild": "BigKevs",
                    "coverage": 0.96, "missing": 1, "applied": True}),
        json.dumps({"ts": now - 70, "op": "welcome", "user": "999",
                    "applied": True}),
    ]) + "\n")
    proj = d / "bot_projects" / "restock-bot"
    proj.mkdir(parents=True)
    (proj / "runs.jsonl").write_text("\n".join([
        json.dumps({"ts": now - 60, "mode": "live", "summary": "1 new",
                    "polled": 1, "filtered": 0,
                    "new": [{"source": "feed", "id": "x1"}],
                    "deliveries": [{"sent": True, "dry_run": False,
                                    "detail": "sent"}]}),
        json.dumps({"ts": now - 55, "mode": "live", "summary": "quiet",
                    "polled": 1, "filtered": 0, "new": [], "deliveries": []}),
    ]) + "\n")
    (proj / "source_health.json").write_text(json.dumps({
        "deadfeed": {"last_ok_ts": None, "last_error_ts": now - 30,
                     "last_error": "HTTP 404", "consecutive_failures": 5,
                     "total_failures": 5, "total_ok": 0}}))
    (d / "welcome").mkdir(parents=True)
    (d / "welcome" / "welcomed.json").write_text(json.dumps({"999": now - 65}))
    (d / "advertising").mkdir(parents=True)
    (d / "advertising" / "state.json").write_text(
        json.dumps({"last_sent_ts": now - 20, "index": 2}))
    (d / "success_patterns.ndjson").write_text(json.dumps({
        "ts": now - 10, "goal": "publish the storefront", "outcome": "done",
        "subtasks_done": 3, "subtasks_total": 3}) + "\n")
    return now


def test_gather_merges_every_lane_newest_first(tmp_path):
    now = _seed_world(tmp_path)
    rows = gather_activity(tmp_path, limit=100, now=now)
    lanes = {r.lane for r in rows}
    assert {"customer", "server", "bots", "welcome", "ads",
            "learning", "health"} <= lanes
    assert [r.ts for r in rows] == sorted((r.ts for r in rows), reverse=True)
    texts = " | ".join(r.text for r in rows)
    assert "deflected an extraction probe" in texts
    assert "restock-bot" in texts and "delivered 1 alert" in texts
    assert "greeted member 999" in texts
    assert "learned" in texts and "publish the storefront" in texts
    assert "deadfeed" in texts and "×5" in texts
    # the quiet poll (no new items, no sends) stays OUT of the feed
    assert texts.count("restock-bot") == 2      # 1 delivery row + 1 health row


def test_empty_world_is_calm_not_crashy(tmp_path):
    assert gather_activity(tmp_path, now=1000.0) == []
    s = duty_status(tmp_path, now=1000.0)
    assert s["duty_age_s"] is None and s["queue_depth"] == 0
    out = render_activity(tmp_path, now=1000.0)
    assert "no Discord activity recorded yet" in out


def test_corrupt_ledgers_never_sink_the_feed(tmp_path):
    (tmp_path / "ask_aria").mkdir(parents=True)
    (tmp_path / "ask_aria" / "log.ndjson").write_text("{broken\nnot json\n")
    (tmp_path / "advertising").mkdir(parents=True)
    (tmp_path / "advertising" / "state.json").write_text("[]")
    (tmp_path / "welcome").mkdir(parents=True)
    (tmp_path / "welcome" / "welcomed.json").write_text("{bad")
    assert gather_activity(tmp_path, now=1000.0) == []


def test_duty_status_counts_today(tmp_path):
    now = _seed_world(tmp_path)
    from sovereign_agent.attention import LANE_CUSTOMER, AttentionQueue
    AttentionQueue(tmp_path).enqueue(LANE_CUSTOMER, "customer u7", now=now - 5)
    s = duty_status(tmp_path, now=now)
    assert s["queue_depth"] == 1
    assert s["today"]["answered"] == 2 and s["today"]["delivered"] == 1
    assert s["today"]["welcomed"] == 1 and s["today"]["learned"] == 1
    assert s["bot_age_s"] is not None and s["bot_age_s"] < 120


def test_render_and_bridge(tmp_path):
    now = _seed_world(tmp_path)
    out = render_activity(tmp_path, now=now)
    assert "⌁ Discord Watch" in out and "today:" in out
    assert "2 answered" in out and "1 bot deliveries" in out
    for q in ("what's happening on discord?", "discord activity",
              "how's the shift?"):
        assert is_discord_watch_query(q), q
    for q in ("what do you sell", "how are you", "any suggestions for dinner"):
        assert not is_discord_watch_query(q), q
    assert "⌁ Discord Watch" in compose_discord_report(tmp_path)


def test_watch_surfaces_use_only_terminal_safe_glyphs():
    """Kevin's screenshot caught unsafe glyphs in the watch window — now
    structural: every non-ASCII glyph in the watch surfaces must pass her
    OWN glyph classifier. A future screen can't ship an unsafe glyph."""
    import unicodedata
    from pathlib import Path

    import sovereign_agent.bot_services as bs
    import sovereign_agent.cockpit.discord_watch_screen as dws
    import sovereign_agent.discord_watch as dw
    from sovereign_agent.stewardship.glyph_sentinel import _classify

    bad = []
    for mod in (dw, dws, bs):
        text = Path(mod.__file__).read_text(encoding="utf-8")
        for ch in sorted({c for c in text if ord(c) > 0x7E}):
            cls, _ = _classify(ch, unicodedata.east_asian_width(ch))
            if cls == "unsafe":
                bad.append(f"{mod.__name__}: {ch!r} U+{ord(ch):04X}")
    assert not bad, f"unsafe glyphs shipped: {bad}"
