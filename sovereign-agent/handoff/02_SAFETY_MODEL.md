# 02 — Safety model (layered; every layer independently tested)

1. **Authority tiers** (`authority.py`): every tool declares tier 0-3 +
   failure_modes. Mode ceilings: BUSY=1, others=3. Withheld tools are not
   even visible to the model. Tier 3 additionally needs an approval token.
2. **Path scope** (`pathguard.py`): BUSY writes ⊆ sandbox. A GARDEN
   (`scope: dir:` in the /work line) extends BUSY to that folder by the
   human's explicit written grant and ADDS a wall to every other mode.
3. **The four session gates** (`run_session`): PROTOCOL-ZERO (`/halt`,
   instant) → operator interrupt (pause at boundary) → session budget
   WITH safety margin → per-subtask authority (over-tier subtasks are
   HELD, not a full-session stop — hold-and-continue, default on; every
   held subtask batches into ONE approval ask; `sov session approve`
   resumes them). Doctrine: propose at boundaries; move freely inside grants.
4. **Scope contracts** (`scope.py`): pre-registered honesty — in/out,
   done_when, watch, security; out-of-scope proposals HELD for review;
   drift visible early. Contracts narrow, never widen.
5. **Mode gating**: `/mode work` required for ANY autonomous run; chat
   mode proposes-and-waits. Idle wondering: work mode + 3/day.
6. **No-interrupt queueing**: operator messages during a run queue to the
   to_aria inbox, deliver at boundaries. `/halt` bypasses.
7. **Kill switches** (each tested to really work): SOV_NO_SENTINELS
   (master), per-sentinel SOV_NO_<ID>_SENTINEL, SOV_NO_PROMPT_DIET,
   SOV_NO_GUIDANCE_DIET, SOV_NO_WONDER, SOV_NO_JOURNAL,
   SOV_BACKUP_CADENCE_HOURS / SOV_BACKUP_ROOT.
8. **Restore is Tier-3 human-gated**; backups are automatic (additive),
   restoring is always a human act.
