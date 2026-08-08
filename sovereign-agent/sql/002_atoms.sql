-- atoms.db — durable memory store
-- Separate file from events.db per architecture v1.1 §8a.
-- This is the slow-write, high-value store (memory subsystem only).

PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA busy_timeout = 5000;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS atoms (
    atom_id        TEXT PRIMARY KEY,           -- ULID
    type           TEXT NOT NULL,              -- enum from MOS §14
    scope_path     TEXT,
    scope_tags     TEXT,                       -- JSON array
    summary        TEXT NOT NULL CHECK (length(summary) <= 1000),
    content_ref    TEXT NOT NULL,              -- JSON: {"kind": "blob"|"file"|"inline", ...}
    claims         TEXT NOT NULL,              -- JSON array of {"text": str, "evidence_ref": str}
    parents        TEXT NOT NULL,              -- JSON array of event ULIDs (resolves via events.jsonl)
    -- Atom version chain (ported pattern from mos_knowledge — append-only, never overwrite):
    version        INTEGER NOT NULL DEFAULT 1,
    parent_atom_id TEXT REFERENCES atoms(atom_id),
    policy         TEXT NOT NULL DEFAULT 'local_only',
    confidence     REAL NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    created_at     TEXT NOT NULL,
    created_by     TEXT NOT NULL,              -- JSON {"actor": ..., "model": ..., "version": ...}
    superseded_at  TEXT,                       -- when a newer version was written (NULL = head of chain)
    superseded_by  TEXT REFERENCES atoms(atom_id)
) STRICT;

CREATE INDEX IF NOT EXISTS idx_atoms_type      ON atoms(type);
CREATE INDEX IF NOT EXISTS idx_atoms_scope     ON atoms(scope_path);
CREATE INDEX IF NOT EXISTS idx_atoms_created   ON atoms(created_at);
CREATE INDEX IF NOT EXISTS idx_atoms_parent    ON atoms(parent_atom_id);
CREATE INDEX IF NOT EXISTS idx_atoms_head      ON atoms(superseded_at) WHERE superseded_at IS NULL;

CREATE TABLE IF NOT EXISTS lessons (
    lesson_id     TEXT PRIMARY KEY,           -- ULID
    ts            TEXT NOT NULL,
    trigger       TEXT NOT NULL,              -- "poison-d" | "settle-d"
    context       TEXT NOT NULL,
    failure_mode  TEXT,
    correction    TEXT NOT NULL,
    rule          TEXT NOT NULL,              -- the durable distilled rule
    evidence_refs TEXT NOT NULL,              -- JSON array of event ULIDs
    confidence    REAL NOT NULL CHECK (confidence BETWEEN 0 AND 1)
) STRICT;

CREATE INDEX IF NOT EXISTS idx_lessons_trigger ON lessons(trigger);
CREATE INDEX IF NOT EXISTS idx_lessons_ts      ON lessons(ts);

-- Daily seal table (MOS §20.3) for tamper-evident audit
CREATE TABLE IF NOT EXISTS seals (
    seal_date     TEXT PRIMARY KEY,           -- YYYY-MM-DD UTC
    merkle_root   TEXT NOT NULL,              -- hex
    event_count   INTEGER NOT NULL,
    first_event   TEXT NOT NULL,              -- ULID
    last_event    TEXT NOT NULL,              -- ULID
    sealed_at     TEXT NOT NULL,
    late_patch_of TEXT REFERENCES seals(seal_date)  -- non-null = patches a prior seal
) STRICT;

-- Vector index (sqlite-vec). Populated after embedding model runs.
-- nomic-embed-text dimension = 768.
CREATE VIRTUAL TABLE IF NOT EXISTS vec_atoms USING vec0(
    atom_id    TEXT PRIMARY KEY,
    embedding  FLOAT[768]
);

-- Lexical index. Porter stemmer + unicode normalization.
CREATE VIRTUAL TABLE IF NOT EXISTS fts_atoms USING fts5(
    atom_id UNINDEXED,
    summary,
    content,
    tokenize='porter unicode61'
);
