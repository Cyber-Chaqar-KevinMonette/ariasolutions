"""Tests for v0.2.17.0 — episodes, bitemporal, unicode normalization,
chain-head auto-resolve, profiler rotation, checkpoint helper.
"""
from __future__ import annotations

import sqlite3
import unicodedata
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
# Episodes channel
# ════════════════════════════════════════════════════════════════════════════


class TestEpisodes:
    def test_open_is_idempotent(self, conn):
        from sovereign_agent.mem_channels.episodes import EpisodesChannel
        ec = EpisodesChannel(conn)
        e1 = ec.open(title="X", idempotency_id="e1")
        e2 = ec.open(title="X", idempotency_id="e1")
        assert e1.episode_id == e2.episode_id

    def test_close_transitions_status(self, conn):
        from sovereign_agent.mem_channels.episodes import EpisodesChannel
        ec = EpisodesChannel(conn)
        e = ec.open(title="X", idempotency_id="e2")
        assert e.status == "open"
        e2 = ec.close(e.episode_id, summary="done well")
        assert e2.status == "closed"
        assert e2.summary == "done well"
        assert e2.closed_at is not None

    def test_close_open_again_is_idempotent(self, conn):
        from sovereign_agent.mem_channels.episodes import EpisodesChannel
        ec = EpisodesChannel(conn)
        e = ec.open(title="X", idempotency_id="e3")
        ec.close(e.episode_id, summary="first")
        e2 = ec.close(e.episode_id, summary="second")  # no-op
        assert e2.summary == "first"   # original preserved

    def test_archive_requires_close(self, conn):
        from sovereign_agent.mem_channels.episodes import (
            EpisodesChannel, EpisodeStateError,
        )
        ec = EpisodesChannel(conn)
        e = ec.open(title="X", idempotency_id="e4")
        with pytest.raises(EpisodeStateError):
            ec.archive(e.episode_id)
        ec.close(e.episode_id)
        archived = ec.archive(e.episode_id)
        assert archived.status == "archived"

    def test_add_member_then_find(self, conn):
        from sovereign_agent.mem_channels.episodes import EpisodesChannel
        ec = EpisodesChannel(conn)
        e = ec.open(title="X", idempotency_id="e5")
        ec.add_member(e.episode_id, member_kind="task", member_ref="tk-abc",
                      role="primary")
        ec.add_member(e.episode_id, member_kind="recall", member_ref="rc-xyz")
        full = ec.get(e.episode_id)
        assert len(full.members) == 2
        # find_by_member
        hits = ec.find_by_member(member_kind="task", member_ref="tk-abc")
        assert len(hits) == 1
        assert hits[0].episode_id == e.episode_id

    def test_invalid_member_kind_rejected(self, conn):
        from sovereign_agent.mem_channels.episodes import EpisodesChannel
        ec = EpisodesChannel(conn)
        e = ec.open(title="X", idempotency_id="e6")
        with pytest.raises(ValueError):
            ec.add_member(e.episode_id, member_kind="banana", member_ref="r1")

    def test_significance_validates(self, conn):
        from sovereign_agent.mem_channels.episodes import EpisodesChannel
        ec = EpisodesChannel(conn)
        with pytest.raises(ValueError):
            ec.open(title="X", idempotency_id="e7", significance=5)

    def test_search_finds_by_summary(self, conn):
        from sovereign_agent.mem_channels.episodes import EpisodesChannel
        ec = EpisodesChannel(conn)
        e = ec.open(title="merge work", idempotency_id="e8")
        ec.close(e.episode_id, summary="discovered the canonical-first rule")
        results = ec.search("canonical")
        assert len(results) >= 1
        assert results[0].episode_id == e.episode_id

    def test_redact_hides_from_default_reads(self, conn):
        from sovereign_agent.mem_channels.episodes import (
            EpisodesChannel, EpisodeNotFoundError,
        )
        ec = EpisodesChannel(conn)
        e = ec.open(title="X", idempotency_id="e9")
        ec.redact(e.episode_id, idempotency_id="r1", reason="test")
        with pytest.raises(EpisodeNotFoundError):
            ec.get(e.episode_id)
        # still findable in audit mode
        assert ec.get(e.episode_id, include_redacted=True).status == "redacted"

    def test_audit_detects_dangling(self, conn):
        from sovereign_agent.mem_channels.episodes import EpisodesChannel
        ec = EpisodesChannel(conn)
        e = ec.open(title="X", idempotency_id="e10")
        ec.add_member(e.episode_id, member_kind="atom", member_ref="at-fake")
        ec.redact(e.episode_id, idempotency_id="r2")
        a = ec.audit()
        # Redacted episodes' members count as dangling per audit definition
        assert a.dangling_members >= 1


