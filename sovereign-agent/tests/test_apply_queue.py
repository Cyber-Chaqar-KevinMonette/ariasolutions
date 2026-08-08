"""Behavior tests for aria-apply-queue — prove the durable queue + quarantine
registry actually sequence, persist, survive a crash, and route failures."""
from __future__ import annotations

import json
from functools import partial
from pathlib import Path

from sovereign_agent.apply_queue.store import (
    ApplyQueueStore,
    QuarantineRegistry,
)


# ── queue: sequencing & idempotency ────────────────────────────────────────

def test_enqueue_orders_by_dependency_priority(tmp_path):
    q = ApplyQueueStore(root=tmp_path / "q")
    # deliberately out of order; PRIORITY puts own-mind before alphabetical strays
    q.enqueue(["aria-zzz-last", "aria-own-mind", "aria-aaa-mid"])
    slugs = q.pending_slugs()
    assert slugs[0] == "aria-own-mind", slugs           # priority chain first
    assert slugs[1:] == ["aria-aaa-mid", "aria-zzz-last"]  # rest alphabetical
    assert [it.seq for it in q.active()] == [1, 2, 3]   # contiguous 1-based seq


def test_enqueue_is_idempotent(tmp_path):
    q = ApplyQueueStore(root=tmp_path / "q")
    q.enqueue(["aria-foo", "aria-bar"])
    q.enqueue(["aria-foo"])                 # selecting twice must not double-queue
    assert q.pending_slugs().count("aria-foo") == 1
    assert len(q.active()) == 2


# ── queue: state transitions remove items / route them ─────────────────────

def test_applied_module_leaves_the_active_queue(tmp_path):
    q = ApplyQueueStore(root=tmp_path / "q")
    q.enqueue(["aria-foo", "aria-bar"])
    q.mark("aria-foo", "applied")
    assert "aria-foo" not in q.pending_slugs()
    assert q.pending_slugs() == ["aria-bar"]


def test_quarantined_module_leaves_the_active_queue(tmp_path):
    q = ApplyQueueStore(root=tmp_path / "q")
    q.enqueue(["aria-foo"])
    q.mark("aria-foo", "quarantined")
    assert q.pending_slugs() == []
    # but it's still in the full history
    assert any(it.slug == "aria-foo" for it in q.all_items())


def test_current_view_file_tracks_active_and_shrinks(tmp_path):
    q = ApplyQueueStore(root=tmp_path / "q")
    q.enqueue(["aria-foo", "aria-bar"])
    data = json.loads(q.current.read_text())
    assert data["count"] == 2
    q.mark("aria-foo", "applied")
    data = json.loads(q.current.read_text())
    assert data["count"] == 1                     # Kevin watches it shrink
    assert data["active"][0]["slug"] == "aria-bar"


# ── queue: durability ──────────────────────────────────────────────────────

def test_state_survives_reconstruction_from_log(tmp_path):
    root = tmp_path / "q"
    q1 = ApplyQueueStore(root=root)
    q1.enqueue(["aria-foo", "aria-bar"])
    q1.mark("aria-foo", "applied")
    # a fresh store reading the same on-disk log sees identical state
    q2 = ApplyQueueStore(root=root)
    assert q2.pending_slugs() == ["aria-bar"]


def test_corrupt_log_line_is_skipped_not_fatal(tmp_path):
    root = tmp_path / "q"
    q = ApplyQueueStore(root=root)
    q.enqueue(["aria-foo"])
    with open(q.log, "a", encoding="utf-8") as fh:
        fh.write("{ this is not json\n")          # a torn write
    # still readable; the good record survives
    assert q.pending_slugs() == ["aria-foo"]


def test_clear_archives_log_and_empties_queue(tmp_path):
    root = tmp_path / "q"
    q = ApplyQueueStore(root=root)
    q.enqueue(["aria-foo"])
    q.clear()
    assert q.pending_slugs() == []
    assert list(root.glob("queue.*.ndjson.archive")), "log should be archived, not deleted"


# ── quarantine registry ────────────────────────────────────────────────────

def test_quarantine_records_and_lists(tmp_path):
    qr = QuarantineRegistry(root=tmp_path / "quar")
    qr.quarantine("aria-broken", "tests failed", snapshot_path="/snap", gate_verdict="RISK")
    rec = qr.show("aria-broken")
    assert rec is not None
    assert rec.status == "quarantined"
    assert rec.reason == "tests failed"
    assert [r.slug for r in qr.active()] == ["aria-broken"]


def test_quarantine_clear_marks_fixed(tmp_path):
    qr = QuarantineRegistry(root=tmp_path / "quar")
    qr.quarantine("aria-broken", "rolled back")
    assert qr.clear("aria-broken") is True
    assert qr.show("aria-broken").status == "cleared"
    assert qr.active() == []                       # cleared ⇒ no longer active
    assert qr.clear("aria-nonexistent") is False


def test_quarantine_rejects_path_traversal(tmp_path):
    qr = QuarantineRegistry(root=tmp_path / "quar")
    import pytest
    with pytest.raises(ValueError):
        qr.quarantine("../escape", "nope")


# ── CLI surface ────────────────────────────────────────────────────────────

def _patch_cli(monkeypatch, tmp_path):
    import sovereign_agent.apply_queue.__main__ as cli
    monkeypatch.setattr(cli, "ApplyQueueStore",
                        partial(ApplyQueueStore, root=tmp_path / "q"))
    monkeypatch.setattr(cli, "QuarantineRegistry",
                        partial(QuarantineRegistry, root=tmp_path / "quar"))
    return cli


def test_cli_enqueue_next_mark_flow(monkeypatch, tmp_path, capsys):
    cli = _patch_cli(monkeypatch, tmp_path)
    assert cli.main(["enqueue", "foo", "bar"]) == 0   # bare slugs get aria- prefix
    capsys.readouterr()
    assert cli.main(["next"]) == 0
    nxt = capsys.readouterr().out.strip()
    assert nxt.startswith("aria-")
    assert cli.main(["mark", nxt, "applied"]) == 0
    capsys.readouterr()
    cli.main(["list"])
    out = capsys.readouterr().out
    assert nxt not in out                              # applied ⇒ gone from list


def test_cli_next_on_empty_queue_exits_nonzero(monkeypatch, tmp_path):
    cli = _patch_cli(monkeypatch, tmp_path)
    assert cli.main(["next"]) == 1                     # sequencer's stop signal


def test_cli_quarantine_subcommands(monkeypatch, tmp_path, capsys):
    cli = _patch_cli(monkeypatch, tmp_path)
    assert cli.main(["quarantine", "add", "aria-bad", "boom"]) == 0
    capsys.readouterr()
    assert cli.main(["quarantine", "list"]) == 0
    assert "aria-bad" in capsys.readouterr().out
    assert cli.main(["quarantine", "clear", "aria-bad"]) == 0
