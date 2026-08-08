-- sql/009_reasoning.sql
-- v0.2.18.0 · Reasoning channel — durable chain-of-thought
--
-- Aria's working thought process — where she goes from "I notice X"
-- through "I hypothesize Y because evidence Z" to "I conclude W with
-- confidence C." This is the trace, not the synthesis (which is
-- insights) and not the action (which is tasks). Reasoning is the
-- working-out itself.

CREATE TABLE IF NOT EXISTS reasoning_traces (
    trace_id            TEXT PRIMARY KEY,           -- rt-<sha256[:20]>
    title               TEXT NOT NULL,              -- the question or topic
    opened_at           TEXT NOT NULL,              -- ISO ts
    closed_at           TEXT,                       -- ISO ts; NULL while open
    status              TEXT NOT NULL DEFAULT 'open',
                                                   -- 'open' | 'concluded' | 'abandoned' | 'redacted'
    conclusion          TEXT,                       -- the final answer (or 'unknown')
    confidence          REAL NOT NULL DEFAULT 0.5,  -- 0-1
    related_task_id     TEXT,                       -- optional task this came out of
    parent_trace_id     TEXT,                       -- for nested reasoning
    idempotency_id      TEXT NOT NULL UNIQUE,
    atom_id             TEXT,
    redacted_at         TEXT,
    CHECK (status IN ('open', 'concluded', 'abandoned', 'redacted'))
) STRICT;

CREATE INDEX IF NOT EXISTS idx_reasoning_status ON reasoning_traces(status);
CREATE INDEX IF NOT EXISTS idx_reasoning_opened ON reasoning_traces(opened_at);
CREATE INDEX IF NOT EXISTS idx_reasoning_task   ON reasoning_traces(related_task_id)
    WHERE related_task_id IS NOT NULL;


-- Each step in the reasoning trace. Append-only.
CREATE TABLE IF NOT EXISTS reasoning_steps (
    step_id             TEXT PRIMARY KEY,           -- rs-<sha256[:20]>
    trace_id            TEXT NOT NULL,
    step_number         INTEGER NOT NULL,           -- ordering within trace
    step_kind           TEXT NOT NULL,
                                                   -- 'observation' | 'hypothesis' | 'evidence'
                                                   -- 'counter_evidence' | 'revision' | 'note'
    content             TEXT NOT NULL,
    confidence          REAL NOT NULL DEFAULT 0.5,
    sources             TEXT NOT NULL DEFAULT '[]', -- json array of upstream ids
    created_at          TEXT NOT NULL,
    FOREIGN KEY (trace_id) REFERENCES reasoning_traces(trace_id),
    CHECK (step_kind IN ('observation', 'hypothesis', 'evidence',
                          'counter_evidence', 'revision', 'note'))
) STRICT;

CREATE INDEX IF NOT EXISTS idx_reasoning_steps_trace
    ON reasoning_steps(trace_id, step_number);

-- FTS over content for "what have I reasoned about X"
CREATE VIRTUAL TABLE IF NOT EXISTS reasoning_traces_fts USING fts5(
    title,
    conclusion,
    content='reasoning_traces',
    content_rowid='rowid',
    tokenize='porter unicode61'
);

CREATE TRIGGER IF NOT EXISTS reasoning_traces_fts_ai AFTER INSERT ON reasoning_traces BEGIN
    INSERT INTO reasoning_traces_fts(rowid, title, conclusion)
    VALUES (new.rowid, new.title, COALESCE(new.conclusion, ''));
END;

CREATE TRIGGER IF NOT EXISTS reasoning_traces_fts_au AFTER UPDATE ON reasoning_traces BEGIN
    INSERT INTO reasoning_traces_fts(reasoning_traces_fts, rowid, title, conclusion)
    VALUES ('delete', old.rowid, old.title, COALESCE(old.conclusion, ''));
    INSERT INTO reasoning_traces_fts(rowid, title, conclusion)
    VALUES (new.rowid, new.title, COALESCE(new.conclusion, ''));
END;

CREATE TRIGGER IF NOT EXISTS reasoning_traces_fts_ad AFTER DELETE ON reasoning_traces BEGIN
    INSERT INTO reasoning_traces_fts(reasoning_traces_fts, rowid, title, conclusion)
    VALUES ('delete', old.rowid, old.title, COALESCE(old.conclusion, ''));
END;
