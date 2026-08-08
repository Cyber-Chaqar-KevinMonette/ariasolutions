"""Tests for v0.2.16.0 — people, recall, task, insights, qa, steward, home, interrupts.

The previous v0.2.14 tests use a minimal in-memory atoms.db without
sqlite-vec. We use the same pattern: tests run against a stripped
atoms schema, channel-specific schemas are applied by the channel's
__init__, and tests assert behavior, not implementation.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest


# ─── Shared fixture: minimal atoms.db ───────────────────────────────────────


@pytest.fixture
def conn(tmp_path):
    """Stripped atoms.db: real schema minus virtual tables (no sqlite-vec)."""
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
# People channel
# ════════════════════════════════════════════════════════════════════════════


class TestPeopleChannel:
    def test_upsert_is_idempotent(self, conn):
        from sovereign_agent.mem_channels.people import PeopleChannel
        pc = PeopleChannel(conn)
        p1 = pc.upsert_person(canonical_name="Feynman", idempotency_id="x1")
        p2 = pc.upsert_person(canonical_name="Feynman", idempotency_id="x1")
        assert p1.person_id == p2.person_id

    def test_principal_uniqueness_refused(self, conn):
        from sovereign_agent.mem_channels.people import (
            PeopleChannel, PrincipalConflictError,
        )
        pc = PeopleChannel(conn)
        pc.upsert_person(canonical_name="Kevin", is_principal=True, idempotency_id="k1")
        with pytest.raises(PrincipalConflictError):
            pc.upsert_person(canonical_name="Alice", is_principal=True, idempotency_id="a1")

    def test_resolve_alias_case_insensitive(self, conn):
        from sovereign_agent.mem_channels.people import PeopleChannel
        pc = PeopleChannel(conn)
        p = pc.upsert_person(canonical_name="Richard Feynman", idempotency_id="rf")
        pc.add_alias(person_id=p.person_id, alias="R. Feynman", source="operator",
                     idempotency_id="al1")
        assert pc.resolve("r. feynman").person_id == p.person_id
        assert pc.resolve("RICHARD FEYNMAN").person_id == p.person_id

    def test_fact_source_defaults_pending_for_llm(self, conn):
        from sovereign_agent.mem_channels.people import PeopleChannel
        pc = PeopleChannel(conn)
        p = pc.upsert_person(canonical_name="X", idempotency_id="x1")
        f = pc.record_fact(person_id=p.person_id, kind="role", value="physicist",
                           source="llm", idempotency_id="f1")
        assert f.status == "pending"
        assert f.confidence <= 0.5

    def test_fact_source_defaults_confirmed_for_operator(self, conn):
        from sovereign_agent.mem_channels.people import PeopleChannel
        pc = PeopleChannel(conn)
        p = pc.upsert_person(canonical_name="X", idempotency_id="x1")
        f = pc.record_fact(person_id=p.person_id, kind="role", value="physicist",
                           source="operator", idempotency_id="f1")
        assert f.status == "confirmed"
        assert f.confidence >= 0.9

    def test_audit_clean_after_simple_use(self, conn):
        from sovereign_agent.mem_channels.people import PeopleChannel
        pc = PeopleChannel(conn)
        pc.upsert_person(canonical_name="Kevin", is_principal=True,
                          idempotency_id="k1")
        a = pc.audit()
        assert a.ok


# ════════════════════════════════════════════════════════════════════════════
# Recall channel
# ════════════════════════════════════════════════════════════════════════════


class TestRecallChannel:
    def test_record_is_idempotent(self, conn):
        from sovereign_agent.mem_channels.recall import RecallChannel
        rc = RecallChannel(conn)
        r1 = rc.record(title="t", body_md="b", idempotency_id="r1")
        r2 = rc.record(title="t", body_md="b", idempotency_id="r1")
        assert r1.recall_id == r2.recall_id

    def test_record_writes_markdown_file(self, conn, tmp_path, monkeypatch):
        from sovereign_agent.config import SETTINGS, Paths
        new_paths = Paths(config_dir=tmp_path / "c", data_dir=tmp_path / "d")
        new_paths.ensure()
        object.__setattr__(SETTINGS, "paths", new_paths)
        from sovereign_agent.mem_channels.recall import RecallChannel
        rc = RecallChannel(conn)
        r = rc.record(title="Hello", body_md="# greeting", idempotency_id="r2")
        assert r.file_path is not None
        assert Path(r.file_path).is_file()
        content = Path(r.file_path).read_text()
        assert "recall_id:" in content
        assert "greeting" in content

    def test_search_finds_recall_by_body(self, conn):
        from sovereign_agent.mem_channels.recall import RecallChannel
        rc = RecallChannel(conn)
        rc.record(title="alpha", body_md="kingfisher kingdoms", idempotency_id="r3")
        rc.record(title="beta", body_md="nothing about birds", idempotency_id="r4")
        out = rc.search("kingfisher")
        assert len(out) == 1
        assert out[0].title == "alpha"

    def test_revise_creates_chain(self, conn):
        from sovereign_agent.mem_channels.recall import RecallChannel
        rc = RecallChannel(conn)
        r1 = rc.record(title="t", body_md="v1", idempotency_id="r5")
        r2 = rc.revise(r1.recall_id, new_body_md="v2", idempotency_id="r6")
        assert r1.recall_id != r2.recall_id
        chain = rc.chain(r2.recall_id)
        assert len(chain) == 2
        assert chain[0].recall_id == r1.recall_id
        assert chain[1].recall_id == r2.recall_id

    def test_revise_marks_old_obsolete(self, conn):
        from sovereign_agent.mem_channels.recall import RecallChannel
        rc = RecallChannel(conn)
        r1 = rc.record(title="t", body_md="v1", idempotency_id="r7")
        rc.revise(r1.recall_id, new_body_md="v2", idempotency_id="r8")
        old = rc.get(r1.recall_id, include_redacted=True)
        assert old.status == "obsolete"

    def test_redact_tombstones_and_hides(self, conn):
        from sovereign_agent.mem_channels.recall import (
            RecallChannel, RecallNotFoundError,
        )
        rc = RecallChannel(conn)
        r = rc.record(title="t", body_md="b", idempotency_id="r9")
        rc.redact(r.recall_id, idempotency_id="rd1", reason="test")
        with pytest.raises(RecallNotFoundError):
            rc.get(r.recall_id)
        # but still readable in audit mode
        assert rc.get(r.recall_id, include_redacted=True).status == "redacted"

    def test_detect_stale_changes_state(self, conn):
        from sovereign_agent.mem_channels.recall import RecallChannel
        rc = RecallChannel(conn)
        r = rc.record(
            title="t", body_md="b", idempotency_id="r10",
            sources=[{"kind": "atom", "id": "at-1", "chain_head": "at-1"}],
        )
        marked = rc.detect_stale(lambda atom_id: "at-different")
        assert r.recall_id in marked
        assert rc.get(r.recall_id).status == "stale"

    def test_mark_verified_returns_to_fresh(self, conn):
        from sovereign_agent.mem_channels.recall import RecallChannel
        rc = RecallChannel(conn)
        r = rc.record(
            title="t", body_md="b", idempotency_id="r11",
            sources=[{"kind": "atom", "id": "at-1", "chain_head": "at-1"}],
        )
        rc.detect_stale(lambda a: "at-other")
        assert rc.get(r.recall_id).status == "stale"
        rc.mark_verified(r.recall_id)
        assert rc.get(r.recall_id).status == "fresh"

    def test_audit_clean(self, conn):
        from sovereign_agent.mem_channels.recall import RecallChannel
        rc = RecallChannel(conn)
        rc.record(title="t", body_md="b", idempotency_id="r12")
        a = rc.audit()
        assert a.ok


# ════════════════════════════════════════════════════════════════════════════
# Task channel
# ════════════════════════════════════════════════════════════════════════════


class TestTaskChannel:
    def test_begin_is_idempotent(self, conn):
        from sovereign_agent.mem_channels.task import TaskChannel
        tc = TaskChannel(conn)
        t1 = tc.begin(title="X", idempotency_id="t1")
        t2 = tc.begin(title="X", idempotency_id="t1")
        assert t1.task_id == t2.task_id

    def test_finish_records_emotion(self, conn):
        from sovereign_agent.mem_channels.task import TaskChannel
        tc = TaskChannel(conn)
        t = tc.begin(title="X", idempotency_id="t2")
        tr = tc.finish(t.task_id, status="success",
                       agent_emotion="focused",
                       agent_emotion_note="went well",
                       idempotency_id="f1")
        assert tr.status == "success"
        assert tr.agent_emotion == "focused"
        assert tr.agent_emotion_note == "went well"

    def test_finish_rejects_unknown_emotion(self, conn):
        from sovereign_agent.mem_channels.task import TaskChannel
        tc = TaskChannel(conn)
        t = tc.begin(title="X", idempotency_id="t3")
        with pytest.raises(ValueError):
            tc.finish(t.task_id, status="success", agent_emotion="exuberant",
                      idempotency_id="f2")

    def test_finish_rejects_invalid_status(self, conn):
        from sovereign_agent.mem_channels.task import TaskChannel, TaskStateError
        tc = TaskChannel(conn)
        t = tc.begin(title="X", idempotency_id="t4")
        with pytest.raises(TaskStateError):
            tc.finish(t.task_id, status="kinda-done", idempotency_id="f3")

    def test_cannot_finish_twice(self, conn):
        from sovereign_agent.mem_channels.task import TaskChannel, TaskStateError
        tc = TaskChannel(conn)
        t = tc.begin(title="X", idempotency_id="t5")
        tc.finish(t.task_id, status="success", idempotency_id="f4")
        with pytest.raises(TaskStateError):
            tc.finish(t.task_id, status="failed", idempotency_id="f5")

    def test_annotate_appends_notes(self, conn):
        from sovereign_agent.mem_channels.task import TaskChannel
        tc = TaskChannel(conn)
        t = tc.begin(title="X", idempotency_id="t6")
        tc.annotate(t.task_id, append_notes="step one done")
        tc.annotate(t.task_id, append_notes="step two done",
                    add_follow_ups=["check edge case"])
        out = tc.get(t.task_id)
        assert "step one done" in out.detailed_notes
        assert "step two done" in out.detailed_notes
        assert "check edge case" in out.follow_ups

    def test_search_finds_by_lessons(self, conn):
        from sovereign_agent.mem_channels.task import TaskChannel
        tc = TaskChannel(conn)
        t = tc.begin(title="alpha", idempotency_id="t7")
        tc.finish(t.task_id, status="success",
                  lessons="always validate the migration first",
                  idempotency_id="f6")
        out = tc.search("migration")
        assert len(out) == 1
        assert out[0].task_id == t.task_id

    def test_stats(self, conn):
        from sovereign_agent.mem_channels.task import TaskChannel
        tc = TaskChannel(conn)
        a = tc.begin(title="a", idempotency_id="ta")
        tc.finish(a.task_id, status="success", agent_emotion="focused",
                  idempotency_id="fa")
        b = tc.begin(title="b", idempotency_id="tb")
        tc.finish(b.task_id, status="failed", agent_emotion="frustrated",
                  idempotency_id="fb")
        s = tc.stats()
        assert s.total == 2
        assert s.by_status.get("success") == 1
        assert s.by_status.get("failed") == 1
        assert s.success_rate == 0.5
        assert "focused" in s.by_emotion
        assert "frustrated" in s.by_emotion

    def test_audit_clean(self, conn):
        from sovereign_agent.mem_channels.task import TaskChannel
        tc = TaskChannel(conn)
        t = tc.begin(title="X", idempotency_id="t8")
        tc.finish(t.task_id, status="success", idempotency_id="f7")
        a = tc.audit()
        assert a.ok
        assert a.total == 1


# ════════════════════════════════════════════════════════════════════════════
# Insights
# ════════════════════════════════════════════════════════════════════════════


class TestInsights:
    def test_person_insight_on_empty_returns_gap(self, conn):
        from sovereign_agent.mem_channels.people import PeopleChannel
        from sovereign_agent.insights import generate_person_insights
        pc = PeopleChannel(conn)
        pc.upsert_person(canonical_name="Lonely", idempotency_id="l1")
        report = generate_person_insights(conn, "Lonely")
        assert report.candidates
        # At least one candidate flags the gap
        assert any(c.kind == "gap" for c in report.candidates) \
            or any("thin" in c.text.lower() or "no facts" in c.text.lower()
                   for c in report.candidates)

    def test_stub_synthesizer_is_deterministic(self, conn):
        from sovereign_agent.mem_channels.people import PeopleChannel
        from sovereign_agent.insights.generator import StubSynthesizer
        pc = PeopleChannel(conn)
        p = pc.upsert_person(canonical_name="Test", idempotency_id="t1")
        pc.record_fact(person_id=p.person_id, kind="role", value="scientist",
                       source="operator", idempotency_id="f1")
        profile = pc.profile("Test")
        s1 = StubSynthesizer()
        s2 = StubSynthesizer()
        cands1 = s1.for_person(profile)
        cands2 = s2.for_person(profile)
        assert [c.text for c in cands1] == [c.text for c in cands2]


# ════════════════════════════════════════════════════════════════════════════
# QA scoring
# ════════════════════════════════════════════════════════════════════════════


class TestQAScoring:
    def test_test_report_score_perfect(self):
        from sovereign_agent.qa import score_test_report
        class FakeReport:
            pass
        r = FakeReport()
        r.total, r.passed, r.failed, r.errored, r.skipped = 50, 50, 0, 0, 0
        r.pass_rate = 1.0
        s = score_test_report(r)
        assert s.value >= 95
        assert s.grade in ("A", "A+")

    def test_test_report_score_with_failures(self):
        from sovereign_agent.qa import score_test_report
        class FakeReport:
            pass
        r = FakeReport()
        r.total, r.passed, r.failed, r.errored, r.skipped = 50, 45, 5, 0, 0
        r.pass_rate = 0.9
        s = score_test_report(r)
        assert s.value < 95
        assert "failing test" in " ".join(s.notes).lower()

    def test_hardening_score_with_critical_fail(self):
        from sovereign_agent.qa import score_hardening_report
        from sovereign_agent.qa.hardening import HardeningCheck

        class FakeReport:
            def __init__(self):
                self.checks = [
                    HardeningCheck(key="crit", label="critical_fail",
                                    passed=False, weight=9, detail=""),
                    HardeningCheck(key="pass", label="passing",
                                    passed=True, weight=5, detail=""),
                    HardeningCheck(key="other", label="other",
                                    passed=True, weight=8, detail=""),
                ]
                total = sum(c.weight for c in self.checks)
                self.weighted_score = sum(c.weight for c in self.checks if c.passed) / total
                self.ok = False
        r = FakeReport()
        s = score_hardening_report(r)
        assert s.value < 80   # critical failure should cap
        assert any("critical" in n for n in s.notes)


# ════════════════════════════════════════════════════════════════════════════
# Steward
# ════════════════════════════════════════════════════════════════════════════


class TestSteward:
    def test_audit_runs_clean_on_empty(self, conn):
        from sovereign_agent.steward import audit_all
        report = audit_all(conn)
        assert report.health_score >= 90

    def test_conflict_detection(self, conn):
        from sovereign_agent.mem_channels.people import PeopleChannel
        from sovereign_agent.steward import find_conflicts
        pc = PeopleChannel(conn)
        p = pc.upsert_person(canonical_name="Subj", idempotency_id="s1")
        pc.record_fact(person_id=p.person_id, kind="role", value="physicist",
                       source="operator", idempotency_id="f1")
        pc.record_fact(person_id=p.person_id, kind="role", value="theoretician",
                       source="operator", idempotency_id="f2")
        conflicts = find_conflicts(conn)
        assert len(conflicts) == 1
        assert conflicts[0]["subject"] == "Subj"
        assert "physicist" in conflicts[0]["values"]
        assert "theoretician" in conflicts[0]["values"]

    def test_stale_recall_detection(self, conn):
        from sovereign_agent.mem_channels.recall import RecallChannel
        from sovereign_agent.steward import find_stale_recalls
        rc = RecallChannel(conn)
        r = rc.record(
            title="t", body_md="b", idempotency_id="r1",
            sources=[{"kind": "atom", "id": "at-X", "chain_head": "at-X"}],
        )
        rc.detect_stale(lambda atom_id: "at-Y")
        out = find_stale_recalls(conn)
        assert r.recall_id in out

    def test_health_score_drops_with_conflict(self, conn):
        from sovereign_agent.mem_channels.people import PeopleChannel
        from sovereign_agent.steward import audit_all
        pc = PeopleChannel(conn)
        p = pc.upsert_person(canonical_name="C", idempotency_id="c1")
        pc.record_fact(person_id=p.person_id, kind="role", value="A",
                       source="operator", idempotency_id="a1")
        pc.record_fact(person_id=p.person_id, kind="role", value="B",
                       source="operator", idempotency_id="b1")
        report = audit_all(conn)
        assert not report.ok
        assert report.conflicts


# ════════════════════════════════════════════════════════════════════════════
# Home
# ════════════════════════════════════════════════════════════════════════════


class TestHome:
    def test_map_lists_rooms(self):
        from sovereign_agent.home import map_home
        m = map_home()
        names = {r.name for r in m.rooms}
        assert "atrium" in names
        assert "library" in names
        assert "studio" in names
        assert "garden" in names
        assert "hearth" in names

    def test_find_room_known(self):
        from sovereign_agent.home import find_room
        r = find_room("studio")
        assert r is not None
        assert "recall" in r.description.lower()

    def test_find_room_unknown(self):
        from sovereign_agent.home import find_room
        assert find_room("dungeon") is None

    def test_to_dict_serialisable(self):
        import json
        from sovereign_agent.home import map_home
        out = map_home().to_dict()
        json.dumps(out, default=str)


# ════════════════════════════════════════════════════════════════════════════
# Interrupts / conversation-mode toggle
# ════════════════════════════════════════════════════════════════════════════


class TestInterrupts:
    def test_initial_state_is_working(self):
        from sovereign_agent.interrupts import status
        s = status()
        assert s.is_working
        assert not s.requested
        assert not s.is_paused

    def test_full_lifecycle(self):
        from sovereign_agent import interrupts
        # operator requests
        s = interrupts.request_conversation(note="hello")
        assert s.requested
        assert s.note == "hello"
        # loop checks
        assert interrupts.check_conversation_request() is True
        # loop acknowledges with a continuation id
        interrupts.acknowledge_pause(continuation_id="ck-abc")
        assert interrupts.status().is_paused
        # operator says resume
        interrupts.request_resume()
        # loop consumes resume
        should, cid = interrupts.consume_resume()
        assert should is True
        assert cid == "ck-abc"
        # back to working
        assert interrupts.status().is_working

    def test_check_returns_false_when_resume_pending(self):
        from sovereign_agent import interrupts
        interrupts.request_conversation()
        interrupts.acknowledge_pause()
        interrupts.request_resume()
        # Once resume is requested, the agent should NOT see this as a
        # conversation-mode request anymore — it should consume_resume.
        assert interrupts.check_conversation_request() is False
        interrupts.consume_resume()

    def test_clear_request_idempotent(self):
        from sovereign_agent import interrupts
        interrupts.clear_conversation_request()
        interrupts.clear_conversation_request()
        assert interrupts.status().is_working
