"""Tests for shop_stats.py — usage stats derived from the runs.jsonl audit."""
from __future__ import annotations

import json

from sovereign_agent.bot_projects import projects_dir, slugify
from sovereign_agent.shop_stats import (
    aggregate_stats,
    bot_stats,
    public_stats_embed,
    read_runs,
    render_bot_digest,
    render_public_stats,
)


def _write_runs(data_dir, project, records):
    d = projects_dir(data_dir) / slugify(project)
    d.mkdir(parents=True, exist_ok=True)
    with open(d / "runs.jsonl", "w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r) + "\n")


def _rec(ts, *, polled=1, new=0, sent=0, dry=0, failed=0):
    deliveries = ([{"sent": True, "dry_run": False}] * sent
                  + [{"sent": False, "dry_run": True}] * dry
                  + [{"sent": False, "dry_run": False}] * failed)
    return {"ts": ts, "mode": "live", "polled": ["s"] * polled,
            "new": [{"source": "s", "id": str(i)} for i in range(new)],
            "deliveries": deliveries}


def test_read_runs_skips_torn_lines(tmp_path):
    d = projects_dir(tmp_path) / slugify("P")
    d.mkdir(parents=True, exist_ok=True)
    (d / "runs.jsonl").write_text(
        json.dumps(_rec(1000)) + "\n{bad line\n" + json.dumps(_rec(1001)) + "\n",
        encoding="utf-8")
    assert len(read_runs(tmp_path, "P")) == 2


def test_bot_stats_aggregates(tmp_path):
    _write_runs(tmp_path, "P", [
        _rec(1000, new=2, sent=2),
        _rec(1100, new=1, sent=1),
    ])
    st = bot_stats(tmp_path, "P", now=1200)
    assert st.cycles == 2 and st.detected == 3 and st.delivered == 3
    assert st.uptime_pct == 100.0


def test_bot_stats_uptime_with_failures(tmp_path):
    _write_runs(tmp_path, "P", [_rec(1000, sent=3, failed=1)])
    st = bot_stats(tmp_path, "P", now=1000)
    assert st.delivered == 3 and st.failed == 1
    assert st.uptime_pct == 75.0        # 3 of 4


def test_bot_stats_window_excludes_old(tmp_path):
    _write_runs(tmp_path, "P", [
        _rec(0, sent=5),                      # ancient (epoch 0)
        _rec(4_000_000, sent=1),              # recent
    ])
    st = bot_stats(tmp_path, "P", window_days=30, now=4_000_000)
    assert st.delivered == 1                  # old record excluded by 30d window


def test_digest_no_activity(tmp_path):
    st = bot_stats(tmp_path, "Empty", now=1000)
    assert "no activity" in render_bot_digest(st)


def test_digest_reads_well(tmp_path):
    _write_runs(tmp_path, "Restocks", [_rec(1000, new=2, sent=2)])
    txt = render_bot_digest(bot_stats(tmp_path, "Restocks", now=1000))
    assert "Restocks" in txt and "2 alerts delivered" in txt and "100.0% uptime" in txt


def test_aggregate_across_bots(tmp_path):
    from sovereign_agent.bot_projects import BotProject, save
    save(BotProject(project_name="A", kind="notification-feed"), tmp_path)
    save(BotProject(project_name="B", kind="restock-alert"), tmp_path)
    _write_runs(tmp_path, "A", [_rec(1000, sent=3)])
    _write_runs(tmp_path, "B", [_rec(1000, sent=2, failed=1)])
    agg = aggregate_stats(tmp_path, now=1000)
    assert agg.bots == 2 and agg.alerts == 5 and agg.failed == 1
    assert "5 alerts delivered" in render_public_stats(agg)
    emb = public_stats_embed(agg)
    assert emb["fields"][0]["value"] == "5"


def test_public_stats_empty(tmp_path):
    agg = aggregate_stats(tmp_path, now=1000)
    assert agg.bots == 0 and "standing by" in render_public_stats(agg)
