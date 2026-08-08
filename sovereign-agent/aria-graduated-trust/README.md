# aria-graduated-trust — hold-and-continue at Gate 4 (FABLE II · M7)

> Kevin: *"propose not act should not prevent her from being a
> forward-motion worker… not too strict where she gets confused or
> cannot work at the highest leverage."* The doctrine lives at DECISION
> BOUNDARIES, not micro-actions: **propose at boundaries; move freely
> inside grants.** Same words, one place each: `loop.py`'s AUTONOMY
> section, `handoff/02_SAFETY_MODEL.md` item 3, `CLAUDE.md` golden rule 1.

## The concrete bottleneck, fixed
Gate 4 used to PAUSE THE WHOLE SESSION the instant one subtask crossed
the tier ceiling — orchestration death in the common case of "one Tier-2
step buried in twenty Tier-1 ones." Now (`hold_and_continue`, default
**on**): the over-tier subtask is marked `awaiting_approval` and the rest
of the queue keeps flowing. When nothing pending remains, every held
subtask batches into ONE approval ask — one human decision, zero lost
momentum. Opting a session out (`state.hold_and_continue = False`)
reproduces the exact old full-stop behavior, byte for byte.

## Resuming held work
- `sov session status <id>` — progress, held ids, revision count
- `sov session approve <id>` / `--all` — approve one or every held subtask
- `sov session skip <id>` — mark one skipped
- Cockpit: `/approve [id]` mirrors `/resume`'s discovery shape

## Plan updates mid-work, resiliently (Kevin, mid-round ask)
`revise_pending_subtasks()` / `sov session revise --remove <id> --why "…"`
reorders, edits, or drops **pending** subtasks only — the subtask
currently `in_progress` (and anything done/blocked/held) is never
touched, so a plan edit never interrupts running work. Every revision is
audit-trailed (`PlanRevision`, mirrors `QueueExtension`) with a required
justification.

## Proving ground (suite v2 → v3)
`graduated-trust-hold`: five T1 subtasks + one T2 among them — the
session completes the five and holds the one (previously: full stop at
subtask #2).

## Verify / Apply
```bash
./scripts/verify_module.sh aria-graduated-trust
./scripts/safe_apply.sh aria-graduated-trust
```
