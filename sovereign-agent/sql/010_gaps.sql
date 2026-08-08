-- sql/010_gaps.sql
-- v0.2.18.0 · Gaps channel — known unknowns

CREATE TABLE IF NOT EXISTS knowledge_gaps (
    gap_id              TEXT PRIMARY KEY,           -- gp-<sha256[:20]>
    title               TEXT NOT NULL,              -- short statement of what's unknown
    description         TEXT,                       -- longer context
    domain              TEXT,                       -- 'person', 'topic', 'skill', 'fact', ...
    subject_ref         TEXT,                       -- optional id of the subject (person_id, etc.)
    priority            INTEGER NOT NULL DEFAULT 2, -- 1 low | 2 medium | 3 high
    status              TEXT NOT NULL DEFAULT 'open',
                                                   -- 'open' | 'investigating' | 'closed' | 'shelved' | 'redacted'
    opened_at           TEXT NOT NULL,
    closed_at           TEXT,
    resolution          TEXT,                       -- how the gap was filled (or 'unresolvable')
    related_recall_ids  TEXT NOT NULL DEFAULT '[]', -- json array
    related_task_id     TEXT,                       -- task that closed this gap
    idempotency_id      TEXT NOT NULL UNIQUE,
    atom_id             TEXT,
    redacted_at         TEXT,
    CHECK (status IN ('open', 'investigating', 'closed', 'shelved', 'redacted')),
    CHECK (priority BETWEEN 1 AND 3)
) STRICT;

CREATE INDEX IF NOT EXISTS idx_gaps_status   ON knowledge_gaps(status);
CREATE INDEX IF NOT EXISTS idx_gaps_priority ON knowledge_gaps(priority, status);
CREATE INDEX IF NOT EXISTS idx_gaps_domain   ON knowledge_gaps(domain);
CREATE INDEX IF NOT EXISTS idx_gaps_subject  ON knowledge_gaps(subject_ref)
    WHERE subject_ref IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_gaps_opened   ON knowledge_gaps(opened_at);

CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_gaps_fts USING fts5(
    title, description, resolution,
    content='knowledge_gaps',
    content_rowid='rowid',
    tokenize='porter unicode61'
);

CREATE TRIGGER IF NOT EXISTS knowledge_gaps_fts_ai AFTER INSERT ON knowledge_gaps BEGIN
    INSERT INTO knowledge_gaps_fts(rowid, title, description, resolution)
    VALUES (new.rowid, new.title, COALESCE(new.description, ''),
            COALESCE(new.resolution, ''));
END;

CREATE TRIGGER IF NOT EXISTS knowledge_gaps_fts_au AFTER UPDATE ON knowledge_gaps BEGIN
    INSERT INTO knowledge_gaps_fts(knowledge_gaps_fts, rowid, title, description, resolution)
    VALUES ('delete', old.rowid, old.title, COALESCE(old.description, ''),
            COALESCE(old.resolution, ''));
    INSERT INTO knowledge_gaps_fts(rowid, title, description, resolution)
    VALUES (new.rowid, new.title, COALESCE(new.description, ''),
            COALESCE(new.resolution, ''));
END;

CREATE TRIGGER IF NOT EXISTS knowledge_gaps_fts_ad AFTER DELETE ON knowledge_gaps BEGIN
    INSERT INTO knowledge_gaps_fts(knowledge_gaps_fts, rowid, title, description, resolution)
    VALUES ('delete', old.rowid, old.title, COALESCE(old.description, ''),
            COALESCE(old.resolution, ''));
END;
