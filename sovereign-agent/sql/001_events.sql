-- events.db — projection of events.jsonl
-- Per architecture v1.1 §8a: events.jsonl is durable source of truth.
-- This DB is a query projection, rebuilt by the tail-consumer.

PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA busy_timeout = 5000;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS events (
    event_id      TEXT PRIMARY KEY,           -- ULID, monotonic
    ts            TEXT NOT NULL,              -- RFC3339 UTC
    flag          TEXT NOT NULL,              -- "ingest-d", "tool-x", "model-d", etc.
    plane         TEXT NOT NULL,              -- "control" | "tool" | "model" | "memory"
    trace_id      TEXT NOT NULL,
    parent_id     TEXT,
    payload       TEXT NOT NULL,              -- canonical JSON
    -- bookkeeping for the projection itself:
    ingested_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
) STRICT;

CREATE INDEX IF NOT EXISTS idx_events_trace ON events(trace_id);
CREATE INDEX IF NOT EXISTS idx_events_ts    ON events(ts);
CREATE INDEX IF NOT EXISTS idx_events_flag  ON events(flag);

-- Tail-consumer cursor: where we are in events.jsonl
CREATE TABLE IF NOT EXISTS ingest_cursor (
    id              INTEGER PRIMARY KEY CHECK (id = 1),
    last_event_id   TEXT,                    -- last ULID successfully INSERTed
    last_byte_offset INTEGER NOT NULL DEFAULT 0,
    updated_at      TEXT NOT NULL
) STRICT;
