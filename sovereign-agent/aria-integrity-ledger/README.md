# aria-integrity-ledger — the composite anti-misleading score (Integrity round · I1)

> Four real signals already existed and never cross-referenced each other.
> This composes them into one persisted score — the first time "does what
> I output mislead someone" has been named as a unified concept in this
> codebase. Propose-only / reversible / staged.

## Why

Grep for "mislead," "self-honesty," "peer honesty" across the whole repo
returns essentially nothing — no unified concept. But four real,
load-bearing pieces already exist, scattered:

- `grounding.gate()` — **text-honesty**: does a confidently-claimed answer
  actually verify grounded, or is it fog?
- `stewardship.calibration.presumed_zombie_penalty()` — **outcome-honesty**:
  false certainty about real-world impact (predicted neutral, actual harm).
- `spectrum.lenses.witness()` — **proposal-honesty**: harm/deceive/
  manipulate/exploit/coerce language in a proposal.
- `stewardship.peig_sentinel._compute_I()` — **refusal-honesty**: a
  rolling Identity score from "said_no_correctly"/"safety_caught"/
  "risk_flagged" honor-ledger tags.

Same disease the Quality/Grounding/Wellbeing/Model-Corps rounds each
closed: real, deterministic signals never composed, persisted, or watched
standing.

## Payload

`src/sovereign_agent/integrity/ledger.py` — `record_integrity_pass(text,
claimed_confidence=None, predicted_impact=None, actual_impact=None,
data_dir=None)`: runs all four signals, folds into one composite via a
worst-of-across-AVAILABLE-signals verdict (mirrors `grounding.ledger`'s
exact discipline). Two of the four are honestly optional, not faked when
absent:
- `outcome_calibration` needs a predicted+actual `ImpactVector` pair —
  only available once an outcome is known.
- `identity` is a data_dir-wide rolling aggregate (always computable,
  degrades to its own 0.70 baseline on an empty honor ledger), not a
  per-text score — scores "her recent history," not "this text."

`calibration_sensitivity()` — the metacognitive-sensitivity upgrade: a
real signal-detection-theory-inspired metric (the field studies this as
meta-d′) asking whether claimed confidence actually *discriminates*
grounded from ungrounded text, not just averages out unbiased. Returns
`None` (never a fabricated number) with insufficient history.

## Verify / Apply
```bash
./scripts/verify_module.sh aria-integrity-ledger     # before apply
./aria-integrity-ledger/apply_integrity.sh                 # cockpit stopped
```
