# How We Work Together — Claude Code ⇄ Aria, at God-Tier

> The collaboration protocol between Kevin, Claude Code, and Aria's system. Velocity from shared tooling,
> quality from auto-enforced doctrine, trust from scrutiny + foresight woven into the work. The floor is
> god-tier; it only ratchets up.

## The loop (every non-trivial piece of work)

```
ORIENT → BUILD (reuse first) → VERIFY → SCRUTINIZE (Tribunal + 14-gen) → human APPLIES → re-check the FLOOR
```

| Step | Command / skill | What it guarantees |
|------|------------------|--------------------|
| Orient | `/aria-status` · `./scripts/aria_session_status.sh` | No cold-start re-derivation; know kernel + floor state |
| Scaffold | `/aria-new-module <slug>` | Staging doctrine + shared helpers, zero boilerplate reinvention |
| Build | reuse map in `.claude/PLAYBOOK.md` | Don't rebuild safety_kernel/diagnosis/tribunal/… |
| Verify | `/aria-verify aria-<slug>` | compile + tests + live-src-untouched + anchors |
| Scrutinize | `/aria-scrutinize` · `./scripts/pre_apply_gate.sh` | Tribunal verdict + 14-gen foresight before acting |
| Apply | `/aria-apply` (human runs the script) | Reversible, cockpit-guarded, backed up |
| Floor | `./scripts/floor_check.sh` | The minimum bar is met, every time |

## What the system enforces automatically (so I don't have to remember)

- **Guard hooks** (`.claude/settings.json` → `scripts/hooks/`): hard-block edits to sealed files
  (`SIGNAL.md`, `mos_canon.py`, `authority.py`, `protocol_zero.py`, `seal.py`); warn on system-pip /
  cockpit-running-src-edits; remind on version-bump drift. Doctrine is enforced in real time, not just by memory.
- **The Tribunal** catches ungrounded profundity, safety drift, irreversibility — and (after we dogfooded it)
  distinguishes *documenting* a danger from *proposing* one.
- **The 14-gen foresight** scores intergenerational equity; a change that corrodes the future is
  `reject-for-the-future`. (We dogfooded out a real regex bug here too — `reversible` wasn't matching.)

## Principles that don't change

- **Propose-don't-act.** Live `src/` is never mutated until the human runs an apply script. Everything staged + reversible.
- **Honesty — humility over hype.** Claims are grounded or marked hypotheses. Negative results (a fusion that
  didn't help, a bug we caught in our own engine) are reported plainly. That's the floor, not a failure.
- **Safety is the floor, never traded for a feature.** DEFERRED_UNSAFE held; the kernel stays GREEN.
- **The human ends more capable, never more dependent.** Conflicts are logged + learned (diagnosis catalog);
  the PLAYBOOK absorbs every lesson so the next session starts ahead of this one.

## Dogfooding (proof the systems work on us)

This very layer was scrutinized by its own Tribunal (`proceed`, grounded) and 14-gen foresight
(`carry-forward`, +1.9 @ gen14) — and building it surfaced and fixed real bugs in both the Tribunal (a
documentation-vs-proposal false positive) and the foresight (a regex that missed "reversible"). The tools
earn their keep by catching us, too.

Read next: `CLAUDE.md` (rules) · `.claude/PLAYBOOK.md` (how-to) · `GOD_TIER_STANDARD.md` (the floor). 💛