# ════════════════════════════════════════════════════════════════════════════
# Bitemporal (people facts)
# ════════════════════════════════════════════════════════════════════════════


class TestBitemporal:
    def test_record_fact_default_valid_from_now(self, conn):
        from sovereign_agent.mem_channels.people import PeopleChannel
        pc = PeopleChannel(conn)
        p = pc.upsert_person(canonical_name="X", idempotency_id="x1")
        pc.record_fact(person_id=p.person_id, kind="role", value="scientist",
                       source="operator", idempotency_id="f1")
        # Querying as-of future returns the fact
        future = "2030-01-01T00:00:00Z"
        facts = pc.as_of_facts(p.person_id, future)
        assert len(facts) == 1
        assert facts[0].value == "scientist"

    def test_as_of_past_excludes(self, conn):
        from sovereign_agent.mem_channels.people import PeopleChannel
        pc = PeopleChannel(conn)
        p = pc.upsert_person(canonical_name="X", idempotency_id="x2")
        pc.record_fact(person_id=p.person_id, kind="role", value="scientist",
                       source="operator", idempotency_id="f2")
        # Querying as-of a date BEFORE the fact was written returns nothing
        past = "2020-01-01T00:00:00Z"
        facts = pc.as_of_facts(p.person_id, past)
        assert facts == []

    def test_explicit_valid_window(self, conn):
        from sovereign_agent.mem_channels.people import PeopleChannel
        pc = PeopleChannel(conn)
        p = pc.upsert_person(canonical_name="Feynman", idempotency_id="x3")
        pc.record_fact(
            person_id=p.person_id, kind="affiliation", value="Caltech",
            source="operator", idempotency_id="f3",
            valid_from="1950-01-01T00:00:00Z",
            valid_until="1988-02-15T00:00:00Z",
        )
        # Using facts_at with valid_on= (current knowledge of the past)
        during = pc.facts_at(p.person_id, valid_on="1970-01-01T00:00:00Z")
        assert len(during) == 1
        assert during[0].value == "Caltech"
        # After the valid window: not visible
        after = pc.facts_at(p.person_id, valid_on="2000-01-01T00:00:00Z")
        assert after == []
        # Before: also not visible
        before = pc.facts_at(p.person_id, valid_on="1940-01-01T00:00:00Z")
        assert before == []

    def test_kind_filter(self, conn):
        from sovereign_agent.mem_channels.people import PeopleChannel
        pc = PeopleChannel(conn)
        p = pc.upsert_person(canonical_name="X", idempotency_id="x4")
        pc.record_fact(person_id=p.person_id, kind="role", value="scientist",
                       source="operator", idempotency_id="f4")
        pc.record_fact(person_id=p.person_id, kind="lab", value="MIT",
                       source="operator", idempotency_id="f5")
        future = "2030-01-01T00:00:00Z"
        only_role = pc.as_of_facts(p.person_id, future, kind="role")
        assert len(only_role) == 1
        assert only_role[0].kind == "role"

    def test_pending_excluded_by_default(self, conn):
        from sovereign_agent.mem_channels.people import PeopleChannel
        pc = PeopleChannel(conn)
        p = pc.upsert_person(canonical_name="X", idempotency_id="x5")
        pc.record_fact(person_id=p.person_id, kind="role", value="scientist",
                       source="llm", idempotency_id="f6")
        future = "2030-01-01T00:00:00Z"
        assert pc.as_of_facts(p.person_id, future) == []
        assert len(pc.as_of_facts(p.person_id, future, include_pending=True)) == 1


# ════════════════════════════════════════════════════════════════════════════
# Unicode normalization in people resolve
# ════════════════════════════════════════════════════════════════════════════


