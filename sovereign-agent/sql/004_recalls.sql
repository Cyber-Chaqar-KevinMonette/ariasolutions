-- sql/004_recalls.sql
-- v0.2.16.0 · Recall subsystem
--
-- Recalls are Aria's curated answers to "remember X for me." They are:
--   * first-class persisted records (a row + a markdown file on disk)
--   * sourced from atoms (provenance preserved, source list is FK-safe)
--   * staleness-aware (sources can move; recalls flag themselves)
--   * append-only with supersedes chains (an updated recall does NOT
--     destroy its predecessor; the previous version is still readable)
--   * redactable via tombstone (recall row marked, file deleted)
--   * searchable by title and rendered content via FTS5
--
-- Design rule: we never delete a recall row except via redaction. We
-- never delete a recall source row except when the recall itself is
-- redacted. The on-disk markdown file mirrors the row; deleting the
-- file leaves the row, which is fine — the file can be regenerated
-- from `body_md`.

CREATE TABLE IF NOT EXISTS recalls (
    recall_id           TEXT PRIMARY KEY,           -- rc-<sha256[:20]>
    title               TEXT NOT NULL,              -- short human title
    query               TEXT,                       -- the question that produced this
    body_md             TEXT NOT NULL,              -- full markdown body
    summary             TEXT,                       -- 1-2 sentence summary
    kind                TEXT NOT NULL,              -- 'person' | 'topic' | 'horizon' | 'ad-hoc'
    subject_id          TEXT,                       -- nullable: person_id, atom_id, etc.
    confidence          REAL NOT NULL DEFAULT 0.6,  -- 0-1, capped
    status              TEXT NOT NULL DEFAULT 'fresh',
                                                   -- 'fresh' | 'stale' | 'obsolete' | 'redacted'
    review_at           TEXT,                       -- ISO ts; nullable; if set, scheduled re-review
    created_at          TEXT NOT NULL,              -- ISO ts (UTC)
    last_verified_at    TEXT,                       -- ISO ts; updated by steward
    staled_at           TEXT,                       -- ISO ts; set when status -> stale
    obsoleted_at        TEXT,                       -- ISO ts; set when status -> obsolete
    redacted_at         TEXT,                       -- ISO ts; set when status -> redacted
    redaction_reason    TEXT,
    supersedes          TEXT,                       -- recall_id of previous version (nullable)
    superseded_by       TEXT,                       -- recall_id of next version (nullable)
    idempotency_id      TEXT NOT NULL UNIQUE,
    atom_id             TEXT,                       -- companion atom for retrieval
    file_path           TEXT,                       -- path on disk (under recalls/ room)
    CHECK (status IN ('fresh', 'stale', 'obsolete', 'redacted')),
    CHECK (kind IN ('person', 'topic', 'horizon', 'ad-hoc', 'meta'))
) STRICT;

CREATE INDEX IF NOT EXISTS idx_recalls_subject
    ON recalls(subject_id) WHERE subject_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_recalls_kind_status
    ON recalls(kind, status);
CREATE INDEX IF NOT EXISTS idx_recalls_status_review
    ON recalls(status, review_at) WHERE review_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_recalls_created_at
    ON recalls(created_at);
CREATE INDEX IF NOT EXISTS idx_recalls_supersedes
    ON recalls(supersedes) WHERE supersedes IS NOT NULL;


CREATE TABLE IF NOT EXISTS recall_sources (
    recall_source_id    TEXT PRIMARY KEY,           -- rs-<sha256[:20]>
    recall_id           TEXT NOT NULL,
    source_kind         TEXT NOT NULL,              -- 'atom' | 'fact' | 'person' | 'event'
    source_id           TEXT NOT NULL,              -- the referenced id (free-form by kind)
    weight              REAL NOT NULL DEFAULT 1.0,  -- relative contribution
    captured_at         TEXT NOT NULL,              -- ISO ts at recall-creation time
    captured_chain_head TEXT,                       -- chain head of source atom at capture
    is_current          INTEGER NOT NULL DEFAULT 1, -- 1 if still reflects current state
    FOREIGN KEY (recall_id) REFERENCES recalls(recall_id),
    CHECK (source_kind IN ('atom', 'fact', 'person', 'event', 'recall'))
) STRICT;

CREATE INDEX IF NOT EXISTS idx_recall_sources_recall
    ON recall_sources(recall_id);
CREATE INDEX IF NOT EXISTS idx_recall_sources_lookup
    ON recall_sources(source_kind, source_id);


-- FTS5 over recall title + summary + body for "recall of recalls"
CREATE VIRTUAL TABLE IF NOT EXISTS recalls_fts USING fts5(
    title,
    summary,
    body_md,
    content='recalls',
    content_rowid='rowid',
    tokenize='porter unicode61'
);

-- Trigger maintenance: keep FTS in sync. We index ALL recalls (including
-- redacted) but the search layer filters by status, so we can show "what
-- we used to remember" if explicitly asked.
CREATE TRIGGER IF NOT EXISTS recalls_fts_ai AFTER INSERT ON recalls BEGIN
    INSERT INTO recalls_fts(rowid, title, summary, body_md)
    VALUES (new.rowid, new.title, COALESCE(new.summary, ''), new.body_md);
END;

CREATE TRIGGER IF NOT EXISTS recalls_fts_ad AFTER DELETE ON recalls BEGIN
    INSERT INTO recalls_fts(recalls_fts, rowid, title, summary, body_md)
    VALUES ('delete', old.rowid, old.title, COALESCE(old.summary, ''), old.body_md);
END;

CREATE TRIGGER IF NOT EXISTS recalls_fts_au AFTER UPDATE ON recalls BEGIN
    INSERT INTO recalls_fts(recalls_fts, rowid, title, summary, body_md)
    VALUES ('delete', old.rowid, old.title, COALESCE(old.summary, ''), old.body_md);
    INSERT INTO recalls_fts(rowid, title, summary, body_md)
    VALUES (new.rowid, new.title, COALESCE(new.summary, ''), new.body_md);
END;
