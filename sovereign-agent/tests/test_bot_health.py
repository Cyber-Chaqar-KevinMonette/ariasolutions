"""Tests for bot_health.py — bot attention awareness (cross-process, persisted)."""
from __future__ import annotations

import json

from sovereign_agent.bot_health import (
    NEEDS_ATTENTION,
    OK,
    WATCH,
    assess_bot,
    compose_bot_attention_report,
    is_bot_health_query,
    scan_bots,
)
from sovereign_agent.bot_projects import BotProject, projects_dir, save, slugify
from sovereign_agent.discord_runtime.queue import JobQueue
from sovereign_agent.discord_runtime.runtime import _project_queue_dir
from sovereign_agent.discord_runtime.sources import Source, add_source


def _p(name):
    return BotProject(project_name=name, kind="notification-feed")


def _write_run(data_dir, project, ts, sent=1):
    d = projects_dir(data_dir) / slugify(project)
    d.mkdir(parents=True, exist_ok=True)
    with open(d / "runs.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"ts": ts, "polled": ["s"],
                             "deliveries": [{"sent": True, "dry_run": False}] * sent}) + "\n")


def test_no_sources_needs_attention(tmp_path):
    a = assess_bot(tmp_path, _p("Empty"), now=1000)
    assert a.level == NEEDS_ATTENTION
    assert any("no sources" in r for r in a.reasons)


def test_healthy_bot_is_ok(tmp_path):
    add_source(tmp_path, "Good", Source(name="feed", url="http://x", allowed_min_interval_s=60))
    _write_run(tmp_path, "Good", ts=1000)
    a = assess_bot(tmp_path, _p("Good"), now=1000 + 3600)   # 1h ago
    assert a.level == OK
    assert a.sources == 1 and a.last_delivery_age_h == 1.0


def test_dead_letter_needs_attention(tmp_path):
    add_source(tmp_path, "Failing", Source(name="feed", allowed_min_interval_s=60))
    _write_run(tmp_path, "Failing", ts=1000)
    q = JobQueue(_project_queue_dir(tmp_path, "Failing"), max_attempts=1)
    q.enqueue("x", key="k", now=0)
    job = q.lease(now=0)[0]
    q.fail(job.id, now=0)                     # → dead-letter
    a = assess_bot(tmp_path, _p("Failing"), now=1000 + 3600)
    assert a.level == NEEDS_ATTENTION
    assert a.dead_letter == 1
    assert any("dead-letter" in r for r in a.reasons)


def test_quiet_feed_is_watch(tmp_path):
    add_source(tmp_path, "Quiet", Source(name="feed", allowed_min_interval_s=60))
    _write_run(tmp_path, "Quiet", ts=1000)
    now = 1000 + 3600 * 72                     # 72h later
    a = assess_bot(tmp_path, _p("Quiet"), now=now)
    assert a.level == WATCH
    assert any("quiet" in r.lower() for r in a.reasons)


def test_scan_sorts_worst_first(tmp_path):
    save(_p("A-empty"), tmp_path)             # needs-attention (no sources)
    add_source(tmp_path, "B-good", Source(name="f", allowed_min_interval_s=60))
    _write_run(tmp_path, "B-good", ts=1000)
    save(_p("B-good"), tmp_path)
    bots = scan_bots(tmp_path, now=1000 + 3600)
    assert bots[0].project == "A-empty" and bots[0].level == NEEDS_ATTENTION


def test_report_empty(tmp_path):
    assert "No bots defined" in compose_bot_attention_report(tmp_path)


def test_report_all_healthy(tmp_path):
    add_source(tmp_path, "Good", Source(name="f", allowed_min_interval_s=60))
    _write_run(tmp_path, "Good", ts=1000)
    save(_p("Good"), tmp_path)
    out = compose_bot_attention_report(tmp_path, now=1000 + 3600)
    assert "healthy" in out.lower() and "Nothing needs you" in out


def test_report_flags_problem(tmp_path):
    save(_p("Broken"), tmp_path)              # no sources
    out = compose_bot_attention_report(tmp_path, now=1000)
    assert "Broken" in out and "need attention" in out


def test_is_bot_health_query():
    assert is_bot_health_query("do any bots need attention?")
    assert is_bot_health_query("how are the bots")
    assert not is_bot_health_query("how are you feeling")
