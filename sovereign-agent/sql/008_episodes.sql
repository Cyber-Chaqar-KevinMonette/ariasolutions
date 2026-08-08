-- sql/008_episodes.sql
-- v0.2.17.0 · Episodes — coherent spans of activity
--
-- An episode is a *named, time-bounded session of work* with a beginning,
-- a middle, an end, and a coherent reason for being. It groups atoms,
-- tasks, recalls, and people into a single narrative the operator can
-- refer to: "remember the Wednesday afternoon we worked on the merge
-- logic" maps to an episode_id.
--
-- Episodes are append-only with state transitions:
--    open → closed → archived (or → redacted)
--
-- Member rows are weak references — they hold (kind, id) pairs by string,
-- not foreign keys, because members may live in different tables that
-- evolve at different rates. The steward audits dangling members.

CREATE TABLE IF NOT EXISTS episodes (
    episode_id          TEXT PRIMARY KEY,           -- ep-<sha256[:20]>
    title               TEXT NOT NULL,
    description         TEXT,
    started_at          TEXT NOT NULL,              -- ISO ts (UTC)
    closed_at           TEXT,                       -- ISO ts; NULL while open
    archived_at         TEXT,                       -- ISO ts; soft 'put away'
    status              TEXT NOT NULL DEFAULT 'open',
                                                   -- 'open' | 'closed' | 'archived' | 'redacted'
    summary             TEXT,                       -- written at close
    significance        INTEGER NOT NULL DEFAULT 1, -- 1 routine | 2 notable | 3 landmark
    tags                TEXT NOT NULL DEFAULT '[]', -- json array of strings
    parent_episode_id   TEXT,                       -- nesting: parent → sub-episode
    idempotency_id      TEXT NOT NULL UNIQUE,
    atom_id             TEXT,
    redacted_at         TEXT,
    CHECK (status IN ('open', 'closed', 'archived', 'redacted')),
    CHECK (significance BETWEEN 1 AND 3)
) STRICT;

CREATE INDEX IF NOT EXISTS idx_episodes_started ON episodes(started_at);
CREATE INDEX IF NOT EXISTS idx_episodes_status  ON episodes(status);
CREATE INDEX IF NOT EXISTS idx_episodes_parent  ON episodes(parent_episode_id)
    WHERE parent_episode_id IS NOT NULL;


CREATE TABLE IF NOT EXISTS episode_members (
    member_id           TEXT PRIMARY KEY,           -- em-<sha256[:20]>
    episode_id          TEXT NOT NULL,
    member_kind         TEXT NOT NULL,              -- 'atom' | 'task' | 'recall' | 'person' | 'fact' | 'reward'
    member_ref          TEXT NOT NULL,              -- the referenced id
    role                TEXT,                       -- 'primary' | 'background' | 'outcome' | etc.
    note                TEXT,                       -- one-line annotation
    added_at            TEXT NOT NULL,
    FOREIGN KEY (episode_id) REFERENCES episodes(episode_id),
    CHECK (member_kind IN ('atom', 'task', 'recall', 'person', 'fact', 'reward'))
) STRICT;

CREATE INDEX IF NOT EXISTS idx_episode_members_episode
    ON episode_members(episode_id);
CREATE INDEX IF NOT EXISTS idx_episode_members_lookup
    ON episode_members(member_kind, member_ref);

CREATE VIRTUAL TABLE IF NOT EXISTS episodes_fts USING fts5(
    title,
    description,
    summary,
    content='episodes',
    content_rowid='rowid',
    tokenize='porter unicode61'
);

CREATE TRIGGER IF NOT EXISTS episodes_fts_ai AFTER INSERT ON episodes BEGIN
    INSERT INTO episodes_fts(rowid, title, description, summary)
    VALUES (new.rowid, new.title, COALESCE(new.description, ''),
            COALESCE(new.summary, ''));
END;

CREATE TRIGGER IF NOT EXISTS episodes_fts_au AFTER UPDATE ON episodes BEGIN
    INSERT INTO episodes_fts(episodes_fts, rowid, title, description, summary)
    VALUES ('delete', old.rowid, old.title, COALESCE(old.description, ''),
            COALESCE(old.summary, ''));
    INSERT INTO episodes_fts(rowid, title, description, summary)
    VALUES (new.rowid, new.title, COALESCE(new.description, ''),
            COALESCE(new.summary, ''));
END;

CREATE TRIGGER IF NOT EXISTS episodes_fts_ad AFTER DELETE ON episodes BEGIN
    INSERT INTO episodes_fts(episodes_fts, rowid, title, description, summary)
    VALUES ('delete', old.rowid, old.title, COALESCE(old.description, ''),
            COALESCE(old.summary, ''));
END;
