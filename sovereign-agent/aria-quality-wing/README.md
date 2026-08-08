# aria-quality-wing — proving-ground wing + round close-out (Quality round · Q5)

The stick before any tuning, for the Q1-Q4 machinery, following the exact
M4/M7 wing shape. Five real, mechanically-scored tasks, no LLM judge:

  1. **hardening-persists** — a quality pass over a real file round-trips
     through Q1's ledger (returned result and freshly-read `latest_quality()`
     agree byte-for-byte on `pass_id`/`value`).
  2. **gate-blocks-bad** — Q2's `gate()` BLOCKs a known-bad fixture (no type
     hints, no docstring, no referencing test) — never silently PASSes it.
  3. **diagnosis-readable** — Q3's `log_to_diagnosis()` bug fix stays fixed:
     it returns a real, readable `TRIB-*` case, and the catalog actually
     holds it as `type="ambiguity"`.
  4. **artisan-measured** — Q3's artisan lens overrides its prose heuristic
     with the measured `quality_score`/`hardening_critical_ok` when present.
  5. **quality-pass-gates** — Q4's stance gates dispatch until a clean pass
     lands, then clears it. The stance's own entry side effect scores
     whatever the live repo's git diff happens to be at the moment the task
     runs — real, but not something a fixed assertion can pin down run to
     run — so that one half is deliberately controlled (the side effect
     disabled just for the "starts unclear" half); the "clears once a real
     pass lands" half then runs an actual `record_quality_pass()`. Real
     machinery throughout, controlled input instead of an unpredictable
     working tree.

## Wiring

`proving_ground/runner.py` — same tail-import pattern `trust_wing.py` and
`memory_wing.py` already use: `from .quality_wing import QUALITY_TASKS` +
`OFFLINE_TASKS.update(QUALITY_TASKS)`. `SUITE_VERSION` bumps `v3 → v4`,
same explanatory-comment convention.

## Doc sync

`GOD_TIER_STANDARD.md`'s Quality floor (dimension 6) and
`scripts/lib/god_tier_floor.json`'s `"quality"` entry both gain the same
words: *"a hardening/test quality score is persisted and gates apply."*
`GOD_TIER_CANON.md`/`god_tier_canon.json` (the aspirational ceiling, not
the floor) are left untouched.

## Round close-out

This is the last workstream of the Quality round (Q1-Q5). The apply
script runs the full offline proving suite as its own final check; the
human-run close-out beyond that is: full `pytest` (0 failures, 0
unexplained skips), `scripts/floor_check.sh`, `sov truth`, both smoke
gates (`golden_path_smoke.sh`, `golden_reflex_smoke.sh`) — then commit.

## Verify / Apply

```bash
./scripts/verify_module.sh aria-quality-wing
./scripts/safe_apply.sh aria-quality-wing
```
