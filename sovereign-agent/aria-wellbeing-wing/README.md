# aria-wellbeing-wing — proving wing + close-out + extensibility retrofit (Wellbeing round · W5)

The stick before any tuning, for the W1-W4 machinery, following the exact
Q5/G5 wing shape. Five real, mechanically-scored tasks, no LLM judge:

  1. **wellbeing-pass-persists** — a wellbeing pass over real events
     round-trips through W1's ledger.
  2. **wellbeing-gate-blocks** — W2's `gate()` BLOCKs a zombie-IV fixture
     (a false-certainty impact vector).
  3. **wellbeing-diagnosis-readable** — W3's standing audit logs a real,
     readable `WELL-*` case into the diagnosis catalog.
  4. **wellbeing-angel-measured** — W3's `angel()` lens uses the measured
     composite over a live-only check.
  5. **wellbeing-pass-gates** — W4's `reflecting` stance gates dispatch
     then clears it.

## Wiring

`proving_ground/runner.py` — same tail-import pattern `trust_wing.py`/
`quality_wing.py`/`grounding_wing.py` already use. `SUITE_VERSION` bumps
`v5 → v6`.

## Doc sync — a genuine 9th god-tier dimension

`GOD_TIER_STANDARD.md` gains a **9th dimension, "Love & Flourishing"**
(the section header updates from "eight dimensions" to "nine"), bringing
it in line with `GOD_TIER_CRITERIA.md`'s own already-existing dimension 9
("Love — the criterion the other frameworks forget", which is about
relational courtesy mechanics and already fully MET — a different,
non-overlapping concern from this round's *measured* value/care/
flourishing signal). `scripts/lib/god_tier_floor.json` gains the matching
`"wellbeing"` entry. Confirmed safe: `floor_check.sh` runs hardcoded bash
checks per numbered section, not a loop over the JSON's `dimensions`
array — adding a 9th entry changes nothing about how the floor is
actually enforced today.

## The extensibility retrofit

Continuing the retrofit habit Grounding round's G5 started: three
PRE-EXISTING modules this round composed but doesn't own each get one
clearly marked extension-seam comment:

  - **`stewardship/msims.py`** — a future 4th `Dimension` (e.g.
    Relational) would be picked up automatically by `dimension_score()`/
    `impact_score()`/`is_7g()`'s existing `for d in Dimension` loops,
    once `DIMENSION_WEIGHTS` names its weight.
  - **`stewardship/calibration.py`** — `honor_score()`'s five weighted
    components (`alpha`/`beta`/`gamma`/`delta`/`epsilon`) are already
    named, independent constants a future round could tune from observed
    calibration accuracy, not just today's hand-picked defaults.
  - **`tools/companion_tools.py`** — the care-flag/future-flag sets in
    `_build_value_report()` are deliberately small and named, extendable
    the moment a new event flag proves worth classifying.

## Round close-out

This is the last workstream of the Wellbeing round (W1-W5). The apply
script runs the full offline proving suite as its own final check; the
human-run close-out beyond that is: full `pytest` run ALONE (0 failures,
0 unexplained skips — verify no concurrent pytest process first, a lesson
learned twice now), `scripts/floor_check.sh`, `sov truth`, both smoke
gates (`golden_path_smoke.sh`, `golden_reflex_smoke.sh`) — then commit.

## Verify / Apply

```bash
./scripts/verify_module.sh aria-wellbeing-wing
./scripts/safe_apply.sh aria-wellbeing-wing
```
