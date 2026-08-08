# aria-scope-contract

Keys round K10 — Kevin: *"hardening her ability to scope — in her work, in
her research, and anywhere else it can matter most; part of her persistence
and horizon abilities"* — and for her designing/architecting (K8's workflow
drafts carry these contracts too).

## The framing that makes it hers

Her stewardship already lives by Plan/Witness/Impact — prediction before,
observation during, reality after. A **ScopeContract is that same
discipline applied to the BOUNDARY of work**: she writes down what DONE
means and what she will NOT touch *before* starting, so completion is
checkable and drift is visible — never discovered after the fact.

## What ships

- **`scope.py`**: `ScopeContract` {goal, in_scope, out_of_scope,
  done_when, max_subtasks}; `/work fix the parser | scope: only
  src/parser; out: tests, docs; done: parse errors gone; max: 8` — the
  operator grammar; persisted beside the session file
  (`sessions/<sid>.scope.json` — her persistence, resumed sessions re-read
  their own contract). The v1 in/out check is a transparent keyword
  heuristic — honest and predictable for an 8B vessel.
- **The teeth, at the exact door scope creep enters**: NEXT_SUBTASK
  queue-extension proposals tripping the out list are held BLOCKED with a
  scope-review note (+ `scope-review-d` event) instead of silently
  joining the queue. Crossing 80% of `max_subtasks` fires a one-time
  `scope-drift-d` — drift visible long before the budget wall stops
  things bluntly.
- **She self-polices**: the contract rides in the session guidance
  preamble, in her own written words.
- **Observable**: both scope events render richly (K1's run surface).
- **Backward compatible**: no contract declared = exactly today's
  behavior (tested).

## Verify / Apply

```
.venv/bin/python -m pytest aria-scope-contract/tests/test_patcher.py -q
./aria-scope-contract/apply_scope_contract.sh
```

Reversible: restore the 3 files from the timestamped `backups/` dir and
remove `scope.py` (orphan `.scope.json` files are inert).
