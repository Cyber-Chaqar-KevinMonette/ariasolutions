-- 003_people.sql — durable people memory
--
-- The People channel records the humans (and named non-humans) Aria knows. It
-- shares atoms.db with the rest of the memory subsystem so universal_recall
-- finds person atoms alongside everything else. Append-only with redaction
-- tombstones — the row is preserved for forensic audit but the API refuses
-- to return its contents once redacted.
--
-- TIER 3 — every write requires an idempotency_id (MOS §16). Mutations land
-- here only through PeopleChannel methods that run inside BEGIN IMMEDIATE.
--
-- Invariants enforced by the schema (not by code):
--   1. At most one principal: partial unique index on is_principal = 1.
--   2. Person → canonical_name is unique (case-insensitive via the alias
--      table; canonical_name itself stores the display form).
--   3. Aliases are unique across the whole table — two people cannot share
--      an alias without an explicit merge.
--   4. Facts must reference a person that exists.
--   5. Redactions must reference a person that exists.

PRAGMA foreign_keys = ON;

-- ─── People ────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS people (
    person_id        TEXT PRIMARY KEY,                    -- "pp-<sha256[:20]>" of canonical_name + idempotency_id
    canonical_name   TEXT NOT NULL,                       -- display form ("Kevin", "Dr. R. Feynman")
    canonical_lower  TEXT NOT NULL,                       -- case-folded canonical_name for de-dup
    is_principal     INTEGER NOT NULL DEFAULT 0,          -- 1 = the operator (exactly one allowed)
    web_enrichment_allowed INTEGER NOT NULL DEFAULT 0,    -- per-person opt-in for internet lookups
    created_at       TEXT NOT NULL,                       -- ISO 8601 UTC
    updated_at       TEXT NOT NULL,                       -- mirrors latest fact write
    idempotency_id   TEXT NOT NULL UNIQUE,                -- MOS §16 contract for upsert
    atom_id          TEXT,                                -- companion atom in atoms.people (semantic recall)
    redacted_at      TEXT                                 -- non-null = tombstoned; API refuses reads
) STRICT;

CREATE UNIQUE INDEX IF NOT EXISTS idx_people_canonical_lower
    ON people(canonical_lower) WHERE redacted_at IS NULL;

-- Schema-level guarantee that at most one principal exists at a time.
CREATE UNIQUE INDEX IF NOT EXISTS idx_people_one_principal
    ON people(is_principal) WHERE is_principal = 1 AND redacted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_people_created   ON people(created_at);
CREATE INDEX IF NOT EXISTS idx_people_redacted  ON people(redacted_at);

-- ─── Aliases ───────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS people_aliases (
    alias_id         TEXT PRIMARY KEY,                    -- "al-<sha256[:20]>"
    person_id        TEXT NOT NULL REFERENCES people(person_id),
    alias            TEXT NOT NULL,                       -- display form ("Kev", "kmon")
    alias_lower      TEXT NOT NULL,                       -- case-folded for lookup
    added_at         TEXT NOT NULL,
    source           TEXT NOT NULL DEFAULT 'operator',    -- 'operator' | 'merge' | 'inference'
    confidence       REAL NOT NULL DEFAULT 1.0 CHECK (confidence BETWEEN 0 AND 1)
) STRICT;

CREATE UNIQUE INDEX IF NOT EXISTS idx_aliases_lower ON people_aliases(alias_lower);
CREATE INDEX IF NOT EXISTS idx_aliases_person ON people_aliases(person_id);

-- ─── Facts ─────────────────────────────────────────────────────────────────
--
-- A fact is one structured claim about a person. The (kind, value) shape
-- captures both typed knowledge ("works_at: Stanford") and freeform notes
-- ("note: prefers walking meetings"). Facts have provenance and a status.
--
-- status semantics:
--   - 'pending'   — LLM-extracted or otherwise unverified; do not surface as truth.
--   - 'confirmed' — operator promoted it; safe to cite to the operator.
--   - 'retracted' — was promoted, then walked back. Kept for audit.

CREATE TABLE IF NOT EXISTS people_facts (
    fact_id          TEXT PRIMARY KEY,                    -- "pf-<sha256[:20]>"
    person_id        TEXT NOT NULL REFERENCES people(person_id),
    kind             TEXT NOT NULL,                       -- "role" | "interest" | "research_area" | "lab" | "publication" | "contact" | "note" | "tag" | ...
    value            TEXT NOT NULL,                       -- the fact itself
    source           TEXT NOT NULL,                       -- "operator" | "llm" | "import:<filename>" | "web:<url>"
    source_event_id  TEXT,                                -- evidence chain: which event captured this?
    confidence       REAL NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    status           TEXT NOT NULL DEFAULT 'pending'      -- 'pending' | 'confirmed' | 'retracted'
        CHECK (status IN ('pending', 'confirmed', 'retracted')),
    created_at       TEXT NOT NULL,
    confirmed_at     TEXT,                                -- when promoted to 'confirmed'
    retracted_at     TEXT,                                -- when moved to 'retracted'
    idempotency_id   TEXT NOT NULL UNIQUE,
    atom_id          TEXT,
    superseded_by    TEXT REFERENCES people_facts(fact_id) -- chain of corrections
) STRICT;

CREATE INDEX IF NOT EXISTS idx_facts_person       ON people_facts(person_id);
CREATE INDEX IF NOT EXISTS idx_facts_kind         ON people_facts(kind);
CREATE INDEX IF NOT EXISTS idx_facts_status       ON people_facts(status);
CREATE INDEX IF NOT EXISTS idx_facts_person_kind  ON people_facts(person_id, kind);

-- ─── Merge events (for reversible identity merges) ─────────────────────────
--
-- When two people records turn out to be the same person, merge() writes a
-- merge_event capturing the source and target. split() can replay this in
-- reverse to re-separate them.

CREATE TABLE IF NOT EXISTS people_merge_events (
    merge_id         TEXT PRIMARY KEY,                    -- "mg-<sha256[:20]>"
    from_person_id   TEXT NOT NULL,                       -- person that was absorbed (no FK — may be removed)
    into_person_id   TEXT NOT NULL REFERENCES people(person_id),
    merged_at        TEXT NOT NULL,
    operator_note    TEXT,
    idempotency_id   TEXT NOT NULL UNIQUE,
    reversed_at      TEXT                                 -- non-null if a split() undid this merge
) STRICT;

CREATE INDEX IF NOT EXISTS idx_merge_into     ON people_merge_events(into_person_id);
CREATE INDEX IF NOT EXISTS idx_merge_reversed ON people_merge_events(reversed_at);

-- ─── Redactions ────────────────────────────────────────────────────────────
--
-- A redaction does NOT delete the row — it marks it tombstoned. The API
-- refuses to surface redacted records or their facts/aliases. The audit
-- path can still read them.

CREATE TABLE IF NOT EXISTS people_redactions (
    redaction_id     TEXT PRIMARY KEY,                    -- "rd-<sha256[:20]>"
    person_id        TEXT NOT NULL REFERENCES people(person_id),
    redacted_at      TEXT NOT NULL,
    reason           TEXT,
    idempotency_id   TEXT NOT NULL UNIQUE
) STRICT;

CREATE INDEX IF NOT EXISTS idx_redactions_person ON people_redactions(person_id);
