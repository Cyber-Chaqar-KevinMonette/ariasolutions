# aria-quality-gate — wiring qa/hardening into real gates (Quality round · Q2)

> Kevin: *"Quality gates perhaps?"* Today neither `pre_apply_gate.sh` nor
> `safe_apply.sh`'s post-apply step calls anything in `qa/*`. This wires
> it in with real teeth.

## What it adds
- `src/sovereign_agent/quality/gate.py` — `gate(paths) -> QualityGateVerdict`
  (PASS/WARN/BLOCK). BLOCK only on a real critical (weight-≥8) hardening
  failure; WARN on a middling score with no critical gaps; PASS on a clean
  pass OR an honestly empty target list (never a silent block on "nothing
  to check"). Persists via Q1's ledger. Kill switch `SOV_NO_QUALITY_GATE=1`.
- `scripts/lib/quality_gate.py` — CLI wrapper, same shape as
  `scripts/lib/scrutiny.py` (works staged or live).
- **Wired into two real gates**:
  1. `scripts/pre_apply_gate.sh` — runs the quality gate over a module's
     payload alongside Tribunal + Foresight; worst-wins the exit code.
  2. `scripts/safe_apply.sh` step 5 — reuses the snapshot commit already
     written in step 2 (`git diff --name-only <snapshot> -- '*.py'`) to
     find exactly the files THIS apply touched, gates them, folds a BLOCK
     into the *existing* rollback path — no new machinery, rides the
     M9-hardened auto-rollback.

## Bugs found and fixed while building this
- `FileScore.failures` mixed critical and non-critical labels together;
  `gate.py`'s BLOCK message named non-critical gaps (e.g. `typed_signatures`,
  weight 4) as if they were critical. Added `FileScore.critical_failures`
  (weight-≥8 only) to `quality/ledger.py` so a BLOCK message names only
  what's actually critical.
- The CLI's own repo-root resolution (`parents[2]`) broke depending on
  whether the file was running staged or promoted — fixed with the same
  walk-up-to-a-stable-marker pattern `test_apply_system.py` already uses.
- `_ensure_engine()`'s "is the engine already importable?" check tested
  the parent package (`sovereign_agent.quality`), which succeeds once Q1
  is live — short-circuiting before Q2's own new `gate.py` submodule was
  ever reachable pre-apply. Fixed to check the submodule specifically.

## Verify / Apply
```bash
./scripts/verify_module.sh aria-quality-gate
./scripts/safe_apply.sh aria-quality-gate
```
