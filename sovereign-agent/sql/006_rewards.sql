-- sql/006_rewards.sql
-- v0.2.16.0 · Reward channel
--
-- A positive-feedback ledger for the behaviors Aria wants to reinforce
-- in herself. Not a gamification gimmick — this is *legible
-- self-modeling*: every reward names what was good, why, and gives
-- the operator a window into what Aria is reinforcing in herself.
--
-- Anti-egotism is built in: confident wrong answers are NEGATIVE
-- rewards. Careful uncertainty is POSITIVE. Finding gaps is rewarded
-- more than declaring completion.
--
-- Append-only. Never deleted. Tombstoned via redacted_at if a reward
-- is later judged to have been awarded in error (which is itself a
-- reward-worthy event — naming our own mistakes).

CREATE TABLE IF NOT EXISTS rewards (
    reward_id           TEXT PRIMARY KEY,           -- rw-<sha256[:20]>
    behavior_kind       TEXT NOT NULL,              -- see BEHAVIOR_KINDS in reward.py
    polarity            TEXT NOT NULL DEFAULT 'positive',
                                                   -- 'positive' | 'corrective'
    intensity           INTEGER NOT NULL DEFAULT 1, -- 1 small, 2 notable, 3 large
    points              REAL NOT NULL,              -- signed (negative for corrective)
    evidence            TEXT NOT NULL,              -- what triggered the reward
    related_task_id     TEXT,                       -- optional: task this came out of
    related_recall_id   TEXT,                       -- optional: recall this came out of
    note                TEXT,                       -- Aria's own reflection
    created_at          TEXT NOT NULL,
    idempotency_id      TEXT NOT NULL UNIQUE,
    atom_id             TEXT,
    redacted_at         TEXT,
    CHECK (polarity IN ('positive', 'corrective')),
    CHECK (intensity BETWEEN 1 AND 3)
) STRICT;

CREATE INDEX IF NOT EXISTS idx_rewards_kind ON rewards(behavior_kind);
CREATE INDEX IF NOT EXISTS idx_rewards_created ON rewards(created_at);
CREATE INDEX IF NOT EXISTS idx_rewards_task ON rewards(related_task_id)
    WHERE related_task_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_rewards_polarity ON rewards(polarity, created_at);
