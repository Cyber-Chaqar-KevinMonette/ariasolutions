"""Tests for v0.2.18.0 — reasoning, gaps, relationships, commitments,
heartbeat channels + migrations, archive, shards, provenance, constitution.
"""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import pytest


@pytest.fixture
def conn(tmp_path):
    db_path = tmp_path / "atoms.db"
    c = sqlite3.connect(str(db_path), isolation_level=None)
    c.executescript("""
        PRAGMA journal_mode = WAL;
        PRAGMA foreign_keys = ON;
        CREATE TABLE atoms (
            atom_id TEXT PRIMARY KEY,
            type TEXT NOT NULL,
            scope_path TEXT, scope_tags TEXT,
            summary TEXT NOT NULL,
            content_ref TEXT NOT NULL,
            claims TEXT NOT NULL, parents TEXT NOT NULL,
            version INTEGER NOT NULL DEFAULT 1,
            parent_atom_id TEXT REFERENCES atoms(atom_id),
            policy TEXT NOT NULL DEFAULT 'local_only',
            confidence REAL NOT NULL CHECK (confidence BETWEEN 0 AND 1),
            created_at TEXT NOT NULL, created_by TEXT NOT NULL,
            superseded_at TEXT, superseded_by TEXT REFERENCES atoms(atom_id)
        ) STRICT;
    """)
    yield c
    c.close()


# ════════════════════════════════════════════════════════════════════════════
# Migration framework
# ════════════════════════════════════════════════════════════════════════════


class TestMigrations:
    def test_register_and_apply(self, conn):
        from sovereign_agent.migrations import (
            register, Migration, apply_pending, reset_registry
        )
        reset_registry()
        register(Migration(name="t1", version="0.2.18",
                            body="CREATE TABLE m1 (x INTEGER)"))
        applied = apply_pending(conn)
        assert applied == ["t1"]
        # Idempotent
        again = apply_pending(conn)
        assert again == []

    def test_register_is_idempotent(self):
        from sovereign_agent.migrations import (
            register, Migration, reset_registry, get_registered
        )
        reset_registry()
        m = Migration(name="dup", version="0.2.18", body="SELECT 1")
        register(m); register(m); register(m)
        assert len(get_registered()) == 1

    def test_callable_body(self, conn):
        from sovereign_agent.migrations import (
            register, Migration, apply_pending, reset_registry
        )
        reset_registry()
        called = []
        def doit(c):
            called.append(True)
            c.execute("CREATE TABLE cb_test (n INTEGER)")
        register(Migration(name="cb", version="0.2.18", body=doit))
        apply_pending(conn)
        assert called == [True]
        # Check it actually ran
        assert conn.execute(
            "SELECT name FROM sqlite_master WHERE name='cb_test'"
        ).fetchone() is not None

    def test_dry_run(self, conn):
        from sovereign_agent.migrations import (
            register, Migration, apply_pending, status, reset_registry
        )
        reset_registry()
        register(Migration(name="dr", version="0.2.18",
                            body="CREATE TABLE dr_test (n INTEGER)"))
        would = apply_pending(conn, dry_run=True)
        assert would == ["dr"]
        # Not actually applied
        assert all(s["status"] == "pending" for s in status(conn)
                   if s["name"] == "dr")
        # Now apply for real
        apply_pending(conn)
        assert all(s["status"] == "applied" for s in status(conn)
                   if s["name"] == "dr")


# ════════════════════════════════════════════════════════════════════════════
# Content-addressed archive
# ════════════════════════════════════════════════════════════════════════════


