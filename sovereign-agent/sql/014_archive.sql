-- sql/014_archive.sql
-- v0.2.18.0 · Content-addressed archive layer
--
-- A blob store keyed by SHA-256 hash. Two atoms with the same content
-- share one row. The atoms table can reference the archive by hash
-- instead of duplicating content. Backup, replication, and integrity
-- verification become first-class.

CREATE TABLE IF NOT EXISTS archive (
    content_hash    TEXT PRIMARY KEY,             -- sha256 hex digest of content
    size_bytes      INTEGER NOT NULL,
    content_type    TEXT NOT NULL DEFAULT 'text/plain',
    content         BLOB NOT NULL,                -- the actual bytes
    encoding        TEXT NOT NULL DEFAULT 'utf-8',
    created_at      TEXT NOT NULL,                -- first time we saw this content
    refcount        INTEGER NOT NULL DEFAULT 0,   -- atoms pointing here
    sealed          INTEGER NOT NULL DEFAULT 0,   -- 1 = immutable forever
    signature       TEXT,                         -- optional detached signature
    CHECK (size_bytes >= 0),
    CHECK (refcount >= 0),
    CHECK (sealed IN (0, 1))
) STRICT;

CREATE INDEX IF NOT EXISTS idx_archive_content_type ON archive(content_type);
CREATE INDEX IF NOT EXISTS idx_archive_refcount     ON archive(refcount);
CREATE INDEX IF NOT EXISTS idx_archive_created_at   ON archive(created_at);

-- A reference log so we can audit who pointed at what
CREATE TABLE IF NOT EXISTS archive_refs (
    ref_id          TEXT PRIMARY KEY,             -- ar-<sha256[:20]>
    content_hash    TEXT NOT NULL,
    ref_kind        TEXT NOT NULL,                -- 'atom' | 'recall' | 'task' | ...
    ref_id_value    TEXT NOT NULL,                -- the referrer's id
    added_at        TEXT NOT NULL,
    removed_at      TEXT,                         -- soft-delete; refcount maintained
    FOREIGN KEY (content_hash) REFERENCES archive(content_hash)
) STRICT;

CREATE INDEX IF NOT EXISTS idx_archive_refs_hash    ON archive_refs(content_hash);
CREATE INDEX IF NOT EXISTS idx_archive_refs_lookup  ON archive_refs(ref_kind, ref_id_value);
