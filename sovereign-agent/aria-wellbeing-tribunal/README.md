# aria-wellbeing-tribunal — standing audit + measured angel lens (Wellbeing round · W3)

> Almost entirely composition + one small measured-data patch — the
> Tribunal and Advocate Spectrum were already rich; they were just never
> STANDING for wellbeing, and the angel lens only ever saw one live text
> sample instead of W1's persisted composite.

## Measured data over prose heuristics

`spectrum/lenses.py`'s `angel()` lens scored "worth protecting" from a
single live `tribunal.angel.advocate()` call. When the proposal now
carries real measured data (`love_grade` / `flourishing_verdict`, from
W1's persisted composite), that overrides the live-only check — measured
beats one-shot. Absent those keys, byte-identical fallback; every
existing bare-string or plain-dict caller is unaffected.

## Standing, not one-shot

`WellbeingSentinel`'s marked extension seam (left there deliberately in
W1) gets a second scan phase: convene **both** Tribunal and Advocate
Spectrum over the sentinel's own just-computed wellbeing pass, logged
through `log_to_diagnosis()` (its `prefix` parameter already made generic
by Grounding round's G3) into the same `diagnosis.ConflictCatalog`, under
`prefix="WELL"`. The standing counterpart to `TribunalSentinel`, which
only re-checks a hardcoded safety string — this one audits her own real
recent value/care/flourishing signal. Best-effort: a scrutiny failure
here never breaks the wellbeing scan.

## Verify / Apply

```bash
./scripts/verify_module.sh aria-wellbeing-tribunal
./scripts/safe_apply.sh aria-wellbeing-tribunal
```
