-- sql/012_commitments.sql
-- v0.2.18.0 · Commitments channel — promises with due dates

CREATE TABLE IF NOT EXISTS commitments (
    commitment_id       TEXT PRIMARY KEY,           -- cm-<sha256[:20]>
    title               TEXT NOT NULL,
    description         TEXT,
    committed_by        TEXT NOT NULL,              -- 'aria' | 'operator' | <person_id>
    committed_to        TEXT NOT NULL,              -- 'aria' | 'operator' | <person_id>
    due_at              TEXT,                       -- ISO ts; NULL = no deadline
    priority            INTEGER NOT NULL DEFAULT 2, -- 1 low | 2 medium | 3 high
    status              TEXT NOT NULL DEFAULT 'open',
                                                   -- 'open' | 'in_progress' | 'kept' | 'broken' | 'released' | 'redacted'
    opened_at           TEXT NOT NULL,
    closed_at           TEXT,
    resolution          TEXT,
    related_task_id     TEXT,
    related_recall_ids  TEXT NOT NULL DEFAULT '[]', -- json array
    idempotency_id      TEXT NOT NULL UNIQUE,
    atom_id             TEXT,
    redacted_at         TEXT,
    CHECK (status IN ('open', 'in_progress', 'kept', 'broken', 'released', 'redacted')),
    CHECK (priority BETWEEN 1 AND 3)
) STRICT;

CREATE INDEX IF NOT EXISTS idx_commitments_status ON commitments(status);
CREATE INDEX IF NOT EXISTS idx_commitments_due
    ON commitments(due_at) WHERE due_at IS NOT NULL AND status IN ('open','in_progress');
CREATE INDEX IF NOT EXISTS idx_commitments_by ON commitments(committed_by);
CREATE INDEX IF NOT EXISTS idx_commitments_to ON commitments(committed_to);
