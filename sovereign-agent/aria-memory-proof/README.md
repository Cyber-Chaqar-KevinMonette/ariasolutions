# aria-memory-proof — the proving ground's memory wing (FABLE II · M4)

> The stick before the tuning, as always: five new SCORED tasks for the
> faculties FABLE II hardens. Real machinery, mechanical scorers, no LLM
> judge. Suite version bumps v1 → v2 because membership changed — stored
> scores keep naming the suite they scored (the M1 `proving-suite` join).

## The five tasks
- `cross-restart-recall` — sealed conversation survives a fresh store
  instance (restart-equivalent for a file-backed store)
- `lesson-roundtrip` — a lesson written to atoms.db lands in the retrain
  corpus (`gather_lesson_text`); the synthetic row is removed after
- `journal-once-only` — the daily witness writes exactly one entry, even
  with the model unreachable (mechanical fallback)
- `one-truth-clean` — M1's sentinel reports all 8 joins agreeing on a
  healthy tree (no wolf-crying)
- `compaction-recall` — M2's compaction keeps recent reads identical and
  old records reachable verbatim through the cold pointer

Note: run against the live tree, `cross-restart-recall` seals two real
turns into her thread (the same convention as v1's `thread-recall`), and
the witness task may leave one tagged field note — everything else runs
in temp dirs.

## Verify / Apply
```bash
./scripts/verify_module.sh aria-memory-proof
./scripts/safe_apply.sh aria-memory-proof
```
