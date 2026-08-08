-- sql/005_tasks.sql
-- v0.2.16.0 · Task memory channel
--
-- Every meaningful unit of work Aria does has begin/end, outcome,
-- detailed notes, lessons, and an agent-side emotional reading.
-- Tasks are append-only at the audit layer, but state transitions
-- (started → in_progress → finished/abandoned) are normal updates.
--
-- A task is NOT an atom; a task GROUPS atoms produced during the work.
-- The atoms remain the immutable record; the task is the structured
-- index over them with named beginning, ending, and meaning.

CREATE TABLE IF NOT EXISTS task_records (
    task_id             TEXT PRIMARY KEY,         -- tk-<sha256[:20]>
    title               TEXT NOT NULL,
    description         TEXT,                     -- what we set out to do
    started_at          TEXT NOT NULL,            -- ISO ts (UTC)
    finished_at         TEXT,                     -- ISO ts; NULL while in_progress
    status              TEXT NOT NULL DEFAULT 'in_progress',
                                                 -- 'in_progress' | 'success' | 'partial' | 'failed' | 'abandoned'
    outcome_summary     TEXT,                     -- 1-3 sentence outcome
    detailed_notes      TEXT,                     -- markdown body
    lessons             TEXT,                     -- what to remember next time
    follow_ups          TEXT,                     -- json array of follow-up items
    related_recall_ids  TEXT,                     -- json array of recall_ids
    related_atom_ids    TEXT,                     -- json array of atom_ids
    agent_emotion       TEXT,                     -- one of EmotionalReading literals
    agent_emotion_note  TEXT,                     -- one-line reflection
    confidence          REAL NOT NULL DEFAULT 0.7,
    parent_task_id      TEXT,                     -- for nested tasks
    idempotency_id      TEXT NOT NULL UNIQUE,
    atom_id             TEXT,                     -- companion atom for retrieval
    redacted_at         TEXT,                     -- tombstone
    CHECK (status IN ('in_progress', 'success', 'partial', 'failed', 'abandoned'))
) STRICT;

CREATE INDEX IF NOT EXISTS idx_task_records_status
    ON task_records(status);
CREATE INDEX IF NOT EXISTS idx_task_records_started
    ON task_records(started_at);
CREATE INDEX IF NOT EXISTS idx_task_records_finished
    ON task_records(finished_at) WHERE finished_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_task_records_parent
    ON task_records(parent_task_id) WHERE parent_task_id IS NOT NULL;

-- FTS over title + detailed_notes + lessons for "what tasks have I done about X"
CREATE VIRTUAL TABLE IF NOT EXISTS task_records_fts USING fts5(
    title,
    detailed_notes,
    lessons,
    content='task_records',
    content_rowid='rowid',
    tokenize='porter unicode61'
);

CREATE TRIGGER IF NOT EXISTS task_records_fts_ai AFTER INSERT ON task_records BEGIN
    INSERT INTO task_records_fts(rowid, title, detailed_notes, lessons)
    VALUES (new.rowid, new.title, COALESCE(new.detailed_notes, ''), COALESCE(new.lessons, ''));
END;

CREATE TRIGGER IF NOT EXISTS task_records_fts_au AFTER UPDATE ON task_records BEGIN
    INSERT INTO task_records_fts(task_records_fts, rowid, title, detailed_notes, lessons)
    VALUES ('delete', old.rowid, old.title, COALESCE(old.detailed_notes, ''), COALESCE(old.lessons, ''));
    INSERT INTO task_records_fts(rowid, title, detailed_notes, lessons)
    VALUES (new.rowid, new.title, COALESCE(new.detailed_notes, ''), COALESCE(new.lessons, ''));
END;

CREATE TRIGGER IF NOT EXISTS task_records_fts_ad AFTER DELETE ON task_records BEGIN
    INSERT INTO task_records_fts(task_records_fts, rowid, title, detailed_notes, lessons)
    VALUES ('delete', old.rowid, old.title, COALESCE(old.detailed_notes, ''), COALESCE(old.lessons, ''));
END;
