"""Tests for handoff.py — the never-empty-handed /clear mechanism.
"""
from __future__ import annotations

import json
import time

from sovereign_agent.handoff import (
    handoffs_dir,
    latest_unread_handoff,
    mark_handoff_read,
    render_handoff_markdown,
    write_handoff,
)

_EVENTS = [
    {"flag": "decision-d", "payload": {"what": "use gst-launch over ffmpeg"}, "ts": 1000},
    {"flag": "commit-d", "payload": {"sha": "abc123"}, "ts": 1001},
    {"flag": "blocked-x", "payload": {"reason": "no fd yet"}, "ts": 1002},
    {"flag": "model-d", "payload": {"model": "qwen3:8b", "kind": "dispatch"}, "ts": 1003},
    {"flag": "token-usage-d", "payload": {"running_total": 500}, "ts": 1004},
    {"flag": "token-usage-d", "payload": {"running_total": 600}, "ts": 1005},
]


def test_render_includes_high_value_events_verbatim():
    md = render_handoff_markdown(_EVENTS, reason="/clear")
    assert "decision-d" in md
    assert "commit-d" in md
    assert "blocked-x" in md
    assert "Reason: /clear" in md


def test_render_never_drops_recent_events_unlike_default_compression():
    """compress_events' own default min_age_seconds=300 would filter out
    everything from an active session — a handoff explicitly wants
    everything, including the last few seconds."""
    now = time.time()
    fresh_events = [
        {"flag": "decision-d", "payload": {"what": "just now"}, "ts": now},
    ]
    md = render_handoff_markdown(fresh_events)
    assert "decision-d" in md
    assert "not compressed" not in md  # would appear if too-recent filtering kicked in


def test_write_handoff_creates_a_real_file(tmp_path):
    path = write_handoff(tmp_path, _EVENTS, reason="/clear")
    assert path.is_file()
    assert path.parent == handoffs_dir(tmp_path)
    assert "decision-d" in path.read_text(encoding="utf-8")


def test_write_handoff_sets_the_unread_pointer(tmp_path):
    path = write_handoff(tmp_path, _EVENTS, reason="/clear")
    found = latest_unread_handoff(tmp_path)
    assert found == path


def test_mark_handoff_read_clears_the_pointer(tmp_path):
    write_handoff(tmp_path, _EVENTS, reason="/clear")
    assert latest_unread_handoff(tmp_path) is not None
    mark_handoff_read(tmp_path)
    assert latest_unread_handoff(tmp_path) is None


def test_mark_handoff_read_is_idempotent_when_nothing_pending(tmp_path):
    mark_handoff_read(tmp_path)  # no pointer file at all yet — must not raise
    assert latest_unread_handoff(tmp_path) is None


def test_latest_unread_handoff_none_when_no_events_ever_written(tmp_path):
    assert latest_unread_handoff(tmp_path) is None


def test_latest_unread_handoff_survives_a_missing_file_gracefully(tmp_path):
    path = write_handoff(tmp_path, _EVENTS, reason="/clear")
    path.unlink()  # simulate the file being deleted out from under the pointer
    assert latest_unread_handoff(tmp_path) is None


def test_second_write_handoff_becomes_the_new_unread_pointer(tmp_path):
    first = write_handoff(tmp_path, _EVENTS, reason="/clear")
    second = write_handoff(tmp_path, _EVENTS, reason="/clear again")
    assert first != second
    assert latest_unread_handoff(tmp_path) == second
