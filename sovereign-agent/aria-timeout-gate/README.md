# aria-timeout-gate — the standing gate (Timeout round · T2)

> A live check over recent events — distinct from T1's persisted ledger,
> mirrors `grounding.gate()`/`integrity.gate()` exactly. BLOCKs on a
> genuine recurring hang (3+ unexplained timeouts for the same tool), not
> one slow call. Propose-only / reversible / staged.

## Payload

- `src/sovereign_agent/timeouts/gate.py` — `gate(data_dir=None)`: reuses
  T1's own classification helpers LIVE (never writing to the ledger —
  that's the standing sentinel's job in T3). Kill switch
  `SOV_NO_TIMEOUT_GATE=1`.
- `scripts/lib/timeout_gate.py` — the CLI wrapper `pre_apply_gate.sh`
  calls. Unlike the other gate CLIs, this one takes no `--module`/`--file`
  target — it checks the shared event log directly, the same check every
  apply shares.

## Wiring

`scripts/pre_apply_gate.sh` gains a fifth check (after scrutiny, quality,
grounding, integrity), worst-wins the same exit code every check already
ORs together.

## Verify / Apply
```bash
./scripts/verify_module.sh aria-timeout-gate     # before apply
./aria-timeout-gate/apply_timeouts.sh                 # cockpit stopped
```
