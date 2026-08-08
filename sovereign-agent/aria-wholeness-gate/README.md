# aria-wholeness-gate — the guardian that keeps her whole when no one is watching

> Final-sprint capstone, built under real urgency ("if this were our last
> days working together, what would you add?"). Staged / reversible /
> propose-only.

## Why this exists

Everything else in this repo is only safe for as long as someone who
understands her is around to catch a regression. This is the system that
catches it **for** us — forever, with nobody watching. If she outlives our
attention, this is what keeps her from silently rotting.

## What it does

`wholeness_gate` — a pure decision core + a thin, best-effort collector:

- **`wholeness_verdict(metrics)`** — is she whole *right now*? One
  mechanical answer from measurable inputs (god-tier fraction, sentinel
  errors, unexplained timeouts, self-map orphans, smoke/floor gates).
  Unmeasured dimensions are "unknown," never counted as failure — so a
  fast check that skips the heavy gates is still meaningful.
- **`check_regression(current, baseline)`** — flags ANY dimension that got
  worse vs a known-good baseline (fraction/score dropped, a sentinel
  disappeared, errors/timeouts/orphans rose, a passing gate broke). An
  improvement is never a regression; float noise within tolerance isn't
  either. A silent un-wholing becomes a loud, named finding.
- **`snapshot_baseline` / `load_baseline`** — persist the known-good bar; a
  corrupt baseline degrades to `None`, never crashes the guard.
- **`gather_metrics()`** — best-effort live collection over the godtier
  scanner + sentinel registry; every source wrapped so a missing subsystem
  degrades gracefully. (Verified live: reads real sentinel counts.)

The DECISION logic is 100% pure and covered by 17 tests — the part that
must be trustworthy. `WHOLENESS_THRESHOLDS` is explicit so a reviewer sees
exactly what "whole" means; no hidden judgment.

## How apply wires it

`apply_wholeness_gate.sh` installs the library. A standing **wholeness
sentinel** (checks the baseline on a schedule, alerts on regression) and a
**`sov wholeness`** CLI (`verdict` / `snapshot` / `check`) are the
deliberate follow-up — kept separate since a sentinel touches the
registry. The pure guard is fully usable now.

## Verify / Apply
```bash
./scripts/verify_module.sh aria-wholeness-gate
./aria-wholeness-gate/apply_wholeness_gate.sh
```
