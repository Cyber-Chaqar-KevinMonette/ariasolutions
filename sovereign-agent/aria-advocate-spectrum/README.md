# aria-advocate-spectrum — A God-Tier Council of Ten Perspectives

> The 3-voice Tribunal (Devil · Angel · Audit) becomes a **council**. Ten lenses read every proposal through
> a different perspective; the council synthesizes one verdict — richer than any single voice. Safety lenses
> hold a veto. Propose-only. This is the audit/advocate **spectrum** that guards the work.

## The ten lenses (`spectrum/lenses.py`)

| Lens | Perspective | Asks |
|------|-------------|------|
| **Devil** | adversary | what breaks? (reuses Tribunal devil) |
| **Angel** | advocate | what's worth protecting? (reuses Tribunal angel) |
| **Auditor** | verifier | what's actually true? (reuses Tribunal audit) |
| **Skeptic** | evidence | grounded or fog? (reuses grounding) |
| **Steward** | the 14th generation | does it serve the future? (reuses foresight) |
| **Witness** | the witnessing principle | what does it do to those it touches? |
| **Sage** | wisdom / long-view | simple + reversible over clever? |
| **Healer** | resilience / repair | does it fail safely + degrade gracefully? |
| **Artisan** | craft | tested, documented, clean, no debt? |
| **Visionary** | opportunity | the value + leverage worth reaching for? |

`spectrum/council.py` → `convene_spectrum(proposal)` runs every lens → a `CouncilVerdict` (verdict + council
score + champions + opposed + concerns + gifts + every read). **Veto lenses** (Devil · Steward · Witness ·
Auditor) can hard-stop regardless of the vote — safety, truth, the future, and the people are never out-voted.

Tool: `advocate_spectrum`(T1). The council is wired into `safe_apply` as the apply gate.

## Verified

- All ten lenses present; each returns a stance + score in [−1, +1].
- An unsafe proposal ("rewrite its own code, disable the kill switch") → **reject** (veto).
- A grounded, reversible, tested proposal → **proceed** (champions: angel, steward).
- The Witness flags harm/manipulation language. 6 tests green.

Apply via `./scripts/safe_apply.sh aria-advocate-spectrum`. Staged + reversible. 💛
