"""Tests for bot_services — the cockpit's Discord-service toggle.

All through injectable runners — no test ever touches real systemd.
"""
from __future__ import annotations

import json

from sovereign_agent.bot_services import (
    UNITS,
    pause_for_production,
    render_states,
    restart,
    restart_duty,
    resume_after_production,
    service_states,
    states_line,
    toggle,
)


def _runner_ok(states):
    """A fake systemctl: `show` answers from `states`, start/stop succeed
    and are recorded."""
    calls = []

    def run(args):
        calls.append(args)
        if "show" in args:
            unit = args[3]
            st, pid = states.get(unit, ("inactive", 0))
            return 0, f"ActiveState={st}\nMainPID={pid}\n"
        return 0, ""

    run.calls = calls
    return run


def test_service_states_parses_systemd_truth():
    r = _runner_ok({"aria-bot.service": ("active", 4242),
                    "aria-duty.service": ("inactive", 0)})
    st = service_states(runner=r)
    assert st["aria-bot.service"] == {"active": True, "state": "active",
                                      "pid": 4242}
    assert st["aria-duty.service"]["active"] is False


def test_service_states_degrades_to_unknown_never_guesses():
    st = service_states(runner=lambda a: (1, "boom"))
    for unit in UNITS:
        assert st[unit]["active"] is None and st[unit]["state"] == "unknown"


def test_toggle_starts_both_units_and_ledgers(tmp_path):
    r = _runner_ok({u: ("active", 7) for u in UNITS})
    out = toggle(True, runner=r, data_dir=tmp_path)
    verbs = [a[2] for a in r.calls if a[2] in ("start", "stop")]
    assert verbs == ["start", "start"]          # both units, systemd only
    assert "STARTED" in out and "aria-bot ◉" in out
    ledger = tmp_path / "discord_duty" / "service_toggle.ndjson"
    rec = json.loads(ledger.read_text().splitlines()[0])
    assert rec["action"] == "start" and all(rec["results"].values())


def test_toggle_stop_receipt(tmp_path):
    r = _runner_ok({u: ("inactive", 0) for u in UNITS})
    out = toggle(False, runner=r, data_dir=tmp_path)
    assert "STOPPED" in out and "▪" in out


def test_restart_hits_both_units_via_the_atomic_systemd_verb(tmp_path):
    """discord-control-d: systemctl's own restart, not a separate
    stop+start pair (which would risk a half-stopped gap on failure)."""
    r = _runner_ok({u: ("active", 7) for u in UNITS})
    out = restart(runner=r, data_dir=tmp_path)
    verbs = [a[2] for a in r.calls if a[2] in ("start", "stop", "restart")]
    assert verbs == ["restart", "restart"]
    assert "RESTARTED" in out and "aria-bot ◉" in out
    ledger = tmp_path / "discord_duty" / "service_toggle.ndjson"
    rec = json.loads(ledger.read_text().splitlines()[0])
    assert rec["action"] == "restart" and all(rec["results"].values())


def test_restart_duty_hits_only_aria_duty(tmp_path):
    """Kevin, 2026-07-28: 'add a button and command for me to restart it'
    — aria-duty specifically, real incident: its Playwright scraper
    leaked ~5GB->~10GB RSS over a few hours, starving movie generation
    of RAM. Restarting just this unit must NOT touch aria-bot at all."""
    r = _runner_ok({u: ("active", 7) for u in UNITS})
    out = restart_duty(runner=r, data_dir=tmp_path)
    restart_calls = [a for a in r.calls if "restart" in a]
    assert restart_calls == [["systemctl", "--user", "restart", "aria-duty.service"]]
    assert "RESTARTED" in out and "aria-duty" in out

    ledger = tmp_path / "discord_duty" / "service_toggle.ndjson"
    rec = json.loads(ledger.read_text().splitlines()[0])
    assert rec["units"] == ["aria-duty.service"]


def test_restart_still_defaults_to_both_units(tmp_path):
    r = _runner_ok({u: ("active", 7) for u in UNITS})
    restart(runner=r, data_dir=tmp_path)
    ledger = tmp_path / "discord_duty" / "service_toggle.ndjson"
    rec = json.loads(ledger.read_text().splitlines()[0])
    assert rec["units"] == list(UNITS)


def test_restart_reports_issues_honestly(tmp_path):
    def bad_runner(args):
        if "show" in args:
            return 0, "ActiveState=failed\nMainPID=0\n"
        return 1, "unit not found"
    out = restart(runner=bad_runner, data_dir=tmp_path)
    assert "issues" in out


def test_render_states_shows_pids_and_teaches_the_toggle():
    r = _runner_ok({"aria-bot.service": ("active", 99),
                    "aria-duty.service": ("failed", 0)})
    out = render_states(runner=r)
    assert "RUNNING (pid 99)" in out
    assert "failed" in out
    assert "/bots on" in out and "/bots off" in out


def test_states_line_is_compact():
    r = _runner_ok({"aria-bot.service": ("active", 1),
                    "aria-duty.service": ("active", 2)})
    assert states_line(runner=r) == "aria-bot ◉ · aria-duty ◉"


