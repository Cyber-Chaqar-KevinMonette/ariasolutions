# aria-grounding-gate — the calibration check (Grounding round · G2)

> The sharpest concrete anti-hallucination lever in this round: today
> `curiosity.py`'s wonder loop trusts the model's SELF-REPORTED confidence
> with nothing checking it against the answer's own grounding texture. A
> model could claim confidence 0.9 while writing pure mystical-fog prose
> and nothing catches the mismatch.

## What it gives her

`grounding/gate.py`'s `gate(text, claimed_confidence=...)` renders a real
PASS/WARN/BLOCK verdict: BLOCK when the text's own verdict is
`"ungrounded"`, OR when a confidently-claimed answer (≥ 0.6) doesn't
actually verify as `"grounded"` — the calibration mismatch. WARN on
`"mixed"` with no mismatch. PASS otherwise, including an honest PASS on
empty input (mirrors `quality.gate`'s exact "nothing to check" discipline).

Wired into `curiosity.py:wonder()`: right after the answer is built and
before it's recorded, a calibration mismatch clamps `rec.confidence` below
`LOW_CONFIDENCE` — so an overclaiming answer can no longer silently skip
the wonder loop's own safety net. The existing `if rec.confidence <
LOW_CONFIDENCE:` branch (which auto-opens a `curiosity`-domain
`Uncertainty`) then fires exactly as it was originally designed to,
now honestly. A genuinely grounded, honestly-confident answer is
byte-identical to today — the gate only acts on a real mismatch.

Also wired into `scripts/pre_apply_gate.sh` as a third check, alongside
`scrutiny.py` and (Quality round's) `quality_gate.py`: a staged module's
own README prose must hold up too, worst-wins the same exit-code idiom.

## Kill switch

`SOV_NO_GROUNDING_GATE=1` — degrades to PASS with a note, never silently
BLOCKs while claiming to have checked something it didn't.

## Verify / Apply

```bash
./scripts/verify_module.sh aria-grounding-gate
./scripts/safe_apply.sh aria-grounding-gate
```
