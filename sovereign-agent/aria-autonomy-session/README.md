# aria-autonomy-session — Supervised Autonomy: Time-Boxed · Observable · Resumable · Bounded

> Kevin's design, made real. Aria PLANS, then presents the human options. Option 1 approves a bounded block
> of autonomous work (~90 min) before re-approval. She works inside a tight blast-radius, the human watches
> and learns, and at the timeout she PAUSES with a resumable checkpoint. The human stays in the loop.

## How a session flows

```
Aria PLANS  →  presents OPTIONS  →  human approves Option 1 (~90 min)
   → she works INSIDE THE LEASE (bounded actions only, every action observable)
   → at timeout she PAUSES with a checkpoint (done / next)
   → human: CONTINUE · RE-APPROVE another block · or enter PLAN MODE to edit the plan with her
```

## The safety core (god-tier: bounded · observable · reversible · always-stoppable)

- **Bounded blast-radius** — inside a block she may ONLY: `draft_staged_module`, `edit_staged_payload`,
  `write_doc`, `run_tests`, `verify_module`, `scrutinize`, `godtier_scan`, `record_note`. Everything else —
  `apply_module`, `edit_live_src`, `edit_sealed_file`, `outward_action`, `git_push`, `raise_tier`,
  `disable_killswitch` — is **refused** (allow-list, not deny-list). She drafts; the human applies.
- **Time-boxed lease** — default 90 min (max 120; beyond is a Tier-3 decision). The lease **expires** and
  can't strand authority; an elapsed block auto-pauses. Mirrors the `aegis/leases.py` doctrine at the
  workflow scale.
- **Observable** — every action is recorded to a live stream (`autonomy_status`) so the human watches.
- **Resumable** — `pause` writes a checkpoint (done / next); `resume` requires **re-approval** (the human
  never falls out of the loop). Plans are living + versioned (`plan_forge.py`) and grow over time.
- **Never self-starts** — `propose` presents options; only a human approval (Option 1) starts a block.

## Payload + tools
- `autonomy/session.py` — the lease, the bounded action set, pause/resume, the observation log, persistence.
- `autonomy/plan_forge.py` — living, versioned plans that grow over time even as she works.
- Tools: `autonomy_plan`(T1), `autonomy_propose`(T1), `autonomy_status`(T0), `autonomy_pause`(T1).

## Verified
- 9 tests green incl. the safety core: forbidden/unknown actions refused; expired lease refuses actions;
  resume requires re-approval; the lease auto-pauses when due; living plan grows + resumes.

Staged + reversible (backups at `aria-autonomy-session/backups/`); nothing in live `src/` changes until
`apply_autonomy.sh` runs. Raising the timeout later is a Tier-3 human decision, earned by proven safety. 💛
