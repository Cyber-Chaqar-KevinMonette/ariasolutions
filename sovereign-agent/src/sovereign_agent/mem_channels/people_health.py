"""
╔══════════════════════════════════════════════════════════════════════════╗
║  mem_channels/people_health.py — offline health tracking                 ║
║  People-Health round · Tier 3, consent-gated                             ║
║                                                                           ║
║  Kevin: a doctor's-office internet outage blocked things that should     ║
║  have just worked locally. This extends the existing People channel     ║
║  (mem_channels/people.py) with structured health records — same         ║
║  idempotency/redaction/bitemporal discipline as people_facts.            ║
║                                                                           ║
║  CONSENT GATE (structural, not just documented): every person except    ║
║  the principal defaults `health_tracking_consented = FALSE`.            ║
║  `record_health_fact()` RAISES — never silently drops — if asked to     ║
║  record a fact for a non-principal, non-consented person. Scoped to     ║
║  the principal + explicitly-consented others (family/dependents         ║
║  brought to real appointments), not arbitrary third-party tracking.     ║
║                                                                           ║
║  Documents/images referenced by a health record go through the          ║
║  EXISTING content-addressed archive (archive.py) via document_hash —    ║
║  no new blob storage invented.                                          ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import hashlib
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Literal

from ..channels import ChannelSpec, MemoryChannel, register_channel

HealthKind = Literal["condition", "medication", "allergy", "appointment", "vitals", "note"]
HealthStatus = Literal["pending", "confirmed", "retracted"]
HealthSource = Literal["operator", "llm", "import", "inferred"]

WELL_KNOWN_HEALTH_KINDS = (
    "condition", "medication", "allergy", "appointment", "vitals", "note",
)


class ConsentRequiredError(PermissionError):
    """Raised when a health fact is attempted for a non-principal person
    who has not explicitly consented to health tracking. Never caught and
    silently swallowed by this module — a caller must actually resolve
    consent, not work around the error."""


class PersonNotFoundError(KeyError):
    pass


class RedactedError(PermissionError):
    pass


# ─── DDL bootstrap ─────────────────────────────────────────────────────────


def _add_health_consent_column(conn: sqlite3.Connection) -> None:
    """Idempotent — mirrors bitemporal.add_bitemporal_columns()'s exact
    guarded-ALTER pattern: safe to call on every channel construction,
    catches 'duplicate column name' as "already migrated," re-raises
    anything else."""
    try:
        conn.execute(
            "ALTER TABLE people ADD COLUMN health_tracking_consented "
            "INTEGER NOT NULL DEFAULT 0"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_people_health_consented "
            "ON people(health_tracking_consented) WHERE health_tracking_consented = 1"
        )
    except sqlite3.OperationalError as e:
        if "duplicate column" not in str(e).lower():
            raise


_HEALTH_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS people_health_records (
    record_id        TEXT PRIMARY KEY,
    person_id        TEXT NOT NULL REFERENCES people(person_id),
    kind             TEXT NOT NULL,
    value            TEXT NOT NULL,
    dosage           TEXT,
    severity         TEXT,
    onset_date       TEXT,
    resolved_date    TEXT,
    source           TEXT NOT NULL DEFAULT 'operator',
    confidence       REAL NOT NULL DEFAULT 1.0 CHECK (confidence BETWEEN 0 AND 1),
    status           TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'confirmed', 'retracted')),
    document_hash    TEXT REFERENCES archive(content_hash),
    valid_from       TEXT,
    valid_until      TEXT,
    created_at       TEXT NOT NULL,
    confirmed_at     TEXT,
    retracted_at     TEXT,
    idempotency_id   TEXT NOT NULL UNIQUE,
    atom_id          TEXT,
    superseded_by    TEXT REFERENCES people_health_records(record_id),
    redacted_at      TEXT,
    CHECK (source IN ('operator', 'llm', 'import', 'inferred'))
) STRICT;

CREATE INDEX IF NOT EXISTS idx_health_person       ON people_health_records(person_id);
CREATE INDEX IF NOT EXISTS idx_health_kind         ON people_health_records(kind);
CREATE INDEX IF NOT EXISTS idx_health_status       ON people_health_records(status);
CREATE INDEX IF NOT EXISTS idx_health_person_kind  ON people_health_records(person_id, kind);
CREATE INDEX IF NOT EXISTS idx_health_redacted     ON people_health_records(redacted_at);
CREATE INDEX IF NOT EXISTS idx_health_valid_window
    ON people_health_records(person_id, kind, valid_from, valid_until);
"""


def ensure_people_health_schema(conn: sqlite3.Connection) -> None:
    """Idempotent — safe to call on every open. The ALTER (consent column)
    and the CREATE TABLE are handled separately (see
    _add_health_consent_column) because ALTER TABLE ADD COLUMN is NOT
    naturally idempotent the way CREATE TABLE IF NOT EXISTS is — same
    split `bitemporal.add_bitemporal_columns()` already uses."""
    _add_health_consent_column(conn)
    conn.executescript(_HEALTH_TABLE_SQL)
    conn.commit()