def test_watch_status_carries_services_and_mirror(tmp_path):
    """services-d + mirror-d: the watch header names the services; a live
    delivery mirrors each find's text into the feed."""
    proj = tmp_path / "bot_projects" / "scout-lego"
    proj.mkdir(parents=True)
    rec = {"ts": 1000.0, "mode": "live", "polled": ["sd-lego"],
           "new": [{"source": "sd-lego", "id": "1",
                    "text": "LEGO UCS Falcon $649", "url": "http://x"}],
           "deliveries": [{"sent": True, "dry_run": False, "detail": "sent"}]}
    (proj / "runs.jsonl").write_text(json.dumps(rec) + "\n", encoding="utf-8")
    from sovereign_agent.discord_watch import duty_status, gather_activity
    rows = gather_activity(tmp_path, now=2000.0)
    texts = [r.text for r in rows]
    assert any("posted: LEGO UCS Falcon" in t for t in texts), texts
    s = duty_status(tmp_path, now=2000.0)
    assert "services" in s                       # present even if unknown


# ── pause/resume for movie production (Kevin, 2026-07-29: "make sure the
# bots automatically pause while episodes are being produced... to
# prevent memory leaks" — then: "if people try to message her or do
# pings... make sure we send them a message... leave an ETA") ─────────────
#
# Only aria-duty.service (the real Playwright-scraper RAM leak) ever gets
# stopped — aria-bot.service (the Discord gateway) MUST stay up so it can
# actually reply to anyone who messages during production. That's driven
# by the production flag file these functions also write/clear.


def test_pause_for_production_stops_only_aria_duty_not_aria_bot(tmp_path):
    r = _runner_ok({u: ("active", 7) for u in UNITS})
    was_active, receipt = pause_for_production(runner=r, data_dir=tmp_path)
    assert was_active is True
    assert "STOPPED" in receipt
    stop_calls = [a for a in r.calls if a[2] == "stop"]
    assert stop_calls == [["systemctl", "--user", "stop", "aria-duty.service"]]


def test_pause_for_production_is_a_no_op_when_aria_duty_already_stopped(tmp_path):
    r = _runner_ok({"aria-bot.service": ("active", 1), "aria-duty.service": ("inactive", 0)})
    was_active, receipt = pause_for_production(runner=r, data_dir=tmp_path)
    assert was_active is False
    assert "already stopped" in receipt
    verbs = [a[2] for a in r.calls if a[2] in ("start", "stop")]
    assert verbs == []   # never touched systemd if there was nothing to pause


def test_resume_after_production_restarts_aria_duty_when_it_was_the_one_that_paused(tmp_path):
    r = _runner_ok({u: ("inactive", 0) for u in UNITS})
    receipt = resume_after_production(True, runner=r, data_dir=tmp_path)
    assert "STARTED" in receipt
    start_calls = [a for a in r.calls if a[2] == "start"]
    assert start_calls == [["systemctl", "--user", "start", "aria-duty.service"]]


def test_resume_after_production_never_starts_aria_duty_if_already_off(tmp_path):
    """The core safety property: if the operator had already stopped
    aria-duty deliberately before production started, this mechanism
    must never be the thing that turns it back on."""
    r = _runner_ok({u: ("inactive", 0) for u in UNITS})
    receipt = resume_after_production(False, runner=r, data_dir=tmp_path)
    assert "already stopped before production" in receipt
    verbs = [a[2] for a in r.calls if a[2] in ("start", "stop")]
    assert verbs == []   # never touched systemd


def test_pause_for_production_writes_the_flag_with_eta(tmp_path):
    from sovereign_agent.bot_services import read_production_flag

    r = _runner_ok({u: ("active", 7) for u in UNITS})
    pause_for_production(runner=r, data_dir=tmp_path, eta_minutes=12.5)
    flag = read_production_flag(tmp_path)
    assert flag is not None
    assert flag["active"] is True
    assert flag["eta_minutes"] == 12.5


def test_pause_for_production_writes_the_flag_even_when_already_stopped(tmp_path):
    """The flag reflects "production is happening right now," independent
    of whether aria-duty specifically needed stopping — Discord replies
    must still switch to away-mode."""
    from sovereign_agent.bot_services import read_production_flag

    r = _runner_ok({u: ("inactive", 0) for u in UNITS})
    pause_for_production(runner=r, data_dir=tmp_path, eta_minutes=3)
    assert read_production_flag(tmp_path) is not None


def test_resume_after_production_always_clears_the_flag(tmp_path):
    from sovereign_agent.bot_services import read_production_flag

    r = _runner_ok({u: ("active", 7) for u in UNITS})
    pause_for_production(runner=r, data_dir=tmp_path, eta_minutes=5)
    assert read_production_flag(tmp_path) is not None
    resume_after_production(True, runner=r, data_dir=tmp_path)
    assert read_production_flag(tmp_path) is None


def test_read_production_flag_is_none_when_never_written(tmp_path):
    from sovereign_agent.bot_services import read_production_flag
    assert read_production_flag(tmp_path) is None


def test_read_production_flag_degrades_honestly_on_corrupt_file(tmp_path):
    from sovereign_agent.bot_services import read_production_flag
    (tmp_path / "movie_production.json").write_text("not valid json {{{", encoding="utf-8")
    assert read_production_flag(tmp_path) is None
