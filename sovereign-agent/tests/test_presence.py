"""Tests for presence.py — Aria awake/asleep, derived from a heartbeat."""
from __future__ import annotations

from sovereign_agent.presence import (
    AWAKE_WINDOW_S,
    presence_status,
    publish_presence,
    read_heartbeat,
    render_presence,
    touch_heartbeat,
)


def test_no_heartbeat_reads_asleep(tmp_path):
    st = presence_status(tmp_path, now=1000.0)
    assert st.awake is False and st.last_seen is None
    assert "asleep" in render_presence(st).lower()


def test_fresh_heartbeat_reads_awake(tmp_path):
    touch_heartbeat(tmp_path, now=1000.0)
    st = presence_status(tmp_path, now=1000.0 + 10)
    assert st.awake is True and st.age_s == 10
    assert st.status_word == "awake"


def test_stale_heartbeat_reads_asleep(tmp_path):
    touch_heartbeat(tmp_path, now=1000.0)
    st = presence_status(tmp_path, now=1000.0 + AWAKE_WINDOW_S + 1)
    assert st.awake is False


def test_heartbeat_round_trips_note(tmp_path):
    touch_heartbeat(tmp_path, now=5.0, note="cockpit")
    hb = read_heartbeat(tmp_path)
    assert hb["ts"] == 5.0 and hb["note"] == "cockpit"


def test_render_awake_mentions_ask_aria(tmp_path):
    touch_heartbeat(tmp_path, now=1000.0)
    st = presence_status(tmp_path, now=1000.0)
    assert "awake" in render_presence(st).lower()


def test_publish_only_on_transition(tmp_path):
    # first call (asleep, no prior) → publishes the transition (dry-run, not sent)
    published1, st1 = publish_presence(tmp_path, live=False, now=1000.0)
    assert st1.awake is False
    # second call, still asleep → no transition → no publish
    published2, _ = publish_presence(tmp_path, live=False, now=1001.0)
    assert published2 is False
    # now she wakes → transition → attempts publish (dry-run, so sent False,
    # but the state file flips)
    touch_heartbeat(tmp_path, now=1002.0)
    _, st3 = publish_presence(tmp_path, live=False, now=1002.0)
    assert st3.awake is True
    # staying awake → no further transition
    published4, _ = publish_presence(tmp_path, live=False, now=1003.0)
    assert published4 is False


def test_publish_dry_run_never_sends(tmp_path):
    touch_heartbeat(tmp_path, now=1000.0)
    published, _ = publish_presence(tmp_path, live=False, now=1000.0)
    assert published is False   # dry-run: nothing actually sent
