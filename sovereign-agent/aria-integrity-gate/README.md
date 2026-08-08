# aria-integrity-gate — the standing gate (Integrity round · I2)

> A live, one-shot check over given text — distinct from I1's persisted
> ledger, mirrors `grounding.gate()` exactly. Propose-only / reversible /
> staged.

## Payload

- `src/sovereign_agent/integrity/gate.py` — `gate(text, claimed_confidence=
  None, predicted_impact=None, actual_impact=None, data_dir=None)`: runs
  I1's four signal-scorers LIVE (never writing to the ledger — that's the
  standing sentinel's job in I3), renders a worst-of PASS/WARN/BLOCK
  verdict. Kill switch `SOV_NO_INTEGRITY_GATE=1`.
- `scripts/lib/integrity_gate.py` — the CLI wrapper `pre_apply_gate.sh`
  calls, same shape as `quality_gate.py`/`grounding_gate.py`.

## Wiring

`scripts/pre_apply_gate.sh` gains a fourth check (after scrutiny, quality,
grounding), worst-wins the same exit code every check already ORs
together.

## Verify / Apply
```bash
./scripts/verify_module.sh aria-integrity-gate     # before apply
./aria-integrity-gate/apply_integrity.sh                 # cockpit stopped
```
