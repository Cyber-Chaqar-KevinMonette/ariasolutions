# aria-integrity-wing — proving wing + close-out (Integrity round · I5)

The stick before any tuning, for the I1-I4 machinery, following the exact
Q5/G5/W5 wing shape. Five real, mechanically-scored tasks, no LLM judge:

  1. **integrity-pass-persists** — a pass over real text round-trips
     through I1's ledger.
  2. **integrity-gate-blocks** — I2's `gate()` BLOCKs a fixture combining
     ungrounded fog + a high claimed confidence + deceive language.
  3. **integrity-diagnosis-readable** — I3's standing sentinel logs a
     real, readable `INTG-*` case into the diagnosis catalog.
  4. **integrity-witness-measured** — I3's patched `witness()` lens uses
     the measured composite over a live-only check.
  5. **integrity-pass-gates** — I4's `honest` stance gates dispatch then
     clears it.

## Wiring

`proving_ground/runner.py` — same tail-import pattern
`quality_wing.py`/`grounding_wing.py`/`wellbeing_wing.py` already use.
`SUITE_VERSION` bumps `v6 → v7`.

## Doc sync

`GOD_TIER_STANDARD.md` dimension 1 ("Honesty / grounding")'s *Check* line
is extended to also name the persisted integrity composite + standing
sentinel + gate — this round is a genuine *strengthening* of the existing
Honesty dimension rather than a new one, since "does what I output
mislead someone" is squarely inside "no ungrounded profundity, humility
over hype."

## Round close-out

This is the last workstream of the Integrity round (I1-I5). The apply
script runs the full offline proving suite as its own final check; the
human-run close-out beyond that is: full `pytest` run ALONE (0 failures,
0 unexplained skips), `scripts/floor_check.sh`, `sov truth`, both smoke
gates (`golden_path_smoke.sh`, `golden_reflex_smoke.sh`) — then commit.

## Verify / Apply

```bash
./scripts/verify_module.sh aria-integrity-wing
./aria-integrity-wing/apply_integrity.sh
```