# ─── Data shapes ────────────────────────────────────────────────────────────


@dataclass
class HealthRecord:
    record_id: str
    person_id: str
    kind: str
    value: str
    source: str
    confidence: float
    status: str
    created_at: str
    dosage: str | None = None
    severity: str | None = None
    onset_date: str | None = None
    resolved_date: str | None = None
    document_hash: str | None = None
    confirmed_at: str | None = None
    retracted_at: str | None = None
    superseded_by: str | None = None


@register_channel
class PeopleHealthChannel(MemoryChannel):
    """Offline health memory. Tier 3. Idempotent writes. Consent-gated for
    anyone who isn't the principal. Redactable."""

    spec = ChannelSpec(
        name="people_health",
        description=(
            "Offline health records (conditions, medications, allergies, "
            "appointments, vitals, notes) for the principal and "
            "explicitly-consented others, with optional document/image "
            "references via the content-addressed archive."
        ),
        authority_tier=3,
        default_confidence=0.95,
        requires_idempotency=True,
        introduced_in="0.4.1",
        voice="Careful, private, never presumptuous — health facts wait for "
              "the operator, and never get recorded for someone who hasn't said yes.",
    )

    def __init__(self, conn: sqlite3.Connection):
        super().__init__(conn)
        ensure_people_health_schema(conn)

    @contextmanager
    def _writer_tx(self) -> Iterator[None]:
        in_tx = self.conn.in_transaction
        if not in_tx:
            self.conn.execute("BEGIN IMMEDIATE")
        self._in_outer_tx = True
        try:
            yield
            if not in_tx:
                self.conn.commit()
        except Exception:
            if not in_tx:
                self.conn.rollback()
            raise
        finally:
            self._in_outer_tx = False

    @staticmethod
    def _hash_id(prefix: str, seed: str) -> str:
        return f"{prefix}-" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:20]

    @staticmethod
    def _utc_now() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    def _fetch_person(self, person_id: str) -> tuple[bool, bool, str] | None:
        """(is_principal, health_tracking_consented, canonical_name) or None."""
        row = self.conn.execute(
            "SELECT is_principal, health_tracking_consented, canonical_name, redacted_at "
            "FROM people WHERE person_id = ?",
            (person_id,),
        ).fetchone()
        if row is None:
            return None
        if row[3] is not None:
            raise RedactedError(f"person {person_id} is redacted")
        return bool(row[0]), bool(row[1]), row[2]

    def _assert_consented(self, person_id: str) -> None:
        """The structural consent gate. Raises ConsentRequiredError —
        never silently drops — if this person is neither the principal
        nor explicitly consented."""
        person = self._fetch_person(person_id)
        if person is None:
            raise PersonNotFoundError(person_id)
        is_principal, consented, name = person
        if not is_principal and not consented:
            raise ConsentRequiredError(
                f"{name} ({person_id}) has not consented to health tracking — "
                f"set people.health_tracking_consented for them first, or "
                f"record this for the principal instead")

    def record_health_fact(
        self, *,
        person_id: str,
        kind: str,
        value: str,
        source: HealthSource,
        idempotency_id: str,
        confidence: float | None = None,
        status: HealthStatus | None = None,
        dosage: str | None = None,
        severity: str | None = None,
        onset_date: str | None = None,
        resolved_date: str | None = None,
        document_hash: str | None = None,
        valid_from: str | None = None,
        valid_until: str | None = None,
    ) -> HealthRecord:
        """Record one health fact about a person. Raises ConsentRequiredError
        if `person_id` is neither the principal nor explicitly consented —
        checked BEFORE any write, inside the same transaction as the
        idempotency lookup, so there is no window where an unconsented
        record could land.

        Defaults follow the same untrusted-input doctrine as people_facts:
        operator=confirmed/0.95, everything else=pending with lower
        confidence.
        """
        if not kind or not value:
            raise ValueError("kind and value are required")
        if not idempotency_id:
            raise ValueError("idempotency_id required")
        if source not in ("operator", "llm", "import", "inferred"):
            raise ValueError(f"invalid health source: {source!r}")

        defaults = {
            "operator": (0.95, "confirmed"),
            "llm": (0.40, "pending"),
            "import": (0.60, "pending"),
            "inferred": (0.40, "pending"),
        }
        d_conf, d_status = defaults[source]
        if confidence is None:
            confidence = d_conf
        if status is None:
            status = d_status  # type: ignore[assignment]
        if not 0.0 <= confidence <= 1.0:
            raise ValueError(f"confidence out of range: {confidence}")

        record_id = self._hash_id("ph", f"{person_id}:{kind}:{idempotency_id}")
        now = self._utc_now()
        confirmed_at = now if status == "confirmed" else None

        with self._writer_tx():
            row = self.conn.execute(
                "SELECT record_id, person_id, kind, value, dosage, severity, "
                "onset_date, resolved_date, source, confidence, status, "
                "document_hash, created_at, confirmed_at, retracted_at, superseded_by "
                "FROM people_health_records WHERE idempotency_id = ?",
                (idempotency_id,),
            ).fetchone()
            if row is not None:
                return HealthRecord(
                    record_id=row[0], person_id=row[1], kind=row[2], value=row[3],
                    dosage=row[4], severity=row[5], onset_date=row[6],
                    resolved_date=row[7], source=row[8], confidence=row[9],
                    status=row[10], document_hash=row[11], created_at=row[12],
                    confirmed_at=row[13], retracted_at=row[14], superseded_by=row[15],
                )

            # The consent gate — inside the same write transaction, before
            # any row is inserted.
            self._assert_consented(person_id)

            atom_id = self.write_atom(
                summary=f"HEALTH[{kind}/{status}]: {value}",
                content={"person_id": person_id, "kind": kind, "value": value,
                        "source": source, "status": status, "confidence": confidence},
                idempotency_id=f"health:{idempotency_id}",
                confidence=confidence,
                actor="people-health-channel",
            )

            vf = valid_from if valid_from is not None else now
            self.conn.execute(
                "INSERT INTO people_health_records (record_id, person_id, kind, value, "
                "dosage, severity, onset_date, resolved_date, source, confidence, "
                "status, document_hash, valid_from, valid_until, created_at, "
                "confirmed_at, idempotency_id, atom_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (record_id, person_id, kind, value, dosage, severity, onset_date,
                 resolved_date, source, confidence, status, document_hash, vf,
                 valid_until, now, confirmed_at, idempotency_id, atom_id),
            )

        return HealthRecord(
            record_id=record_id, person_id=person_id, kind=kind, value=value,
            dosage=dosage, severity=severity, onset_date=onset_date,
            resolved_date=resolved_date, source=source, confidence=confidence,
            status=status, document_hash=document_hash, created_at=now,
            confirmed_at=confirmed_at,
        )

    def confirm_health_fact(self, record_id: str) -> None:
        now = self._utc_now()
        with self._writer_tx():
            cur = self.conn.execute(
                "UPDATE people_health_records SET status='confirmed', confirmed_at=? "
                "WHERE record_id=? AND status != 'retracted'",
                (now, record_id),
            )
            if cur.rowcount == 0:
                raise KeyError(f"no confirmable health record {record_id!r}")

    def retract_health_fact(self, record_id: str, *, reason: str = "") -> None:
        now = self._utc_now()
        with self._writer_tx():
            cur = self.conn.execute(
                "UPDATE people_health_records SET status='retracted', retracted_at=? "
                "WHERE record_id=?",
                (now, record_id),
            )
            if cur.rowcount == 0:
                raise KeyError(f"no health record {record_id!r}")

    def redact_health_fact(self, record_id: str, *, reason: str = "") -> None:
        """Right-to-be-forgotten tombstone — the row is preserved for
        forensic audit but list/export refuse its contents once redacted."""
        now = self._utc_now()
        with self._writer_tx():
            cur = self.conn.execute(
                "UPDATE people_health_records SET redacted_at=? WHERE record_id=?",
                (now, record_id),
            )
            if cur.rowcount == 0:
                raise KeyError(f"no health record {record_id!r}")

    def list_health_facts(self, person_id: str, *, kind: str | None = None,
                          include_redacted: bool = False) -> list[HealthRecord]:
        q = ("SELECT record_id, person_id, kind, value, dosage, severity, "
            "onset_date, resolved_date, source, confidence, status, "
            "document_hash, created_at, confirmed_at, retracted_at, superseded_by "
            "FROM people_health_records WHERE person_id = ?")
        params: list = [person_id]
        if not include_redacted:
            q += " AND redacted_at IS NULL"
        if kind:
            q += " AND kind = ?"
            params.append(kind)
        q += " ORDER BY created_at DESC"
        rows = self.conn.execute(q, params).fetchall()
        return [
            HealthRecord(
                record_id=r[0], person_id=r[1], kind=r[2], value=r[3], dosage=r[4],
                severity=r[5], onset_date=r[6], resolved_date=r[7], source=r[8],
                confidence=r[9], status=r[10], document_hash=r[11], created_at=r[12],
                confirmed_at=r[13], retracted_at=r[14], superseded_by=r[15],
            )
            for r in rows
        ]

    def export_person_health(self, person_id: str) -> dict:
        """Data sovereignty — parity with PeopleChannel.export_person():
        the operator can always leave with the health data recorded for
        anyone they've consented to track."""
        person = self._fetch_person(person_id)
        if person is None:
            raise PersonNotFoundError(person_id)
        records = self.list_health_facts(person_id, include_redacted=False)
        return {
            "person_id": person_id,
            "records": [
                {
                    "record_id": r.record_id, "kind": r.kind, "value": r.value,
                    "dosage": r.dosage, "severity": r.severity,
                    "onset_date": r.onset_date, "resolved_date": r.resolved_date,
                    "source": r.source, "confidence": r.confidence,
                    "status": r.status, "document_hash": r.document_hash,
                    "created_at": r.created_at,
                }
                for r in records
            ],
        }
