"""Tests for aria-people-health: the consent-gated offline health channel.
Real SQLite, real channel machinery — the same fixture pattern
tests/test_v0216.py already established for PeopleChannel (a stripped
atoms schema; each channel bootstraps its own schema on __init__)."""
from __future__ import annotations

import sqlite3

import pytest


@pytest.fixture
def conn(tmp_path):
    """Stripped atoms.db — same minimal schema test_v0216.py uses."""
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
        CREATE TABLE archive (
            content_hash TEXT PRIMARY KEY,
            size_bytes INTEGER NOT NULL,
            content_type TEXT NOT NULL DEFAULT 'text/plain',
            content BLOB NOT NULL,
            created_at TEXT NOT NULL
        ) STRICT;
    """)
    yield c
    c.close()


def _make_principal(pc, name="Kevin") -> str:
    person = pc.upsert_person(canonical_name=name, is_principal=True, idempotency_id=f"mk:{name}")
    return person.person_id


def _make_other(pc, name="Alex") -> str:
    person = pc.upsert_person(canonical_name=name, idempotency_id=f"mk:{name}")
    return person.person_id


class TestPeopleHealthChannel:
    def test_recording_for_the_principal_needs_no_consent(self, conn):
        from sovereign_agent.mem_channels.people import PeopleChannel
        from sovereign_agent.mem_channels.people_health import PeopleHealthChannel

        pc = PeopleChannel(conn)
        principal_id = _make_principal(pc)

        phc = PeopleHealthChannel(conn)
        record = phc.record_health_fact(
            person_id=principal_id, kind="condition", value="seasonal allergies",
            source="operator", idempotency_id="rf1")
        assert record.status == "confirmed"
        assert record.person_id == principal_id

    def test_recording_for_a_non_consented_other_raises(self, conn):
        from sovereign_agent.mem_channels.people import PeopleChannel
        from sovereign_agent.mem_channels.people_health import (
            ConsentRequiredError,
            PeopleHealthChannel,
        )

        pc = PeopleChannel(conn)
        _make_principal(pc)
        other_id = _make_other(pc)

        phc = PeopleHealthChannel(conn)
        with pytest.raises(ConsentRequiredError):
            phc.record_health_fact(
                person_id=other_id, kind="condition", value="asthma",
                source="operator", idempotency_id="rf2")

    def test_recording_for_a_non_consented_other_never_writes_a_row(self, conn):
        """The consent check must fail BEFORE any insert — no partial or
        orphaned row left behind by a rejected attempt."""
        from sovereign_agent.mem_channels.people import PeopleChannel
        from sovereign_agent.mem_channels.people_health import (
            ConsentRequiredError,
            PeopleHealthChannel,
        )

        pc = PeopleChannel(conn)
        _make_principal(pc)
        other_id = _make_other(pc)

        phc = PeopleHealthChannel(conn)
        with pytest.raises(ConsentRequiredError):
            phc.record_health_fact(
                person_id=other_id, kind="condition", value="asthma",
                source="operator", idempotency_id="rf3")
        rows = conn.execute(
            "SELECT COUNT(*) FROM people_health_records WHERE person_id = ?",
            (other_id,),
        ).fetchone()
        assert rows[0] == 0

    def test_recording_after_explicit_consent_succeeds(self, conn):
        from sovereign_agent.mem_channels.people import PeopleChannel
        from sovereign_agent.mem_channels.people_health import PeopleHealthChannel

        pc = PeopleChannel(conn)
        _make_principal(pc)
        other_id = _make_other(pc)
        phc = PeopleHealthChannel(conn)  # runs the ALTER TABLE that adds the consent column
        conn.execute(
            "UPDATE people SET health_tracking_consented = 1 WHERE person_id = ?",
            (other_id,),
        )

        record = phc.record_health_fact(
            person_id=other_id, kind="medication", value="albuterol inhaler",
            dosage="2 puffs as needed", source="operator", idempotency_id="rf4")
        assert record.person_id == other_id
        assert record.dosage == "2 puffs as needed"

    def test_record_is_idempotent(self, conn):
        from sovereign_agent.mem_channels.people import PeopleChannel
        from sovereign_agent.mem_channels.people_health import PeopleHealthChannel

        pc = PeopleChannel(conn)
        principal_id = _make_principal(pc)
        phc = PeopleHealthChannel(conn)

        r1 = phc.record_health_fact(person_id=principal_id, kind="note",
                                    value="prefers morning appointments",
                                    source="operator", idempotency_id="dup1")
        r2 = phc.record_health_fact(person_id=principal_id, kind="note",
                                    value="prefers morning appointments",
                                    source="operator", idempotency_id="dup1")
        assert r1.record_id == r2.record_id
        count = conn.execute(
            "SELECT COUNT(*) FROM people_health_records WHERE idempotency_id = 'dup1'"
        ).fetchone()[0]
        assert count == 1

    def test_llm_sourced_fact_defaults_pending_low_confidence(self, conn):
        from sovereign_agent.mem_channels.people import PeopleChannel
        from sovereign_agent.mem_channels.people_health import PeopleHealthChannel

        pc = PeopleChannel(conn)
        principal_id = _make_principal(pc)
        phc = PeopleHealthChannel(conn)

        record = phc.record_health_fact(
            person_id=principal_id, kind="condition", value="possible flu",
            source="llm", idempotency_id="llm1")
        assert record.status == "pending"
        assert record.confidence <= 0.5

    def test_confirm_retract_redact_lifecycle(self, conn):
        from sovereign_agent.mem_channels.people import PeopleChannel
        from sovereign_agent.mem_channels.people_health import PeopleHealthChannel

        pc = PeopleChannel(conn)
        principal_id = _make_principal(pc)
        phc = PeopleHealthChannel(conn)

        record = phc.record_health_fact(
            person_id=principal_id, kind="condition", value="tentative diagnosis",
            source="llm", idempotency_id="lc1")
        assert record.status == "pending"

        phc.confirm_health_fact(record.record_id)
        facts = phc.list_health_facts(principal_id)
        assert facts[0].status == "confirmed"

        phc.retract_health_fact(record.record_id, reason="was wrong")
        facts = phc.list_health_facts(principal_id)
        assert facts[0].status == "retracted"

        phc.redact_health_fact(record.record_id, reason="operator request")
        facts = phc.list_health_facts(principal_id)  # excludes redacted by default
        assert facts == []

    def test_export_person_health_round_trips(self, conn):
        from sovereign_agent.mem_channels.people import PeopleChannel
        from sovereign_agent.mem_channels.people_health import PeopleHealthChannel

        pc = PeopleChannel(conn)
        principal_id = _make_principal(pc)
        phc = PeopleHealthChannel(conn)
        phc.record_health_fact(person_id=principal_id, kind="vitals",
                               value="BP 118/76", source="operator",
                               idempotency_id="ex1")

        export = phc.export_person_health(principal_id)
        assert export["person_id"] == principal_id
        assert len(export["records"]) == 1
        assert export["records"][0]["value"] == "BP 118/76"

    def test_redacted_records_excluded_from_export(self, conn):
        from sovereign_agent.mem_channels.people import PeopleChannel
        from sovereign_agent.mem_channels.people_health import PeopleHealthChannel

        pc = PeopleChannel(conn)
        principal_id = _make_principal(pc)
        phc = PeopleHealthChannel(conn)
        record = phc.record_health_fact(person_id=principal_id, kind="note",
                                        value="sensitive note", source="operator",
                                        idempotency_id="rx1")
        phc.redact_health_fact(record.record_id)

        export = phc.export_person_health(principal_id)
        assert export["records"] == []