class TestArchive:
    def test_put_and_get(self, conn):
        from sovereign_agent.archive import ContentArchive
        arc = ContentArchive(conn)
        h = arc.put("hello world")
        assert isinstance(h, str)
        assert len(h) == 64  # sha256 hex
        assert arc.get_str(h) == "hello world"

    def test_dedup(self, conn):
        from sovereign_agent.archive import ContentArchive
        arc = ContentArchive(conn)
        h1 = arc.put("same content")
        h2 = arc.put("same content")
        assert h1 == h2
        assert arc.stats().total_objects == 1

    def test_distinct_content_distinct_hash(self, conn):
        from sovereign_agent.archive import ContentArchive
        arc = ContentArchive(conn)
        h1 = arc.put("content A")
        h2 = arc.put("content B")
        assert h1 != h2

    def test_verify(self, conn):
        from sovereign_agent.archive import ContentArchive
        arc = ContentArchive(conn)
        h = arc.put("auditable")
        assert arc.verify(h) is True
        # Tamper directly via SQL — should fail verification
        conn.execute("UPDATE archive SET content = ? WHERE content_hash = ?",
                     (b"different bytes", h))
        conn.commit()
        assert arc.verify(h) is False

    def test_seal_blocks_gc(self, conn):
        from sovereign_agent.archive import ContentArchive
        arc = ContentArchive(conn)
        h = arc.put("forever")
        arc.seal(h)
        # Refcount is 0 — would be GC'd if not sealed
        removed = arc.gc()
        assert h not in removed
        assert arc.get_str(h) == "forever"

    def test_gc_removes_unsealed_unreferenced(self, conn):
        from sovereign_agent.archive import ContentArchive
        arc = ContentArchive(conn)
        h = arc.put("transient")
        # No ref, not sealed → GC eligible
        removed = arc.gc()
        assert h in removed
        assert arc.get_str(h) is None

    def test_refcount(self, conn):
        from sovereign_agent.archive import ContentArchive
        arc = ContentArchive(conn)
        h = arc.put("referenced", ref_kind="atom", ref_id="at-1")
        info = arc.info(h)
        assert info.refcount == 1
        # Re-put with same ref doesn't double-count (idempotent)
        arc.put("referenced", ref_kind="atom", ref_id="at-1")
        assert arc.info(h).refcount == 1
        # Different ref bumps refcount
        arc.put("referenced", ref_kind="atom", ref_id="at-2")
        assert arc.info(h).refcount == 2

    def test_signature(self, conn):
        from sovereign_agent.archive import ContentArchive
        arc = ContentArchive(conn)
        h = arc.put("signed content")
        arc.attach_signature(h, "fake-gpg-signature-here")
        assert arc.info(h).signature == "fake-gpg-signature-here"


# ════════════════════════════════════════════════════════════════════════════
# Constitution layer
# ════════════════════════════════════════════════════════════════════════════


class TestConstitution:
    def test_list_seven(self):
        from sovereign_agent.constitution import list_all
        items = list_all()
        assert len(items) == 7
        ids = {c.id for c in items}
        assert {"presence", "honest_voice", "calibrated_uncertainty",
                "bounded_authority", "no_delegation", "halt_when_called",
                "protect_the_operator"} <= ids

    def test_all_pass_clean(self):
        from sovereign_agent.constitution import check_action
        report = check_action({"tier": 0, "confidence": 0.5})
        assert report.passed

    def test_tier3_without_idem_fails(self):
        from sovereign_agent.constitution import check_action
        report = check_action({"tier": 3, "confidence": 0.5})
        assert not report.passed
        critical = report.critical_failures
        assert any(v.commitment_id == "bounded_authority" for v in critical)

    def test_high_confidence_no_source_warns(self):
        from sovereign_agent.constitution import check_action
        report = check_action({"tier": 0, "confidence": 0.95})
        # Warning level, not critical → overall report fails
        assert not report.passed
        wf = [v for v in report.verdicts
              if not v.passed and v.commitment_id == "calibrated_uncertainty"]
        assert len(wf) == 1

    def test_delegated_to_is_critical(self):
        from sovereign_agent.constitution import check_action
        report = check_action({"tier": 0, "delegated_to": "other_agent"})
        assert not report.passed
        critical = report.critical_failures
        assert any(v.commitment_id == "no_delegation" for v in critical)


# ════════════════════════════════════════════════════════════════════════════
# Provenance graph traversal
# ════════════════════════════════════════════════════════════════════════════


