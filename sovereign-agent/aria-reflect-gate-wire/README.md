# aria-reflect-gate-wire — wire the tribunal's Ring-2 EXPAI gate to the reflector

## What this gives Aria

`tribunal.gate_ring2_improvement()` is fully built and already wired to the Tribunal and the
`improvement_gov` evidence ledger, but it has zero callers — PLAYBOOK.md advertises an "evidence-gated
change log" as if it fires automatically, and it doesn't. `reflector.py` captures a durable lesson on
every `settle-d`/`poison-d` event but never routes anything through that gate.

This module wires exactly one trigger to that one existing gate: a lesson captured with confidence
above 0.8 (the same threshold the `mos-lesson-capture` doctrine clause already uses to distinguish
provisional from enforceable) gets proposed through the tribunal + EXPAI evidence gate.

## Why it is safe

- **Propose-only.** `gate_ring2_improvement` never edits code or values — it appends one promote/dismiss
  decision to `improvement_ledger.ndjson`, an append-only, human-reviewed transparency log.
- **Reversible by construction.** The thing being gated is a `lessons`-table row (trigger/context/
  correction/rule/confidence). Deleting or superseding it has zero blast radius on running code, tool
  tiers, or authority — it is data, not code, so `reversible=True` in the proposal is honest, not gamed.
- **Bounded scope.** One call site, in one function, guarded by one confidence threshold. No new
  autonomous behavior — the gate's own verdict still decides promote vs. dismiss, and a human still
  reads the ledger.
- **Rollback is trivial.** The patched `reflector.py` / `tests/test_reflector.py` are byte-for-byte
  restorable from the timestamped `.bak` files the apply script writes before touching either file, and
  `safe_apply.sh`'s own git-snapshot rollback covers this module like any other.
- **No lock-in, no value drift.** This does not touch `mos_canon.py`'s `DEFERRED_UNSAFE` catalog, does
  not raise any tool's authority tier, and does not change what counts as safe — it only connects an
  existing, already-approved gate to an existing, already-approved event.

## Payload

No new files — this is a patch-only wire. `apply_reflect_gate_wire.sh` idempotently patches two live
files (backing each up first):

- `src/sovereign_agent/reflector.py` — import `gate_ring2_improvement`, add the
  `_gate_high_confidence_lesson()` helper, call it from `reflect()`'s success path when
  `lesson.confidence > 0.8`.
- `tests/test_reflector.py` — three tests: gate fires above threshold, gate does not fire below
  threshold, a gate failure never fails lesson capture.

## Verify

```bash
./scripts/verify_module.sh aria-reflect-gate-wire
./scripts/pre_apply_gate.sh aria-reflect-gate-wire
./scripts/safe_apply.sh aria-reflect-gate-wire
.venv/bin/python -m pytest tests/test_reflector.py -v
```
