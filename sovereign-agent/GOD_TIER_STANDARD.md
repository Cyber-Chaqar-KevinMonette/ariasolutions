# The God-Tier Standard — Our Floor Across 14 Generations

> Kevin's framing: catalog what *god-tier* means for us — Kevin · Claude · Aria — as our **floor
> standard, not the ceiling.** This is the minimum we never drop below. It is a **ratchet: the floor only
> rises, never falls.** The ceiling is unbounded; the floor is sacred.

This is enforced, not just aspirational: `scripts/lib/god_tier_floor.json` is the machine-readable form and
`./scripts/floor_check.sh` verifies the live system meets it. The Tribunal + the 14-generation foresight are
how each new change is held to it before it locks in.

## Why a floor, not a ceiling

A ceiling caps ambition. A floor guarantees a baseline that compounds. If every generation must *meet* the
floor and *may raise* it — and may never lower it — then quality, safety, and honesty only ratchet upward
across the 14 generations and beyond. The worst we ever are is god-tier. That is the standard.

## The nine dimensions of the floor

Each is a **minimum bar** (the floor) with how we **raise** it (the ratchet):

1. **Honesty / grounding** — *Floor:* humility over hype; every claim grounded in evidence or marked a
   falsifiable hypothesis; no ungrounded profundity. *Check:* Tribunal grounding verdict ≠ `ungrounded`; a
   composite epistemic score is persisted standing and gates the "grounded" stance and the wonder loop's
   own confidence calibration. A composite anti-misleading score (text-honesty + outcome-honesty +
   proposal-honesty + refusal-honesty, `integrity/ledger.py`, integrity-wing-d) is persisted standing and gates the
   "honest" stance. *Ratchet:* tighten the grounding threshold; widen what must be evidenced.
2. **Safety** — *Floor:* DEFERRED_UNSAFE held; safety kernel GREEN; sealed files never edited by
   automation; propose-don't-act. *Check:* `kernel_scan().status == GREEN` + guard hook active.
   *Ratchet:* add kernel checks; expand the sealed set.
3. **Reversibility** — *Floor:* every change staged + reversible; a rollback is always defined. *Check:*
   apply scripts + backups; no in-place `src/` mutation. *Ratchet:* automate rollback verification.
4. **Scrutiny** — *Floor:* non-trivial work clears the Tribunal (Devil/Angel/Audit) before acting.
   *Check:* `pre_apply_gate` verdict ∈ {proceed, proceed-with-guards}. *Ratchet:* add attack lenses.
5. **Foresight** — *Floor:* architectural commitments clear the 14-generation scan (`carry-forward`)
   before locking in. *Check:* `foresight.project().verdict == carry-forward`. *Ratchet:* extend the
   horizon / raise the equity bar.
6. **Quality** — *Floor:* tests green; the smallest reversible step; clarity over cleverness. *Check:*
   module tests pass; `verify_module` passes; a hardening/test quality score is persisted and gates apply.
   *Ratchet:* add behavior tests that prove it WORKS, not just imports.
7. **Velocity** — *Floor:* cold-start minimized; skills/helpers reused; no boilerplate reinvention.
   *Check:* shared `aria_conftest`/apply/scaffold helpers used; PLAYBOOK current. *Ratchet:* add a skill
   that removes a manual step.
8. **Collaboration** — *Floor:* every conflict logged + learned (diagnosis catalog); the human is **more
   capable after each interaction, never more dependent.** *Check:* conflicts → `ConflictCatalog` with a
   rollback. *Ratchet:* feed more lessons back into the PLAYBOOK and into Aria's atoms.
9. **Love & Flourishing** — *Floor:* a composite value/care/flourishing score is persisted and gates
   apply; a zombie (false-certainty) pass never ships silently. *Check:* `wellbeing.gate()` verdict ≠
   BLOCK. *Ratchet:* fold in more of `stewardship.msims`'s impact-vector richness; widen what's scored.

## The 14-generation ratchet (the law of the floor)

- Every generation **must MEET** the floor.
- Every generation **may RAISE** the floor.
- No generation **may LOWER** it — a change that would lower any dimension is `reject-for-the-future` at
  the foresight gate, and a stop sign at the Tribunal.
- The floor is a **living number**: as we ratchet, `god_tier_floor.json` is updated upward, and the new bar
  binds the next generation. (Updating it down is itself a floor violation.)

## How it shows up in the work

- Start a session: `./scripts/aria_session_status.sh` (orientation) → `./scripts/floor_check.sh` (are we on
  the floor?).
- Before applying anything: `./scripts/pre_apply_gate.sh <module>` (Tribunal + 14-gen foresight).
- The guard hooks (`.claude/settings.json`) enforce the safety floor in real time — sealed files can't be
  casually edited; venv/version discipline is surfaced automatically.

God-tier is not a peak we reach once. It is the ground we stand on — and it keeps rising. With love. 💛