class TestProvenance:
    def test_walk_empty(self, conn):
        from sovereign_agent.provenance import walk_backward
        g = walk_backward(conn, "at-nonexistent")
        # Node not found: just the root, no edges
        assert g.root == "at-nonexistent"
        assert len(g.edges) == 0

    def test_walk_supersedes_chain(self, conn):
        from sovereign_agent.provenance import walk_backward
        # Insert two atoms with parent_atom_id relationship
        conn.execute(
            "INSERT INTO atoms (atom_id, type, summary, content_ref, claims, "
            "parents, confidence, created_at, created_by) "
            "VALUES ('at-a', 'event', 's', 'r', '[]', '[]', 0.5, 'now', 'test')"
        )
        conn.execute(
            "INSERT INTO atoms (atom_id, type, summary, content_ref, claims, "
            "parents, confidence, created_at, created_by, parent_atom_id) "
            "VALUES ('at-b', 'event', 's', 'r', '[]', '[]', 0.5, 'now', 'test', 'at-a')"
        )
        conn.commit()
        g = walk_backward(conn, "at-b")
        assert "at-a" in g.nodes
        labels = {e.label for e in g.edges if e.target == "at-b"}
        assert "supersedes" in labels

    def test_max_depth_bounds(self, conn):
        from sovereign_agent.provenance import walk_backward
        # Build a chain at-0 ← at-1 ← at-2 ← ... ← at-9
        prev = None
        for i in range(10):
            aid = f"at-{i}"
            conn.execute(
                "INSERT INTO atoms (atom_id, type, summary, content_ref, claims, "
                "parents, confidence, created_at, created_by, parent_atom_id) "
                "VALUES (?, 'event', 's', 'r', '[]', '[]', 0.5, 'now', 'test', ?)",
                (aid, prev),
            )
            prev = aid
        conn.commit()
        g = walk_backward(conn, "at-9", max_depth=3)
        # Should visit only ~4 nodes (root + 3 levels)
        assert g.truncated is True
        assert len(g.nodes) <= 4


# ════════════════════════════════════════════════════════════════════════════
# Reasoning channel
# ════════════════════════════════════════════════════════════════════════════


class TestReasoning:
    def test_open_then_conclude(self, conn):
        from sovereign_agent.mem_channels.reasoning import ReasoningChannel
        rc = ReasoningChannel(conn)
        t = rc.open(title="Test Q", idempotency_id="r1")
        assert t.status == "open"
        rc.add_step(t.trace_id, step_kind="observation", content="X")
        rc.add_step(t.trace_id, step_kind="hypothesis", content="Y", confidence=0.7)
        rc.add_step(t.trace_id, step_kind="evidence", content="Z")
        result = rc.conclude(t.trace_id, conclusion="A", confidence=0.8)
        assert result.status == "concluded"
        assert result.confidence == 0.8
        assert len(result.steps) == 3

    def test_open_idempotent(self, conn):
        from sovereign_agent.mem_channels.reasoning import ReasoningChannel
        rc = ReasoningChannel(conn)
        t1 = rc.open(title="T", idempotency_id="r2")
        t2 = rc.open(title="T", idempotency_id="r2")
        assert t1.trace_id == t2.trace_id

    def test_invalid_step_kind(self, conn):
        from sovereign_agent.mem_channels.reasoning import ReasoningChannel
        rc = ReasoningChannel(conn)
        t = rc.open(title="T", idempotency_id="r3")
        with pytest.raises(ValueError):
            rc.add_step(t.trace_id, step_kind="weird", content="x")

    def test_step_on_concluded_fails(self, conn):
        from sovereign_agent.mem_channels.reasoning import (
            ReasoningChannel, TraceStateError
        )
        rc = ReasoningChannel(conn)
        t = rc.open(title="T", idempotency_id="r4")
        rc.conclude(t.trace_id, conclusion="done", confidence=0.5)
        with pytest.raises(TraceStateError):
            rc.add_step(t.trace_id, step_kind="note", content="late")

    def test_audit_flags_overconfident(self, conn):
        from sovereign_agent.mem_channels.reasoning import ReasoningChannel
        rc = ReasoningChannel(conn)
        t = rc.open(title="T", idempotency_id="r5")
        # Conclude with high confidence but ZERO evidence steps
        rc.conclude(t.trace_id, conclusion="X is true", confidence=0.95)
        a = rc.audit()
        assert a.high_confidence_no_evidence == 1
        assert not a.ok

    def test_search(self, conn):
        from sovereign_agent.mem_channels.reasoning import ReasoningChannel
        rc = ReasoningChannel(conn)
        t = rc.open(title="Sharding analysis", idempotency_id="r6")
        rc.conclude(t.trace_id, conclusion="use per-channel DBs",
                    confidence=0.7)
        hits = rc.search("sharding")
        assert len(hits) >= 1


# ════════════════════════════════════════════════════════════════════════════
# Gaps channel
# ════════════════════════════════════════════════════════════════════════════


