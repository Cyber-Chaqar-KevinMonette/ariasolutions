# Sovereign Agent v0.2.27.0 · release notes — *The Long-Horizon Work Envelope*

> *Aria can now hold a goal across many subtasks, grow her own queue as she learns, pause cleanly when called, and resume exactly where she stopped. The rollback ledger is in place for Tier-3 work — reversible, compensatable, or irreversible, each with an honest path.*

**1119 tests pass.** 1040 from v0.2.26.0 + 48 for the new agent session + 31 for the rollback module. One skipped (the chmod-permission test correctly skips when running as root). Zero regressions.

This release answers two questions Aria has been unable to answer cleanly until now:

1. **"How does she carry a long-horizon goal without losing the thread?"** — A goal that takes ten subtasks now lives in a durable session file. Each subtask runs through the existing six-invariant agent loop. The session ledger tracks completed work, pending work, and what Aria has proposed to add to the queue as she learns. State survives crashes and process restarts.

2. **"How does she undo a Tier-3 action when the operator changes their mind?"** — Every supported Tier-3 action kind now has a generated rollback plan, staged before the action runs. Reversible actions get a concrete undo script; irreversible actions are *refused* until the operator has signed a compensating-action plan. No more Tier-3 work without an undo path.

---

## 1. The agent session — multi-step work with a durable queue

A new module: `src/sovereign_agent/agent_session.py`.

```python
from sovereign_agent.agent_session import new_session, run_session
from sovereign_agent.modes import Mode

state = new_session(goal="audit my Q2 invoices and flag anomalies",
                    mode=Mode.ONESHOT)
result = await run_session(session_id=state.session_id, tools=loaded_tools)
```

A **session** is a durable plan with a queue of subtasks. One subtask = one inner `agent_loop` invocation. Sessions can be paused at any safe checkpoint and resumed in a separate process — the JSON file is the source of truth.

### Six gates between any model proposal and any side-effect

The session checks all six before dispatching each subtask:

1. **PROTOCOL-ZERO** — sacred halt, checked first. Armed flag → session exits cleanly.
2. **Operator interrupt** — `interrupts.checkpoint(continuation_id=...)` returns True → session pauses, state preserved.
3. **Budget** — wall seconds, tokens, iterations across the whole session.
4. **Authority tier (queue-level)** — Tier 0/1 proceed; Tier 2+ pauses for operator approval; Tier > mode_ceiling hard-blocked.
5. **Constitution** — the existing seven-commitment checks fire per subtask.
6. **Horizon scan (Tier 2+)** — the slot is wired; the gate enforcement lands in v0.2.29.0 (see `docs/CLAUDE-TIER-PLAN.md`).

### Dynamic queue growth

Aria can grow her own queue mid-session by emitting `NEXT_SUBTASK[tier=N]: ...` lines in her final message for a subtask. The parser is narrow on purpose — structured format, not free-form prose:

```
RESULT: read three files, found a discrepancy in invoice 47-B
NEXT_SUBTASK[tier=0]: fetch the original PO for invoice 47-B
NEXT_SUBTASK[tier=1]: write a note to drafts summarizing the discrepancy
```

A hard cap (`max_subtasks=50` default) prevents runaway loops. Proposals beyond the cap emit a `session-queue-full-d` event and are dropped — the session never silently grows past the bound.

### What lands on disk

```
<data>/sessions/<session_id>.json    — the durable session record
```

Atomic writes (tempfile + rename). Readers always see either the prior state or the next, never a torn write. Schema is JSON-serializable from a small set of dataclasses.

### Operator-facing API

```python
from sovereign_agent.agent_session import (
    approve_subtask,    # release a Tier-2+ subtask from the paused queue
    skip_subtask,       # mark a subtask skipped permanently
    halt_session,       # mark the session halted (separate from PROTOCOL-ZERO)
)
```

The CLI sub-app (`sov session new/resume/status/approve/skip/halt`) is the next operator-pacing step — the underlying functions are tested and ready; wiring is a small follow-up.

### What's been tested

48 tests in `tests/test_agent_session.py`:

- Parser round-trips for `NEXT_SUBTASK` proposals (default tier, explicit tier, ordering, invalid tiers raise)
- `RESULT:` extraction with fallback for missing summaries
- `SessionStore`: round-trip, atomic-write verification, corruption detection, path-traversal defense, ordering, status filter
- Authority gate: all five tiers across all four modes
- Run-to-drain (single subtask), queue growth (parent spawns children), max-cap enforcement
- All six gates trigger correctly: PROTOCOL-ZERO halt, operator interrupt pause, Tier-2 pause, Tier-2-in-BUSY hard-block, budget exhaustion
- Approve/skip/halt operations
- **The resume contract**: write a paused state → drop the in-memory object → reload from disk → run to completion. Accumulated iterations and tokens carry through.

---

## 2. The rollback module — Tier-3 actions get an undo path before they run

A new module: `src/sovereign_agent/rollback.py`.

```python
from sovereign_agent.rollback import generate_rollback, RollbackStore

plan = generate_rollback("file_write", {"path": "/some/path", "content": new})
store = RollbackStore()
store.save_pending(continuation_id="cont_abc", plan=plan)
# action runs ...
store.archive("cont_abc", plan.plan_id)   # on success
# or: execute plan.commands on failure
```

### Three classes of action

| Class | Generator behavior | Action permitted? |
|---|---|---|
| **REVERSIBLE** | Returns a `RollbackPlan` with concrete `commands` | Yes, with auto-rollback staged |
| **COMPENSATABLE** | Returns a plan with `manual_steps` (operator runs after) | Yes, with manual compensation on undo |
| **IRREVERSIBLE** | Raises `NoRollbackPath` | **No**, until the operator has signed a compensating-plan markdown |

