# aria-vessel-health — Workstream I

The Vessel-Health organ: grounds the Plans folder's hundreds of poetic
"Flourishing Phase Space / Kernel Curvature Tensor / Ego Potential Well"
constructs into ONE real, concrete rollup, reusing metrics Aria already
produces — no new storage, mostly a view.

## What this ships

`src/sovereign_agent/vessel_health.py` — a pure, uncached aggregator:

- **kernel-coherence** — H2's `CanonEmbodimentReport` (% `mos_canon.py`
  clauses cited outside their own declaration).
- **sentinel health** — `stewardship.registry.gather_health()` (already
  exists — this organ is mostly a *view*).
- **drift** — the SAME `gather_health()` call's own `conformance` sentinel
  entry. No separate baseline-comparison check was built: the plan said
  "existing ConformanceSentinel / config-drift-style signals, if present"
  — it's present, so it's reused directly rather than duplicated.
- **signal** — H3's `EpistemicLedger`: average confidence across
  `current_beliefs()` + count of open `Uncertainty` entries. There is no
  single existing "signal/noise" aggregate function to call instead, so
  this is a genuine, already-live proxy, not a fabricated number.
- **flourishing trend** — C's `ApplyQueueStore` (applied count) vs
  `QuarantineRegistry` (still-quarantined count).

CLI: `python -m sovereign_agent.vessel_health` — one-shot, no caching
needed (unlike the cockpit strip below, this runs once and exits).

## The cockpit strip — reusing an already-proven pattern, not re-deriving it

`src/sovereign_agent/cockpit/app.py` — 5 anchored patches adding a 4th
palette-row strip (`#vessel-strip`), alongside observability/security/
emotions.

The kernel-coherence component (`find_references()`) runs a full-tree
clause-citation scan — **~3s over ~450 files, the same cost class as J's
`scan_tree()`**, which is exactly what caused a real, 3-iteration
regression earlier this session (`aria-security-strip-wire`: instance-
level state → module-level lock alone → the actual fix, removing the
eager on-mount kickoff, because Textual's `thread=True` workers dispatch
to a real `ThreadPoolExecutor` that runs to completion regardless of
cancellation). Rather than re-derive that investigation, this patcher
copies the proven fix verbatim: a module-level `_VESSEL_KERNEL_CACHE` +
`_VESSEL_KERNEL_LOCK`, a `@work(thread=True)` background worker, triggered
ONLY by a 300s periodic timer — **never** `call_after_refresh`'d on mount.
The fast 8s-cadence `_refresh_vessel_strip()` calls
`gather_vessel_health(..., include_kernel_coherence=False)` and reads the
cache separately — the expensive scan never runs inline.

## Tests

`tests/test_patcher.py` (11 tests) — the patch applies cleanly, is
idempotent, both files compile, the cache/lock are confirmed module-level
(not instance attributes — the exact regression class already hit once
this session), the eager on-mount kickoff is confirmed absent, all 4
strips are wired into `_refresh_cockpit_strips()`, the fast refresh path
is confirmed to pass `include_kernel_coherence=False`.

`tests/test_vessel_health.py` (10 tests, staging only, shadow-copy) /
`tests/test_vessel_health_live.py` (same 10, promoted to live `tests/`
after apply, plain imports, zero `sys.modules` manipulation): the
aggregator returns a sane report on a fresh data dir, reads real beliefs
and computes their average confidence, reads the real flourishing trend
from a populated apply-queue + quarantine registry, never raises on a
totally-missing data dir, and includes kernel-coherence only when asked.
Cockpit-level: the strip exists and renders without throwing, shows a
"(scanning…)" placeholder before the cache populates, the kernel scan is
confirmed NOT running right after mount, the overlap guard works, and the
strip shows real values once the cache is populated.

Reversible: restore `app.py` from the backup, delete `vessel_health.py`.