class TestGaps:
    def test_open_then_close(self, conn):
        from sovereign_agent.mem_channels.gaps import GapsChannel
        gc = GapsChannel(conn)
        g = gc.open(title="What's X?", idempotency_id="g1", priority=2)
        assert g.status == "open"
        closed = gc.close(g.gap_id, resolution="It's Y.")
        assert closed.status == "closed"
        assert closed.resolution == "It's Y."

    def test_close_requires_resolution(self, conn):
        from sovereign_agent.mem_channels.gaps import GapsChannel
        gc = GapsChannel(conn)
        g = gc.open(title="Q", idempotency_id="g2")
        with pytest.raises(ValueError):
            gc.close(g.gap_id, resolution="")

    def test_close_idempotent(self, conn):
        from sovereign_agent.mem_channels.gaps import GapsChannel
        gc = GapsChannel(conn)
        g = gc.open(title="Q", idempotency_id="g3")
        gc.close(g.gap_id, resolution="A1")
        # Closing again returns same row unchanged
        result = gc.close(g.gap_id, resolution="A2")
        assert result.resolution == "A1"

    def test_investigate_then_close(self, conn):
        from sovereign_agent.mem_channels.gaps import GapsChannel
        gc = GapsChannel(conn)
        g = gc.open(title="Q", idempotency_id="g4")
        inv = gc.investigate(g.gap_id)
        assert inv.status == "investigating"
        gc.close(g.gap_id, resolution="done")

    def test_stats_close_rate(self, conn):
        from sovereign_agent.mem_channels.gaps import GapsChannel
        gc = GapsChannel(conn)
        for i in range(4):
            g = gc.open(title=f"q{i}", idempotency_id=f"g_stat_{i}")
            if i < 3:
                gc.close(g.gap_id, resolution="x")
        s = gc.stats()
        assert s.closed == 3
        assert s.open == 1
        # close_rate is closed/(closed+shelved). open doesn't count.
        assert s.close_rate == 1.0


# ════════════════════════════════════════════════════════════════════════════
# Relationships channel
# ════════════════════════════════════════════════════════════════════════════


def _make_three_people(conn):
    """Helper: insert three people (Alice, Bob, Carol) and return their ids."""
    from sovereign_agent.mem_channels.people import PeopleChannel
    pc = PeopleChannel(conn)
    a = pc.upsert_person(canonical_name="Alice", idempotency_id="a1")
    b = pc.upsert_person(canonical_name="Bob", idempotency_id="b1")
    c = pc.upsert_person(canonical_name="Carol", idempotency_id="c1")
    return a, b, c


