-- sql/015_people_health.sql
-- Integrity round follow-on · People-Health channel — offline health
-- tracking, scoped to the principal + explicitly-consented others.
--
-- Kevin: a doctor's-office internet outage blocked things that should
-- have just worked locally. Health tracking is a natural EXTENSION of
-- the existing People channel (sql/003_people.sql), not a new subsystem
-- — same idempotency/redaction/bitemporal discipline as people_facts and
-- relationships.
--
-- CONSENT GATE (structural, not just documented): `people.
-- health_tracking_consented` defaults FALSE for every person except the
-- principal (set TRUE at profile creation). `PeopleHealthChannel.
-- record_health_fact()` (mem_channels/people_health.py) raises — never
-- silently drops — if a caller tries to record a health fact for a
-- non-principal person whose consent flag isn't TRUE. This migration
-- only adds the column and the table; the enforcement lives in code.
--
-- Documents/images referenced by a health record go through the EXISTING
-- content-addressed archive (sql/014_archive.sql) via document_hash — no
-- new blob storage invented.
--
-- This migration is IDEMPOTENT the same way 007_bitemporal is: ALTER
-- TABLE ADD COLUMN errors if the column already exists, so the channel
-- bootstrap code (ensure_people_health_schema(), mirroring
-- ensure_people_schema()) wraps execution in try/except — see
-- mem_channels/people_health.py.

-- ─── Consent flag on the existing people table ────────────────────────────

ALTER TABLE people ADD COLUMN health_tracking_consented INTEGER NOT NULL DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_people_health_consented
    ON people(health_tracking_consented) WHERE health_tracking_consented = 1;

-- ─── Health records ────────────────────────────────────────────────────────
--
-- One structured health record per row. `kind` mirrors people_facts'
-- typed-kind pattern; `document_hash` optionally points at a document or
-- image (a lab report, a prescription photo) already stored in the
-- content-addressed archive. Bitemporal (valid_from/valid_until) from
-- day one, matching 007_bitemporal's later-added augmentation to
-- people_facts/recalls — no retrofit needed here.

CREATE TABLE IF NOT EXISTS people_health_records (
    record_id        TEXT PRIMARY KEY,                    -- "ph-<sha256[:20]>"
    person_id        TEXT NOT NULL REFERENCES people(person_id),
    kind             TEXT NOT NULL,                        -- 'condition' | 'medication' | 'allergy'
                                                          -- | 'appointment' | 'vitals' | 'note'
    value            TEXT NOT NULL,                        -- the fact itself
    dosage           TEXT,                                 -- for 'medication' kind
    severity         TEXT,                                 -- free-form ('mild' | 'moderate' | 'severe' | ...)
    onset_date       TEXT,                                 -- ISO 8601, when it started
    resolved_date    TEXT,                                 -- ISO 8601, when it resolved; NULL = ongoing
    source           TEXT NOT NULL DEFAULT 'operator',      -- 'operator' | 'llm' | 'import' | 'inferred'
    confidence       REAL NOT NULL DEFAULT 1.0 CHECK (confidence BETWEEN 0 AND 1),
    status           TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'confirmed', 'retracted')),
    document_hash    TEXT REFERENCES archive(content_hash), -- optional: a stored document/image
    valid_from       TEXT,                                  -- bitemporal: when true in the world
    valid_until      TEXT,                                  -- NULL = still valid
    created_at       TEXT NOT NULL,
    confirmed_at     TEXT,
    retracted_at     TEXT,
    idempotency_id   TEXT NOT NULL UNIQUE,
    atom_id          TEXT,
    superseded_by    TEXT REFERENCES people_health_records(record_id),
    redacted_at      TEXT,                                  -- non-null = tombstoned (right-to-be-forgotten)
    CHECK (source IN ('operator', 'llm', 'import', 'inferred'))
) STRICT;

CREATE INDEX IF NOT EXISTS idx_health_person       ON people_health_records(person_id);
CREATE INDEX IF NOT EXISTS idx_health_kind         ON people_health_records(kind);
CREATE INDEX IF NOT EXISTS idx_health_status       ON people_health_records(status);
CREATE INDEX IF NOT EXISTS idx_health_person_kind  ON people_health_records(person_id, kind);
CREATE INDEX IF NOT EXISTS idx_health_redacted     ON people_health_records(redacted_at);
CREATE INDEX IF NOT EXISTS idx_health_valid_window
    ON people_health_records(person_id, kind, valid_from, valid_until);
