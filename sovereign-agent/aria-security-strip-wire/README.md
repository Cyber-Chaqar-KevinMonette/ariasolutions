# aria-security-strip-wire — Workstream M follow-up

**Found during a plan-accuracy review this session:** M's security strip was built with an "interim"
design (authority tier census + a `safe_eval` presence check) because the plan's own text said J's
Tier-A scanners were "staged, not yet applied" at the time. That framing was wrong — J had actually
already landed live in commit `78a5560`, *before* M was built later the same session — but M's
implementation was never revisited to use it.

## What this ships

`src/sovereign_agent/cockpit/app.py` — 5 anchored patches:
- A process-wide module-level cache + lock (`_SECURITY_SCAN_CACHE`, `_SECURITY_SCAN_LOCK`,
  `_SECURITY_SCAN_RUNNING`) — deliberately module-level, not per-instance (see "the regression" below).
- `import threading` added alongside the existing stdlib imports.
- A new `_maybe_run_security_scan()` (guards against overlapping scans, process-wide) +
  `_run_security_scan_worker()` (`@work(thread=True)`, mirrors `_refresh_status_worker`'s own pattern)
  that runs `scanner_tier_a.scan_tree()` off the main thread.
- A `set_interval(300.0, ...)` — **not** the strip's existing 8s cadence — because a full scan over
  ~450 files takes ~3s (measured directly). The 8s strip refresh only ever reads the cache; the
  expensive work happens in the background every 5 minutes, and — critically — is **not** kicked off
  immediately on mount (see below).
- `_refresh_security_strip()` shows the real `blocks`/`warns` counts once the first scan completes,
  falling back to the tier-census display until then.

## The regression (found live by Kevin, root-caused via careful bisection)

This module went through **three** iterations before it was actually correct — worth recording
honestly, since each wrong turn taught something real:

1. **First cut:** cache/running-flag as `CockpitApp` *instance* attributes, kicked off immediately on
   mount via `call_after_refresh`. Applied, tests passed — but a full-suite run afterward showed 20
   new failures (`test_telemetry`, `test_v0214_hardening`, `test_vram`, etc.) that hadn't been there
   before. Bisected by re-running the same failing subset with the fix reverted (passed clean) and
   restored (failed) — confirmed this module was the cause.
2. **Second cut:** moved the cache/lock to module level (shared across all `CockpitApp` instances in
   a process, guarded by a `threading.Lock`), reasoning that separate instance-level threads piling up
   in the same process (normal in a test suite that boots many short-lived cockpits; never happens in
   real single-instance production use) were contending for the GIL. Re-ran the exact same bisection —
   **still failed**, identically. The module-level lock alone wasn't the fix.
3. **Actual root cause, found by digging into Textual internals:** `@work(thread=True)` dispatches via
   `asyncio`'s `loop.run_in_executor(None, ...)` — a real `ThreadPoolExecutor` thread. Once dispatched,
   the thread runs `scan_tree()` (CPU-bound, ~3s) to full completion no matter what; `.cancel()` only
   stops the *async* side from awaiting the result, never the underlying OS thread. So every
   `CockpitApp` boot that triggered an eager scan — regardless of instance vs. module-level state —
   spawned a real, uncancellable, CPU-bound thread. **The actual fix: stop triggering the scan eagerly
   on mount at all.** Relying purely on the 300s periodic timer means the scan literally never fires
   during a short `run_test()` window; in real production, the strip just shows the graceful interim
   fallback for the first 5 minutes of a session, an acceptable and honest UX tradeoff.
4. **A second, unrelated contributing bug found during the same investigation:** the ORIGINAL
   `test_security_strip_wire.py` (a shadow-copy-and-patch test file, needed only for pre-apply
   verification) was promoted wholesale to live `tests/`. Its `shadow_cockpit` fixture did a
   save/delete/restore dance on `sys.modules["sovereign_agent.*"]` — the *exact* class of bug already
   found and fixed once this session in `test_locator_events_fix.py`. Even with the eager-kickoff fix
   in place, this fixture alone (isolated down to just this one test file + the 3 failing ones, no
   other cockpit tests at all) still reproduced the exact same failure signature. Fixed by writing
   `test_security_strip_wire_live.py` — a plain-import version with zero `sys.modules` manipulation —
   for the promoted/live copy, keeping the shadow-copy version in staging only (`aria-security-strip-
   wire/tests/test_security_strip_wire.py`, never promoted), where it's legitimate for testing the
   patch function itself before the code is actually applied.

**Lesson for future `app.py` patches with a `thread=True` worker:** don't trigger it eagerly from
`on_mount`/`call_after_refresh` unless the work is either fast (<a few hundred ms) or genuinely safe to
leave running in the background indefinitely across many rapid app instantiations. And never promote a
shadow-copy-based test file to live `tests/` without first checking whether it manipulates
`sys.modules` — if it does, write a plain-import variant for the live copy instead.

## Tests (10/10 passing pre-apply in staging; 5/5 in the promoted live copy)

`tests/test_patcher.py` — the patch applies cleanly against the CURRENT live file, is idempotent, the
patched file compiles, the worker decorator is `thread=True` + `exclusive=True`, the cache/lock are
confirmed module-level (not instance attributes), and the eager on-mount kickoff is confirmed absent
(only the periodic timer remains). `tests/test_security_strip_wire.py` (staging only) — shadow-copy
verification of the patch function itself. `tests/test_security_strip_wire_live.py` (promoted to live
`tests/`) — the same behavioral coverage, tested directly against the real, already-patched module: no
scan starts eagerly on boot, real scan counts show once the cache is populated, the overlap guard
works, only one scan ever starts across many app instances, and `scan_tree()` runs clean against the
real `src/` tree.

Reversible: restore `app.py` from the backup.