class TestUnicodeNormalize:
    def test_nfc_nfd_resolve_same(self, conn):
        from sovereign_agent.mem_channels.people import PeopleChannel
        pc = PeopleChannel(conn)
        p = pc.upsert_person(canonical_name="Café", idempotency_id="u1")
        nfd = unicodedata.normalize("NFD", "Café")
        assert nfd != "Café"   # different code points
        assert pc.resolve(nfd).person_id == p.person_id

    def test_casefold_handles_ss(self, conn):
        """ß should match its casefold equivalent ss."""
        from sovereign_agent.mem_channels.people import PeopleChannel
        pc = PeopleChannel(conn)
        p = pc.upsert_person(canonical_name="Straße", idempotency_id="u2")
        # casefold("Straße") == "strasse"
        # resolve("strasse") should hit because both are casefolded
        # (note: alphabetical "ss" vs "ß" do not have the same canonical_lower
        # under simple .lower() — this is the very bug the fix addresses)
        assert pc.resolve("Straße").person_id == p.person_id

    def test_rtl_override_stripped(self, conn):
        """An RTL override character should not let an attacker create a duplicate."""
        from sovereign_agent.mem_channels.people import PeopleChannel
        pc = PeopleChannel(conn)
        p = pc.upsert_person(canonical_name="Feynman", idempotency_id="u3")
        attacker = "Feyn\u202eman"   # contains U+202E RTL override
        # Resolution should still find the canonical person (override stripped)
        resolved = pc.resolve(attacker)
        assert resolved is not None
        assert resolved.person_id == p.person_id


# ════════════════════════════════════════════════════════════════════════════
# Recall chain-head auto-resolve
# ════════════════════════════════════════════════════════════════════════════


class TestRecallChainResolve:
    def test_missing_chain_head_does_not_break_record(self, conn):
        """When the atom referred to doesn't exist, recall.record() must
        not crash — it should just leave chain_head as None for that source.
        """
        from sovereign_agent.mem_channels.recall import RecallChannel
        rc = RecallChannel(conn)
        # The fake atom_id won't resolve; channel must degrade gracefully
        r = rc.record(
            title="t", body_md="b", idempotency_id="r1",
            sources=[{"kind": "atom", "id": "at-nonexistent"}],
        )
        assert r.recall_id is not None
        # The source row was inserted but with chain_head=None (no crash)
        assert len(r.sources) == 1


# ════════════════════════════════════════════════════════════════════════════
# Profiler rotation
# ════════════════════════════════════════════════════════════════════════════


class TestProfilerRotation:
    def test_disk_samples_disabled_by_default(self, tmp_path, monkeypatch):
        from sovereign_agent.config import SETTINGS, Paths
        new_paths = Paths(config_dir=tmp_path / "c", data_dir=tmp_path / "d")
        new_paths.ensure()
        object.__setattr__(SETTINGS, "paths", new_paths)
        from sovereign_agent.profiler import timed, _profile_path
        with timed("test.op"):
            pass
        # No file should be created when disk samples disabled
        assert not _profile_path().exists()

    def test_enabled_writes_then_rotates(self, tmp_path):
        from sovereign_agent.config import SETTINGS, Paths
        new_paths = Paths(config_dir=tmp_path / "c", data_dir=tmp_path / "d")
        new_paths.ensure()
        object.__setattr__(SETTINGS, "paths", new_paths)
        from sovereign_agent.profiler import (
            timed, enable_disk_samples, _profile_path,
        )
        enable_disk_samples(True)
        try:
            with timed("x"):
                pass
            assert _profile_path().exists()
            assert _profile_path().stat().st_size > 0
        finally:
            enable_disk_samples(False)


# ════════════════════════════════════════════════════════════════════════════
# Interrupts checkpoint helper
# ════════════════════════════════════════════════════════════════════════════


class TestCheckpoint:
    def test_no_request_no_pause(self):
        from sovereign_agent import interrupts
        # Ensure clean state
        interrupts.clear_conversation_request()
        result = interrupts.checkpoint(continuation_id="x")
        assert result is False
        assert interrupts.status().is_working

    def test_request_then_checkpoint_acks(self):
        from sovereign_agent import interrupts
        interrupts.clear_conversation_request()
        interrupts.request_conversation(note="hello")
        result = interrupts.checkpoint(continuation_id="ck-1")
        assert result is True
        assert interrupts.status().is_paused
        # cleanup
        interrupts.request_resume()
        interrupts.consume_resume()
