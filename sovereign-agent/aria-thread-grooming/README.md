# aria-thread-grooming — the loose-threads first grooming (FABLE II · M5)

> The organ's first full worklist pass: 47 undispositioned threads → 0.
> One real WIRE, two idioms the scanner learns, and written reasons for
> everything else. No silence, no suppression.

## The wire — record_action lives in /work now
`autonomy.session.record_action` (the blast-radius enforcer, finished and
dead since the autonomy-session round) is wired into `session_bridge`:
- `arm_lease(lease)` / `disarm_lease()` / `active_lease()` — auto modes
  (M6) arm an AutonomySession lease after explicit operator approval.
- Every `start_goal_session` / `resume_goal_session` dispatch is recorded
  through `record_action("run_goal_session", …)` on the lease's
  OBSERVABLE action log (saved to disk each time — watchable).
- An expired lease REFUSES new goals (PermissionError, before any session
  state is created). Leases never self-extend. No lease armed = today's
  behavior, byte-identical.
- `ALLOWED_ACTIONS` gains `run_goal_session`; `FORBIDDEN_ACTIONS`
  untouched.

## The scanner learns two idioms (Article II — don't cry wolf)
- `@mcp.tool()` / `@mcp.resource()` / `@mcp.prompt()` endpoints are
  framework-called (7 false threads).
- `MemoryChannel` subclasses register at import (10 false threads).

## The ledger — every remaining thread dispositioned
The rest of the worklist gets WIRED/RETIRED/ACCEPTED entries with written
reasons (see `loose_threads/ledger.ndjson` after apply; the apply of this
module + the disposition pass leaves the sentinel at 0 undispositioned).

## Verify / Apply
```bash
./scripts/verify_module.sh aria-thread-grooming
./scripts/safe_apply.sh aria-thread-grooming
```
