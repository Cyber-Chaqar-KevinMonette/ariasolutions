# aria-model-corps-governance — standing model-roster governance (Model Corps round · MC3-MC6)

> Closes `GOD_TIER_CRITERIA.md`'s own named gaps #2 ("standing scored model
> benchmark") and #3 ("small-model response-quality tuning"). Propose-only /
> reversible / staged.

## Payload

- `src/sovereign_agent/model_corps_governance/registry.py` (MC3) — the
  declared roster (role → base tag → license → approx VRAM) plus a persisted
  NDJSON ledger (`record_registry_snapshot()`/`latest_registry()`), mirrors
  `quality/ledger.py`'s exact discipline.
- `src/sovereign_agent/stewardship/model_corps_sentinel.py` (MC4) —
  `ModelCorpsSentinel`: license allow-list check (Apache-2.0/MIT/BSD-3-Clause
  only — would have caught every model in the pre-round roster), drift
  check (`ollama list` vs. the registry), VRAM budget check (reuses
  `vram.py`'s own `TOTAL_VRAM_MB`/`SAFETY_FLOOR_MB`, not a second invented
  budget).
- `src/sovereign_agent/model_corps_governance/gate.py` (MC5) — a small
  (2 cases × 6 roles = 12), hand-written, mechanically-scored eval — no LLM
  judge — persisted as a trend; `gate()` BLOCKs a future model swap that
  scores below floor or regresses versus the previous pass.
- `src/sovereign_agent/model_corps_governance/nonclassical_confidence.py`
  (MC6) — the honest answer to "can weights be made non-classical, emulated
  or simulated if needed": literal quantum weights aren't physically
  possible at this scale, but `nonclassical_supreme.superpose` already IS a
  real, working quantum-faithful simulation (Bloch phase, Born-rule
  collapse, Grover-like interference, CPU-only). This module composes that
  EXISTING engine as an optional extra confidence signal over multiple
  candidate strings — an extension seam, nothing currently calls it.

## Verify / Apply
```bash
./scripts/verify_module.sh aria-model-corps-governance     # before apply
./aria-model-corps-governance/apply_model_corps_governance.sh                 # cockpit stopped
```

Applying seeds both ledgers for real: one registry snapshot, and one live
eval pass that actually calls all 6 `aria-<role>` models over Ollama
(~1-3 minutes) — so `latest_registry()`/`latest_eval()`/`gate()` are never
empty on first look after apply.
