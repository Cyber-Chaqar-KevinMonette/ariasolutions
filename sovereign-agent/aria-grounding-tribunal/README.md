# aria-grounding-tribunal — standing audit + measured skeptic lens (Grounding round · G3)

> Kevin: *"how to be a scientist, and when to be genuinely grounded."*
> Almost entirely composition + one small additive API change — the
> Tribunal and Advocate Spectrum were already rich; they were just never
> STANDING for grounding, and the skeptic lens only ever saw one live text
> sample instead of G1's richer persisted composite.

## A small additive API change

`tribunal.log_to_diagnosis()` gains an optional `prefix` parameter
(default `"TRIB"`, every existing caller unchanged) so a standing
grounding case can log under `"GRND"` instead — distinguishing origin in
the case-ID namespace without adding a new `diagnosis.CONFLICT_TYPES`
member (same `"ambiguity"` type either way, per the convention
`tribunal.py` already documents for the Quality round's own `TRIB` cases).

## Measured data over prose heuristics

`spectrum/lenses.py`'s `skeptic()` lens scored grounding from a single
live `tribunal.grounding.analyze()` call. When the proposal now carries
real measured data (`grounding_verdict` / `epistemic_score` /
`qa_calibration_ok`, from G1's persisted composite — richer than one
sample, since it also folds in belief confidence and hypothesis track
record), that overrides the live-only check — measured beats one-shot.
Absent those keys, byte-identical fallback; every existing bare-string or
plain-dict caller is unaffected.

## Standing, not one-shot

`GroundingSentinel`'s marked extension seam (left there deliberately in
G1) gets a second scan phase: convene **both** Tribunal and Advocate
Spectrum over the sentinel's own just-computed grounding pass, logged
through the now-prefix-aware `log_to_diagnosis()` into the same
`diagnosis.ConflictCatalog` Tribunal already uses, under `prefix="GRND"`.
The standing counterpart to `TribunalSentinel`, which only re-checks a
hardcoded safety string — this one audits her own real recent writing.
Best-effort: a scrutiny failure here never breaks the grounding scan.

## Verify / Apply

```bash
./scripts/verify_module.sh aria-grounding-tribunal
./scripts/safe_apply.sh aria-grounding-tribunal
```
