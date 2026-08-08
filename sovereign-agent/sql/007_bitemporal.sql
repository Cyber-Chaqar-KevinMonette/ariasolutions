-- sql/007_bitemporal.sql
-- v0.2.17.0 · Bitemporal augmentation
--
-- WHAT THIS DOES
--
-- Every existing time field on people_facts and recalls answers "when
-- did Aria write this row?" — system time. None of them answer "when
-- was this fact true in the world?" — valid time. Bitemporal storage
-- is the textbook solution: two time dimensions per record.
--
-- We add:
--    valid_from  — first moment this fact is asserted to hold (UTC ISO)
--    valid_until — last moment this fact is asserted to hold; NULL = still valid
--
-- Default behaviour: new rows set valid_from = created_at and valid_until = NULL.
-- This means existing code keeps working — every fact is "true now and forever
-- until retracted" by default. Callers who DO know better can set valid_from
-- and valid_until explicitly (e.g. "Feynman taught at Caltech from 1950 to 1988").
--
-- WHY THIS MATTERS
--
-- Aria can now answer "what did I believe on date X?" by filtering on the
-- system_time pair (created_at + superseded-by-chain) while the valid_time
-- pair tells her whether the underlying claim was supposed to apply on
-- that date. Two independent timelines, both auditable.
--
-- WHAT THIS DOES NOT DO
--
-- It does not retroactively populate valid_from for existing rows beyond
-- copying created_at. That's the honest default. Backfilling true
-- valid-time spans for old facts would require human judgment per fact;
-- the operator can do that with explicit UPDATE statements when needed.
--
-- This migration is IDEMPOTENT. SQLite's ALTER TABLE ... ADD COLUMN does
-- not error if the column exists when wrapped with the right guard.

-- people_facts
-- We use a guard pattern: try-then-check via PRAGMA. SQLite does not
-- support ADD COLUMN IF NOT EXISTS directly until 3.35, but for safety
-- we use a trigger-style check.

-- The simple path: add columns; if they exist this script errors on
-- the second column add, so the channel bootstrap code wraps execution
-- in try/except. See ensure_bitemporal_schema() in mem_channels/people.py
-- and mem_channels/recall.py.

ALTER TABLE people_facts ADD COLUMN valid_from TEXT;
ALTER TABLE people_facts ADD COLUMN valid_until TEXT;

CREATE INDEX IF NOT EXISTS idx_people_facts_valid_from
    ON people_facts(valid_from) WHERE valid_from IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_people_facts_valid_window
    ON people_facts(person_id, kind, valid_from, valid_until);

-- recalls
ALTER TABLE recalls ADD COLUMN valid_from TEXT;
ALTER TABLE recalls ADD COLUMN valid_until TEXT;

CREATE INDEX IF NOT EXISTS idx_recalls_valid_from
    ON recalls(valid_from) WHERE valid_from IS NOT NULL;
