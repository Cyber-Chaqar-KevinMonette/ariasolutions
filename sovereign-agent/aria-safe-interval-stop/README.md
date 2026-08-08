# aria-safe-interval-stop — Workstream N: safe interval-stop for autonomous work mode

**Kevin's ask:** work mode's autonomous intervals (~1 hour at a time, while a human is watching)
must always stop at a clean, safe boundary — never mid-work or mid-task — and must never resume
without an explicit human approval action.

## What this composes (not a new subsystem)

Three primitives already existed with the right shape; this module wires them together:

1. **`modes.RunBudget` / `modes.effective_wall_limit`** — `RunBudget` gets a new
   `safety_margin_seconds` field (default `0`, so every existing caller's behavior is byte-for-byte
   unchanged unless it opts in). `effective_wall_limit(budget)` returns
   `max_wall_seconds - safety_margin_seconds`, floored at 0. `loop.py::_check_budget` and
   `agent_session.py::_check_session_budget` — both of which already only check budgets *between*
   iterations/subtasks, never mid-tool-call — now trip at this margined boundary instead of the
   hard limit, so the current step always has room to finish cleanly before the real deadline.
2. **`autonomy.session.AutonomySession`** (already applied) — the lease/checkpoint/approval shape:
   `expire_if_due()` pauses with a resumable `{done, next, notes}` checkpoint; `resume()` requires
   explicit `approved=True`.
3. **`interrupts.py`** (already live) — the general-purpose "explicit, separately-timestamped human
   approval" gate: `request_resume()` / `consume_resume()`.

`work_interval.py` (new) ties these into one work-mode-shaped surface:
`WorkIntervalConfig` (default 3600s interval / 360s margin, floor 60s) → `start_work_interval()` →
`interval_boundary_reached()` (checked at the same safe point as the budget checks above) →
`stop_at_safe_point()` (writes the checkpoint) → `resume_work_interval()` (refuses unless
`approved=True` was passed explicitly OR the operator separately called `interrupts.request_resume()`
— elapsed time alone never unlocks resume, no matter how long the pause has lasted).

## Deliberately out of scope for this pass

`dream_runner.py` has its own separate pause/resume (`sov dream resume <id>`), not currently routed
through `interrupts.py`. Read closely: `dream_resume_cmd` (`cli.py:3132`) already requires the human
to type the exact `dream_id` as a CLI argument and checks `d.status == "paused"` first — it already
satisfies "explicit, separately-timestamped human action required," just via a different code path
than `interrupts.consume_resume()`. Refactoring `dream_runner.py` onto the same primitive is real,
valuable polish but carries real regression risk to a working, tested system for a safety property
it already has in substance. Named here, not silently dropped — a candidate for a future pass.

## Files

- `payload/src/sovereign_agent/modes.py` — full-file replacement (adds the field + helper only).
- `payload/src/sovereign_agent/work_interval.py` — new file.
- `patcher.py` — anchored, idempotent text patches for `loop.py` / `agent_session.py`.
- `apply_safe_interval_stop.sh` — backs up all 3 touched files, applies, compile-checks,
  smoke-imports, copies the test file to `tests/`, runs it plus `test_loop_utils.py` +
  `test_agent_session.py` (the two suites most likely to catch a regression in the budget checks).

## Tests (20/20 passing pre-apply)

`tests/test_patcher.py` — the loop.py/agent_session.py patches apply cleanly against the CURRENT
live files, are idempotent, fail loudly (not silently) if an anchor has moved, and the patched
result still compiles. `tests/test_safe_interval_stop.py` — `effective_wall_limit` math, config
margin flooring, `interval_boundary_reached` fires at the margined boundary (never for a non-active
session), `stop_at_safe_point` always produces a real checkpoint, and — the core safety guarantee —
`resume_work_interval` refuses without approval, refuses even after a simulated 3-day gap with no
approval call, and only succeeds via explicit `approved=True` or a real `interrupts.request_resume()`
call.

Reversible: restore the 3 backed-up files, `rm src/sovereign_agent/work_interval.py`.
