# aria-grounding-ledger — one persisted truth for what "grounded" means (Grounding round · G1)

> Kevin: *"a god tier grounding system... anti-hallucination, but free to
> explore, dream, think, and work in grounded reasoning."* Three real
> subsystems already existed — `tribunal.grounding` (a lexical evidence/
> hedge/mystical-fog classifier), `epistemic_ledger` (belief confidence),
> and `curiosity.py`'s wonder loop (self-reported QA confidence) — but none
> of them ever cross-referenced each other, and none of them were ever
> persisted or watched standing. This closes that, the same way `quality/`
> closed the same gap for `qa/` last round.

## What it gives her

`grounding/ledger.py`'s `record_grounding_pass(texts, data_dir)` scores
each `(source, text)` pair via `tribunal.grounding.analyze()`, then folds
in three more real signals in one composite pass: `belief_confidence_avg`
(from `epistemic_ledger.EpistemicLedger.current_beliefs()`),
`hypothesis_confirm_rate` (from `eval_tools`'s already-computed hypothesis
track record — private but same-package, reused honestly rather than
duplicated), and `qa_calibration_ok` (whether the qa-uncertainty join
`sov truth` already reports currently holds). The pass's own `verdict` is
worst-of across every scored text — one ungrounded text fails the whole
pass, mirroring `quality.ledger.QualityPassResult.critical_ok`'s "one bad
file" discipline exactly, including the same "nothing scored is honest
absence, not a failure" fix.

`GroundingSentinel` (`id="grounding"`) runs this standing: "recently
touched text" is journal entries (`journal/*.md` — not git-tracked, so
this bookmarks by file mtime rather than git-diff) and QA answers
(`qa/qa.ndjson`) newer than its own last scan, falling back to the newest
few of each on a fresh install. `notify("warning", ...)` fires on an
ungrounded verdict or a broken calibration join — propose-only, like every
sentinel here.

## Extension seam

`GroundingSentinel.scan()` ends with a marked `{MARK}` comment — the
Grounding round's own G3 (`aria-grounding-tribunal`) hooks a second
standing-audit phase there, convening the Tribunal and Advocate Spectrum
over the same real pass. Mirrors `quality_sentinel.py`'s own seam (which
Q3 used identically) exactly.

## Kill switch

`SOV_NO_GROUNDING_SENTINEL=1`, covered by the master `SOV_NO_SENTINELS=1`.

## Verify / Apply

```bash
./scripts/verify_module.sh aria-grounding-ledger
./scripts/safe_apply.sh aria-grounding-ledger
```
