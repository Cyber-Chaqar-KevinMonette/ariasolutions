"""Tests for command_bridge — the cockpit→server command queue."""
from __future__ import annotations

import json

import pytest

from sovereign_agent.discord_admin.command_bridge import (
    WHITELIST,
    enqueue,
    pending,
    record_result,
    render_help,
    result_for,
)


def test_enqueue_whitelist_only(tmp_path):
    rid = enqueue(tmp_path, "setup-all")
    assert len(rid) == 12
    with pytest.raises(ValueError):
        enqueue(tmp_path, "rm -rf /")          # never arbitrary
    with pytest.raises(ValueError):
        enqueue(tmp_path, "")


def test_round_trip_pending_then_result(tmp_path):
    rid = enqueue(tmp_path, "audit")
    jobs = pending(tmp_path)
    assert [j["id"] for j in jobs] == [rid]
    assert jobs[0]["cmd"] == "audit"
    record_result(tmp_path, rid, "🧭 worksheet…")
    assert pending(tmp_path) == []             # answered = done
    assert result_for(tmp_path, rid) == "🧭 worksheet…"
    assert result_for(tmp_path, "nope") is None


def test_cleanup_carries_its_phrase_as_args(tmp_path):
    rid = enqueue(tmp_path, "cleanup", "DELETE ORPHANS")
    assert pending(tmp_path)[0]["args"] == "DELETE ORPHANS"
    record_result(tmp_path, rid, "done")


def test_stale_jobs_expire_instead_of_surprising_the_server(tmp_path):
    """A command queued while the bot was down for over an hour must NOT
    fire later out of nowhere — it answers itself as expired."""
    rid = enqueue(tmp_path, "setup")
    assert pending(tmp_path, now=__import__("time").time() + 7200) == []
    assert "expired" in (result_for(tmp_path, rid) or "")


def test_corrupt_lines_never_crash(tmp_path):
    q = tmp_path / "discord_admin" / "command_queue.ndjson"
    q.parent.mkdir(parents=True)
    q.write_text('{"id": "ok1", "ts": 9999999999, "cmd": "seed", "args": ""}\n'
                 "NOT JSON\n" + json.dumps({"cmd": "evil-unknown"}) + "\n",
                 encoding="utf-8")
    jobs = pending(tmp_path, now=9999999999.0)
    assert [j["id"] for j in jobs] == ["ok1"]  # bad lines skipped, quietly


def test_help_teaches_every_command():
    out = render_help()
    for cmd in WHITELIST:
        assert f"/server {cmd}" in out


def test_grant_is_bridgeable(tmp_path):
    """grant-bridge-d (Kevin, 2026-07-27): "give Theodore full access" —
    a grant can be queued/answered through the same bridge as every other
    server command, without Kevin needing to type /grant in Discord."""
    assert "grant" in WHITELIST
    rid = enqueue(tmp_path, "grant", "1465498390656843909 owner-pass 36500")
    assert pending(tmp_path)[0]["args"] == "1465498390656843909 owner-pass 36500"
    record_result(tmp_path, rid, "⏳ granted Theodore OWNER-PASS for 36500d.")
    assert "granted" in result_for(tmp_path, rid)
