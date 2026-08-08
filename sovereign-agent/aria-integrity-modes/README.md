# aria-integrity-modes — the "honest" stance (Integrity round · I4)

> The fifth stance with a real tooth: entering it runs a real integrity
> pass; new goal dispatch is gated until it clears. Propose-only /
> reversible / staged.

## Payload (in-place patches only — no new files this round)

- `modes_crown/stances.py` — `"honest"` added to `SAFE_STANCES`;
  `_run_integrity_pass_for_stance()` (reuses `_recent_text_for_stance`,
  grounding-modes-d's own on-demand journal+QA sourcing — composed, not
  duplicated); `integrity_gate_clear()` mirrors `quality_gate_clear`/
  `grounding_gate_clear`/`wellbeing_gate_clear` exactly.
- `session_bridge.py`'s `_crown_gate()` — a fifth block, same shape as the
  four already there.
- `modes_crown/observatory.py` — an `integrity` field beside
  `quality`/`grounding`/`wellbeing`.

## Verify / Apply
```bash
./scripts/verify_module.sh aria-integrity-modes     # before apply
./aria-integrity-modes/apply_integrity.sh                 # cockpit stopped
```