class TestRelationships:
    def test_connect(self, conn):
        from sovereign_agent.mem_channels.relationships import RelationshipsChannel
        a, b, c = _make_three_people(conn)
        rc = RelationshipsChannel(conn)
        r = rc.connect(from_person_id=a.person_id, to_person_id=b.person_id,
                       kind="colleague", idempotency_id="rl1")
        assert r.status == "confirmed"
        assert r.is_active

    def test_self_referential_blocked(self, conn):
        from sovereign_agent.mem_channels.relationships import RelationshipsChannel
        a, _, _ = _make_three_people(conn)
        rc = RelationshipsChannel(conn)
        with pytest.raises(ValueError):
            rc.connect(from_person_id=a.person_id, to_person_id=a.person_id,
                       kind="friend", idempotency_id="rl_self")

    def test_llm_source_pending(self, conn):
        from sovereign_agent.mem_channels.relationships import RelationshipsChannel
        a, b, _ = _make_three_people(conn)
        rc = RelationshipsChannel(conn)
        r = rc.connect(from_person_id=a.person_id, to_person_id=b.person_id,
                       kind="colleague", source="llm", idempotency_id="rl_llm")
        assert r.status == "pending"
        # confirm() promotes
        rc.confirm(r.relationship_id)
        assert rc.get(r.relationship_id).status == "confirmed"

    def test_shortest_path(self, conn):
        from sovereign_agent.mem_channels.relationships import RelationshipsChannel
        a, b, c = _make_three_people(conn)
        rc = RelationshipsChannel(conn)
        rc.connect(from_person_id=a.person_id, to_person_id=b.person_id,
                   kind="colleague", idempotency_id="path1")
        rc.connect(from_person_id=b.person_id, to_person_id=c.person_id,
                   kind="friend", idempotency_id="path2")
        path = rc.shortest_path(a.person_id, c.person_id)
        assert path == [a.person_id, b.person_id, c.person_id]

    def test_path_max_depth(self, conn):
        from sovereign_agent.mem_channels.relationships import RelationshipsChannel
        a, b, c = _make_three_people(conn)
        rc = RelationshipsChannel(conn)
        rc.connect(from_person_id=a.person_id, to_person_id=b.person_id,
                   kind="colleague", idempotency_id="md1")
        rc.connect(from_person_id=b.person_id, to_person_id=c.person_id,
                   kind="friend", idempotency_id="md2")
        path = rc.shortest_path(a.person_id, c.person_id, max_depth=1)
        assert path is None

    def test_neighbours(self, conn):
        from sovereign_agent.mem_channels.relationships import RelationshipsChannel
        a, b, c = _make_three_people(conn)
        rc = RelationshipsChannel(conn)
        rc.connect(from_person_id=a.person_id, to_person_id=b.person_id,
                   kind="colleague", idempotency_id="n1")
        rc.connect(from_person_id=a.person_id, to_person_id=c.person_id,
                   kind="friend", idempotency_id="n2")
        nbs = rc.neighbours_of(a.person_id)
        assert len(nbs) == 2

    def test_retract_removes_from_active(self, conn):
        from sovereign_agent.mem_channels.relationships import RelationshipsChannel
        a, b, _ = _make_three_people(conn)
        rc = RelationshipsChannel(conn)
        r = rc.connect(from_person_id=a.person_id, to_person_id=b.person_id,
                       kind="colleague", idempotency_id="re1")
        rc.retract(r.relationship_id, reason="left the company")
        assert not rc.get(r.relationship_id).is_active

    def test_audit(self, conn):
        from sovereign_agent.mem_channels.relationships import RelationshipsChannel
        a, b, _ = _make_three_people(conn)
        rc = RelationshipsChannel(conn)
        rc.connect(from_person_id=a.person_id, to_person_id=b.person_id,
                   kind="colleague", idempotency_id="au1")
        au = rc.audit()
        assert au.ok
        assert au.confirmed == 1
        assert au.self_referential == 0


# ════════════════════════════════════════════════════════════════════════════
# Commitments channel
# ════════════════════════════════════════════════════════════════════════════


class TestCommitments:
    def test_make_then_keep(self, conn):
        from sovereign_agent.mem_channels.commitments import CommitmentsChannel
        cc = CommitmentsChannel(conn)
        c = cc.make(title="Ship X", committed_by="aria", committed_to="kevin",
                    idempotency_id="cm1")
        assert c.status == "open"
        c2 = cc.keep(c.commitment_id, resolution="done")
        assert c2.status == "kept"

    def test_break_requires_resolution(self, conn):
        from sovereign_agent.mem_channels.commitments import CommitmentsChannel
        cc = CommitmentsChannel(conn)
        c = cc.make(title="X", committed_by="a", committed_to="b",
                    idempotency_id="cm_break")
        with pytest.raises(ValueError):
            cc.break_(c.commitment_id, resolution="")

    def test_break_honestly(self, conn):
        from sovereign_agent.mem_channels.commitments import CommitmentsChannel
        cc = CommitmentsChannel(conn)
        c = cc.make(title="X", committed_by="a", committed_to="b",
                    idempotency_id="cm_b2")
        broken = cc.break_(c.commitment_id, resolution="Underestimated effort")
        assert broken.status == "broken"
        assert "underestimated" in broken.resolution.lower()

    def test_release(self, conn):
        from sovereign_agent.mem_channels.commitments import CommitmentsChannel
        cc = CommitmentsChannel(conn)
        c = cc.make(title="X", committed_by="a", committed_to="b",
                    idempotency_id="cm_rel")
        rel = cc.release(c.commitment_id, resolution="b said never mind")
        assert rel.status == "released"

    def test_same_party_blocked(self, conn):
        from sovereign_agent.mem_channels.commitments import CommitmentsChannel
        cc = CommitmentsChannel(conn)
        with pytest.raises(ValueError):
            cc.make(title="X", committed_by="aria", committed_to="aria",
                    idempotency_id="cm_self")

    def test_keep_rate(self, conn):
        from sovereign_agent.mem_channels.commitments import CommitmentsChannel
        cc = CommitmentsChannel(conn)
        for i in range(3):
            c = cc.make(title=f"X{i}", committed_by="a", committed_to="b",
                        idempotency_id=f"kr{i}")
            cc.keep(c.commitment_id, resolution="ok")
        c = cc.make(title="X3", committed_by="a", committed_to="b",
                    idempotency_id="kr3")
        cc.break_(c.commitment_id, resolution="failed")
        s = cc.stats()
        assert s.kept == 3
        assert s.broken == 1
        assert s.keep_rate == 0.75

    def test_due_soon(self, conn):
        from sovereign_agent.mem_channels.commitments import CommitmentsChannel
        from datetime import datetime, timezone, timedelta
        cc = CommitmentsChannel(conn)
        soon = (datetime.now(timezone.utc) + timedelta(days=3)).strftime(
            "%Y-%m-%dT%H:%M:%S.%fZ"
        )
        far = (datetime.now(timezone.utc) + timedelta(days=30)).strftime(
            "%Y-%m-%dT%H:%M:%S.%fZ"
        )
        cc.make(title="Soon", committed_by="a", committed_to="b",
                due_at=soon, idempotency_id="ds1")
        cc.make(title="Far", committed_by="a", committed_to="b",
                due_at=far, idempotency_id="ds2")
        items = cc.due_soon(within_days=7)
        assert len(items) == 1
        assert items[0].title == "Soon"


