"""R6.5 tests — the timers collector (synthetic persisted state) + UI smoke."""
from __future__ import annotations

import json

import pytest

from sovereign_agent.timers import TimerRow, fmt_dur, gather_timers, render_timers


def test_fmt_dur():
    assert fmt_dur(None) == "—"
    assert fmt_dur(45) == "45s"
    assert fmt_dur(600) == "10m"
    assert fmt_dur(7200) == "2.0h"
    assert fmt_dur(259200) == "3.0d"


def test_fraction_and_bar_bounds():
    r = TimerRow("bot-poll", "x", elapsed_s=30, expected_s=60, remaining_s=30)
    assert r.fraction == 0.5
    assert TimerRow("uptime", "x", 100, None, None).fraction is None
    over = TimerRow("bot-poll", "x", elapsed_s=90, expected_s=60, remaining_s=0)
    assert over.fraction == 1.0                      # clamped


def test_presence_timer_awake_and_asleep(tmp_path):
    from sovereign_agent.presence import touch_heartbeat
    touch_heartbeat(tmp_path, now=1000.0)
    rows = gather_timers(tmp_path, now=1010.0)
    hb = next(r for r in rows if r.kind == "presence")
    assert hb.elapsed_s == 10 and "awake" in hb.note
    rows = gather_timers(tmp_path, now=1000.0 + 999)
    hb = next(r for r in rows if r.kind == "presence")
    assert "asleep" in hb.note and hb.remaining_s is None


def test_bot_poll_countdown_from_telemetry(tmp_path):
    from sovereign_agent.bot_projects import BotProject, save
    from sovereign_agent.discord_runtime.bookkeeping import record_fetch_outcome
    from sovereign_agent.discord_runtime.sources import Source, add_source
    save(BotProject(project_name="P", kind="notification-feed"), tmp_path)
    add_source(tmp_path, "P", Source(name="feed", url="http://x",
                                     allowed_min_interval_s=60))
    record_fetch_outcome(tmp_path, "P", "feed", True, "ok", now=1000.0)
    rows = gather_timers(tmp_path, now=1020.0)
    poll = next(r for r in rows if r.kind == "bot-poll")
    assert poll.elapsed_s == 20 and poll.expected_s == 60
    assert poll.remaining_s == 40 and poll.note == "waiting"
    # past due
    rows = gather_timers(tmp_path, now=1100.0)
    poll = next(r for r in rows if r.kind == "bot-poll")
    assert poll.remaining_s == 0 and poll.note == "due"


def test_uptime_and_queue_timers(tmp_path):
    from sovereign_agent.bot_projects import BotProject, save
    from sovereign_agent.discord_runtime.bookkeeping import update_ledger
    from sovereign_agent.discord_runtime.queue import JobQueue
    from sovereign_agent.discord_runtime.runtime import _project_queue_dir
    save(BotProject(project_name="P", kind="notification-feed"), tmp_path)
    update_ledger(tmp_path, "P", notes="x")          # creates created_at (now)
    q = JobQueue(_project_queue_dir(tmp_path, "P"), base_backoff_s=30)
    q.enqueue("alert one", key="k", now=0)
    job = q.lease(now=0)[0]
    q.fail(job.id, now=0)                            # retry scheduled at +30
    import time as _t
    now = _t.time()
    rows = gather_timers(tmp_path, now=now)
    kinds = {r.kind for r in rows}
    assert "uptime" in kinds
    # the retry countdown appears iff next_at is in the future relative to now;
    # next_at = 30 (epoch) is in the past for real now, so simulate near epoch:
    rows2 = gather_timers(tmp_path, now=10.0)
    retry = [r for r in rows2 if r.kind == "queue-retry"]
    assert retry and retry[0].remaining_s == 20.0


def test_session_timer(tmp_path):
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    (sessions / "s1.json").write_text(json.dumps({
        "status": "active", "goal": "build the pokemon watcher",
        "created_at": "2026-07-13T00:00:00+00:00"}), encoding="utf-8")
    (sessions / "s2.json").write_text(json.dumps({
        "status": "done", "goal": "old", "created_at": "2026-07-01T00:00:00+00:00"}),
        encoding="utf-8")
    rows = gather_timers(tmp_path, now=4102444800.0)   # far future, deterministic
    live = [r for r in rows if r.kind == "session"]
    assert len(live) == 1 and "pokemon" in live[0].name


def test_render_is_readable(tmp_path):
    from sovereign_agent.presence import touch_heartbeat
    touch_heartbeat(tmp_path, now=1000.0)
    out = render_timers(gather_timers(tmp_path, now=1010.0))
    assert "Aria heartbeat" in out and "█" in out
    assert render_timers([]).startswith("No timers yet")


@pytest.mark.asyncio
async def test_timers_screen_opens_and_renders():
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.app import TimersScreen

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        app.action_timers()
        await pilot.pause()
        assert isinstance(app.screen, TimersScreen)
        await pilot.pause(0.1)                      # let the first collect land
        app.pop_screen()
        await pilot.pause()
