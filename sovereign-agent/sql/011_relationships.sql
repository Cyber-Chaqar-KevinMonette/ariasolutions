-- sql/011_relationships.sql
-- v0.2.18.0 · Relationships channel — typed edges between people
--
-- The hearth has nodes (people). This adds edges. Bidirectional (most
-- relationships are mutual) but with explicit asymmetry where needed
-- (mentor → mentee is not symmetric).

CREATE TABLE IF NOT EXISTS relationships (
    relationship_id     TEXT PRIMARY KEY,           -- rl-<sha256[:20]>
    from_person_id      TEXT NOT NULL,
    to_person_id        TEXT NOT NULL,
    kind                TEXT NOT NULL,
                                                   -- 'colleague' | 'mentor' | 'mentee'
                                                   -- 'family' | 'friend' | 'collaborator'
                                                   -- 'spouse' | 'parent' | 'child'
                                                   -- 'rival' | 'student_of' | 'teacher_of'
                                                   -- 'employer_of' | 'employee_of'
                                                   -- 'acquaintance' | 'other'
    label               TEXT,                       -- free-form clarification
    started_at          TEXT,                       -- when the relationship began (valid_from)
    ended_at            TEXT,                       -- when it ended (valid_until); NULL = current
    confidence          REAL NOT NULL DEFAULT 0.7,
    source              TEXT NOT NULL DEFAULT 'operator',
                                                   -- 'operator' | 'llm' | 'import' | 'inferred'
    status              TEXT NOT NULL DEFAULT 'confirmed',
                                                   -- 'pending' | 'confirmed' | 'retracted'
    note                TEXT,
    created_at          TEXT NOT NULL,
    confirmed_at        TEXT,
    retracted_at        TEXT,
    idempotency_id      TEXT NOT NULL UNIQUE,
    atom_id             TEXT,
    redacted_at         TEXT,
    FOREIGN KEY (from_person_id) REFERENCES people(person_id),
    FOREIGN KEY (to_person_id)   REFERENCES people(person_id),
    CHECK (from_person_id != to_person_id),
    CHECK (status IN ('pending', 'confirmed', 'retracted')),
    CHECK (source IN ('operator', 'llm', 'import', 'inferred'))
) STRICT;

CREATE INDEX IF NOT EXISTS idx_relationships_from ON relationships(from_person_id);
CREATE INDEX IF NOT EXISTS idx_relationships_to   ON relationships(to_person_id);
CREATE INDEX IF NOT EXISTS idx_relationships_kind ON relationships(kind);
CREATE INDEX IF NOT EXISTS idx_relationships_status_active
    ON relationships(status, ended_at)
    WHERE status = 'confirmed' AND redacted_at IS NULL;
