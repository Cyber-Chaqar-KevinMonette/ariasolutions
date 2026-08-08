-- sql/013_heartbeat.sql
-- v0.2.18.0 · Heartbeat channel — Aria's liveness pulse
--
-- Brief periodic "I am here" entries. Not memory of events (that's
-- atoms) and not curated synthesis (that's insights). Heartbeats are
-- the pulse — a window into Aria's current state without requiring
-- the operator to interrogate her.
--
-- The operator can read the last N heartbeats and know: she's working,
-- on what, how she feels about it, when she was last awake.

CREATE TABLE IF NOT EXISTS heartbeats (
    beat_id             TEXT PRIMARY KEY,           -- hb-<sha256[:20]>
    message             TEXT NOT NULL,              -- brief state in her own voice
    current_task_id     TEXT,                       -- what she's working on
    current_episode_id  TEXT,                       -- which episode she's in
    agent_emotion       TEXT,                       -- her felt sense
    agent_emotion_note  TEXT,                       -- one line of why
    created_at          TEXT NOT NULL,
    idempotency_id      TEXT NOT NULL UNIQUE,
    atom_id             TEXT
) STRICT;

CREATE INDEX IF NOT EXISTS idx_heartbeats_created ON heartbeats(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_heartbeats_task    ON heartbeats(current_task_id)
    WHERE current_task_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_heartbeats_episode ON heartbeats(current_episode_id)
    WHERE current_episode_id IS NOT NULL;