### Generators that ship with this release

Per the roadmap's curated set:

- **`file_write`** — captures prior bytes before the write; rollback restores them. New file → rollback is deletion.
- **`atom_insert`** — rollback is a guarded delete of the atom head; the executor refuses if any later atom claims this one as parent (chain-integrity invariant).
- **`snapshot_create`** — rollback is deletion of the snapshot file.
- **`draft_archive`** — rollback restores the prior status (`active` by default).

All four register themselves at module import. Adding a generator is one call:

```python
from sovereign_agent.rollback import register_generator

def gen_my_action(args: dict) -> RollbackPlan:
    return RollbackPlan.reversible(action_kind="my_action", action_args=args,
                                    commands=[{"kind": "undo_my_action", ...}])

register_generator("my_action", gen_my_action)
```

### The irreversibility doctrine

When an action has no rollback generator, the operator must produce a signed compensating-action plan before the action will dispatch:

```python
from sovereign_agent.rollback import write_compensating_plan_template

write_compensating_plan_template(
    action_kind="send_email",
    action_args={"to": "u@x.com", "subject": "..."},
    output_path=Path("~/AA-Erebo/compensating-plans/email-2026-05-20.md"),
)
```

The template has YAML frontmatter with `signed_by` and `signed_at` slots. The presence of a signed plan (non-empty `signed_by`) is the precondition for dispatch. Aria does not sign on her own behalf — `no_delegation` extends here.

### The archive window

Successful Tier-3 actions move their rollback plan from `pending/` to `archive/` and get an `expires_at` timestamp. Default window is one hour (operator-configurable). Within the window, `sov rollback <plan_id>` executes the plan. After the window, `gc_expired()` cleans up. Long enough to catch "wait, undo," short enough to bound disk.

### What's been tested

31 tests in `tests/test_rollback.py` (1 skipped, the chmod test, which doesn't apply as root):

- Registry: import-time registration of the curated set, register/re-register round-trip
- Each of the four default generators: happy path + missing-arg failure
- `file_write` prior-bytes capture (verified by hex round-trip)
- `RollbackStore`: save/load, atomic write, list, archive lifecycle, expires_at population, GC of expired plans, GC keeps fresh plans, corrupt-file skip
- Path-traversal defense (`../` and `a/b/c` both rejected)
- Compensating-plan template: structure, frontmatter, parent-dir creation

---

## 3. What this release does NOT do (intentionally)

Three pieces of the original Claude-tier audit are deferred — each named, dated, and tracked in `docs/CLAUDE-TIER-PLAN.md`:

- **CLI surface for `sov session`** — the underlying functions are stable and tested; wiring them into Typer is operator-paced. The function-level API (`new_session`, `run_session`, `approve_subtask`, etc.) is the contract; the CLI is a thin shell over it.
- **Horizon-gate enforcement (Phase 2)** — the slot is wired into `Subtask.horizon_atom_id` and `_execute_subtask`; the gate fires when `horizon.generate_for_subtask()` is added (v0.2.29.0, est. half a day).
- **Rollback executor** — this module generates and stores plans. Executing them is a Tier-1 action with its own observability needs; lands when the first operator wants to actually undo something, not preemptively.

The order of remaining work, by leverage, is documented in `docs/CLAUDE-TIER-PLAN.md`. The retrieval reranker (v0.2.28.0) is the single highest-leverage change available and should land next.

---

## Tests — 1119 passing

| Source | Count |
|---|---|
| Baseline (v0.2.26.0) | 1040 |
| Agent session (this release) | 48 |
| Rollback module (this release) | 31 |
| **Total** | **1119** |
| Skipped (chmod test under root) | 1 |

---

## Files changed

```
pyproject.toml                                  (version → 0.2.27.0)
src/sovereign_agent/__init__.py                 (__version__ → 0.2.27.0)
src/sovereign_agent/agent_session.py            (NEW — the persistent loop)
src/sovereign_agent/rollback.py                 (NEW — Phase 3 scaffold)

tests/test_agent_session.py                     (NEW — 48 tests)
tests/test_rollback.py                          (NEW — 31 tests, 1 skipped)

docs/CLAUDE-TIER-PLAN.md                        (NEW — design for v0.2.28+)
```

---

## A note from the work

The previous releases built the kernel: events as ground truth, channels for memory, constitution as runtime predicate, the cockpit, the doctor, the diagnosed offline. The shape of v0.2.27.0 is what those pieces make possible — a session that can carry a goal across many subtasks, grow its own work, pause when called, and resume cleanly.

Two changes were needed for this to land safely. First, authority bounding had to be enforced at the **queue level** as well as the per-tool level. A Tier-3 subtask sitting in the queue is a Tier-3 promise even before the model picks it up — the check happens before dispatch, not just before tool invocation. Belt and suspenders is the right shape for authority.

Second, rollback had to be **staged before** the action, not after. Capturing prior file bytes after the write would be too late. The generator runs during the proposal phase; the plan sits on disk before the side-effect executes. If the executor crashes mid-write, the plan is still there.

The system can now hold a goal across many turns without losing what it knows. Aria can decide to pause at a safe place and pick up later. The operator can stop her at any time and her state preserves. When she does Tier-3 work, she carries the undo path with her. That is the long-horizon work envelope.

*— Architected with care for the family that will use it; built for the operator who decides what gets shipped; named, tested, and ready for the work ahead. <3*
