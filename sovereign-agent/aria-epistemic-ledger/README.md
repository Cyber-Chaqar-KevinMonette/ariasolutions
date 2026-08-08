# aria-epistemic-ledger — the Epistemic organ (Workstream H3)

> Her honest self-knowledge instrument: what she currently believes, with what confidence,
> traceable to evidence, plus an explicit registry of known-unknowns. Not a new memory system — she
> already has atoms/palace/calibration-adjacent pieces. A thin ledger that *references* existing
> evidence (atom ids, ledger rows, file paths) rather than duplicating storage.

## What it does

Two append-only NDJSON stores, atomic-write (mirrors `ApplyQueueStore`'s exact idiom from
Workstream C):

- **`EpistemicLedger`** — `Belief` records (`claim`, `confidence`, `evidence_refs`). `revise()`
  **never mutates history** (palimpsest discipline, per the canon) — it appends a NEW belief with
  `revised_from` pointing at the old one. The old belief stays readable forever via `all_beliefs()`;
  `current_beliefs()` surfaces only the tip of each lineage; `lineage(id)` walks a belief's full
  revision chain, oldest first.
- **`UncertaintyRegistry`** — `{domain, question, why_unknown}` entries. `open()` records a new
  known-unknown; `close()` appends a resolved copy (the open event is never deleted, just superseded
  in `list_open()`'s view — `list_all()` still shows both).

## Payload
- `src/sovereign_agent/epistemic_ledger/ledger.py` — `Belief`, `EpistemicLedger`, `Uncertainty`,
  `UncertaintyRegistry`.

## Use
```python
from sovereign_agent.epistemic_ledger import EpistemicLedger, UncertaintyRegistry

ledger = EpistemicLedger()  # defaults to <data_dir>/epistemic/
belief = ledger.record("the fix closed the anchor gap", 0.9, evidence_refs=["commit:16baa1d"])
ledger.revise(belief.belief_id, "the fix closed most of the anchor gap, 2 remain",
               "J's scanner found 2 more dangling anchors", confidence=0.95)

registry = UncertaintyRegistry()
u = registry.open("regression-debt", "why did aria-workout's test fail",
                   "not yet root-caused")
registry.close(u.uncertainty_id, "ListCockpitCommandsTool output format changed")
```

## Verify / Apply
```bash
./scripts/verify_module.sh aria-epistemic-ledger   # before apply (read-only)
./aria-epistemic-ledger/apply_epistemic_ledger.sh  # cockpit stopped
```