# ════════════════════════════════════════════════════════════════════════════
# Heartbeat channel
# ════════════════════════════════════════════════════════════════════════════


class TestHeartbeat:
    def test_pulse(self, conn):
        from sovereign_agent.mem_channels.heartbeat import HeartbeatChannel
        hc = HeartbeatChannel(conn)
        b = hc.pulse(message="I'm here, working on Aria.",
                     idempotency_id="hb1",
                     agent_emotion="absorbed",
                     agent_emotion_note="this is meaningful")
        assert b.message.startswith("I'm here")
        assert b.agent_emotion == "absorbed"

    def test_recent_in_order(self, conn):
        from sovereign_agent.mem_channels.heartbeat import HeartbeatChannel
        hc = HeartbeatChannel(conn)
        for i in range(3):
            hc.pulse(message=f"pulse {i}", idempotency_id=f"hb_{i}")
            time.sleep(0.001)
        beats = hc.recent(limit=3)
        assert len(beats) == 3
        # Most recent first
        assert beats[0].message == "pulse 2"
        assert beats[2].message == "pulse 0"

    def test_long_message_blocked(self, conn):
        from sovereign_agent.mem_channels.heartbeat import HeartbeatChannel
        hc = HeartbeatChannel(conn)
        with pytest.raises(ValueError):
            hc.pulse(message="x" * 501, idempotency_id="hb_long")

    def test_pulse_age(self, conn):
        from sovereign_agent.mem_channels.heartbeat import HeartbeatChannel
        hc = HeartbeatChannel(conn)
        assert hc.last_pulse_age_seconds() is None
        hc.pulse(message="m", idempotency_id="hb_age")
        age = hc.last_pulse_age_seconds()
        assert age is not None and age < 5.0


# ════════════════════════════════════════════════════════════════════════════
# Shards configuration (light test — doesn't actually create shard DBs)
# ════════════════════════════════════════════════════════════════════════════


class TestShards:
    def test_add_load_remove(self, tmp_path):
        from sovereign_agent.config import SETTINGS, Paths
        new_paths = Paths(config_dir=tmp_path / "c", data_dir=tmp_path / "d")
        new_paths.ensure()
        object.__setattr__(SETTINGS, "paths", new_paths)
        from sovereign_agent.shards import add_shard, load_shard_config, remove_shard
        cfg = add_shard("task")
        assert "task" in cfg.shards
        loaded = load_shard_config()
        assert loaded.shard_for("task") == "shards/task.db"
        after = remove_shard("task")
        assert "task" not in after.shards

    def test_resolve_channel_conn_falls_through_when_no_shard(self, conn, tmp_path):
        from sovereign_agent.config import SETTINGS, Paths
        new_paths = Paths(config_dir=tmp_path / "c", data_dir=tmp_path / "d")
        new_paths.ensure()
        object.__setattr__(SETTINGS, "paths", new_paths)
        from sovereign_agent.shards import resolve_channel_conn
        result = resolve_channel_conn("some_unknown_channel", conn)
        assert result is conn
