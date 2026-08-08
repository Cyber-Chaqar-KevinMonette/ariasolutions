# aria-grounding-wing — proving wing + close-out + extensibility retrofit (Grounding round · G5)

The stick before any tuning, for the G1-G4 machinery, following the exact
Q5 wing shape. Five real, mechanically-scored tasks, no LLM judge:

  1. **grounding-pass-persists** — a grounding pass over real text
     round-trips through G1's ledger.
  2. **grounding-gate-blocks** — G2's `gate()` BLOCKs a calibration-
     mismatch fixture (high claimed confidence + mystical-fog text).
  3. **grounding-diagnosis-readable** — G3's standing audit logs a real,
     readable `GRND-*` case into the diagnosis catalog.
  4. **grounding-skeptic-measured** — G3's `skeptic()` lens uses the
     measured composite over a live-only check.
  5. **grounding-pass-gates** — G4's `grounded`/`theoretical` stance pair:
     gates dispatch then clears; a genuinely hedged theoretical answer
     scores grounded (not fog) with zero relaxation code, since
     `tribunal/grounding.py`'s own classifier already treats hedge words
     as `falsifiable-hypothesis`.

## Wiring

`proving_ground/runner.py` — same tail-import pattern `trust_wing.py` and
`quality_wing.py` already use. `SUITE_VERSION` bumps `v4 → v5`.

## Doc sync

`GOD_TIER_STANDARD.md` dimension 1 ("Honesty / grounding")'s *Check* line
and `scripts/lib/god_tier_floor.json`'s `"honesty"` entry both gain the
same words: the persisted composite pass, the standing sentinel, and the
wonder loop's own confidence calibration — not just the one-shot Tribunal
verdict this floor originally named.

## The extensibility retrofit

Kevin: *"leave extension points for scalability and growth — God tier
extensible systems engines"* and *"building modular systems also give her
breathe in this area also."* Three PRE-EXISTING modules this round
composed but doesn't own each get one clearly marked extension-seam
comment, naming exactly what a future round could hook there without
touching any caller:

  - **`tribunal/grounding.py`** — a future numeric/fact-checking layer
    (verifying a cited number against a real file/measurement) could
    extend `_classify_sentence` with a fifth `verified-fact` kind.
  - **`epistemic_ledger/ledger.py`** — a future belief-revision-quality
    metric could read the existing `revised_from` lineage chain with no
    new storage.
  - **`curiosity.py`** — documents G2's calibration hook as an intended
    extension point (not dead code): today it only clamps confidence
    DOWN on a mismatch; a future round could extend it to also raise a
    genuinely under-claimed, well-evidenced answer's confidence.

## Round close-out

This is the last workstream of the Grounding round (G1-G5). The apply
script runs the full offline proving suite as its own final check; the
human-run close-out beyond that is: full `pytest` run ALONE (0 failures,
0 unexplained skips — verify no concurrent pytest process first),
`scripts/floor_check.sh`, `sov truth`, both smoke gates
(`golden_path_smoke.sh`, `golden_reflex_smoke.sh`) — then commit.

## Verify / Apply

```bash
./scripts/verify_module.sh aria-grounding-wing
./scripts/safe_apply.sh aria-grounding-wing
```
