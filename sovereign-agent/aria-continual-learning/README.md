# aria-continual-learning

Pipes Reflector-distilled lessons into Aria's own from-scratch training
corpus (`aria_lm`), and adds a bounded, propose-only retrain trigger.

## The gap

`reflector.py` already writes structured "lesson" records
(trigger/context/failure_mode/correction/rule) to `atoms.db`'s `lessons`
table after every settle/poison event in the agent loop — real,
accumulating task-experience, but never consulted by the training
pipeline. `aria_lm/data.py::gather_corpus()` built the training corpus
from static distilled-research files only, with zero awareness of
lessons, honor scores, or any other task-experience signal. There was
also no retrain trigger anywhere — `grow_mind()` only ever ran as a
manual, one-shot CLI-triggered batch job.

## The fix

1. **`gather_corpus()` gains a new corpus source.** Reads recorded lessons
   via a new `aria_lm/retrain_trigger.py::gather_lesson_text()` and
   formats each as a short training example (`trigger: rule correction`).
   **Inserted at the front of the corpus, not appended** — the distilled
   research text can easily exceed `max_chars` on its own, and the
   existing truncation keeps only the first `max_chars` characters. A
   dedicated regression test
   (`test_lesson_text_survives_truncation_when_distilled_corpus_is_huge`)
   proves lesson text survives even when a synthetic huge distilled
   corpus is present — this was a real bug caught by testing the first
   draft (which used `parts.append(...)`), not found by inspection.
   Degrades silently to the current behavior when no lessons exist yet —
   zero regression to the existing corpus path (proven by
   `test_gather_corpus_degrades_gracefully_with_no_lessons`, and the
   pre-existing `test_gather_corpus_nonempty` in
   `tests/test_aria_lm_foundation.py` stays untouched and green).
2. **A bounded retrain trigger, not an unbounded auto-retrain loop.**
   `retrain_trigger.py` tracks a `last_retrain.json` marker
   (`{lesson_count_at_last_retrain, last_retrain_ts}`) under
   `data_dir/aria_lm/`. `check_retrain_proposal(data_dir, threshold=20)`
   compares the current lesson count against that marker and returns a
   proposal dict once enough NEW lessons have accumulated — it **never
   triggers training itself**. `record_retrain()` resets the baseline,
   called (best-effort, via an anchored patch to `pipeline.py::
   grow_mind()`) only after a real training run actually completes.
3. **`ProposeRetrainTool`** (Tier 1, `tools/continual_learning_tools.py`)
   is a thin surface over `check_retrain_proposal()` — reports whether a
   retrain is due and, if so, the exact command a human would run
   (`python -m sovereign_agent.aria_lm.pipeline`). It never imports or
   calls `grow_mind()`/`train_model()` — proven by a dedicated test that
   monkeypatches `grow_mind` to raise if called at all. Training a
   base-weight model stays Tier 3 / human-gated, per `aria_lm_tools.py`'s
   own existing doctrine — this tool only counts and proposes, matching
   every other autonomous-adjacent workstream this session (N's
   `work_interval.py` in particular): propose, don't act.

## Files

- `payload/src/sovereign_agent/aria_lm/retrain_trigger.py` — NEW file:
  `gather_lesson_text()`, `total_lesson_count()`, `check_retrain_proposal()`,
  `record_retrain()`.
- `payload/src/sovereign_agent/tools/continual_learning_tools.py` — NEW
  file: `ProposeRetrainTool`.
- `patcher.py` — `patch_data_py()` (adds the lesson corpus source to
  `gather_corpus()`), `patch_pipeline_py()` (adds the `record_retrain()`
  call to `grow_mind()`), `patch_tools_init()` (registers
  `ProposeRetrainTool`, import + `__all__` in the same patch). All
  anchored, idempotent (`MARK = "continual-learning-d"`).
- `tests/test_patcher.py` — structural tests against the patch functions.
- `tests/test_continual_learning.py` — shadow-copy behavior tests (never
  touches real `src/`). Staged only, never promoted. Note: the shadow
  builder mirrors the real repo layout (`shadow/src/sovereign_agent/...` +
  `shadow/sql/...`, not just the package alone) because `db.py`'s
  `open_atoms_db()` locates `sql/002_atoms.sql` via
  `Path(__file__).parent.parent.parent`, which requires `src` and `sql`
  to be siblings exactly as they are in the real repo.
- `tests/test_continual_learning_live.py` — the promoted copy: plain
  imports of the real post-apply modules, zero `sys.modules`
  manipulation.
- `apply_continual_learning.sh` — guard → backup 3 files → patch → copy 2
  new files → compile check → import/registration check → promote the
  live test file → run.

## Verify

```
.venv/bin/python -m pytest aria-continual-learning/tests/test_patcher.py \
  aria-continual-learning/tests/test_continual_learning.py -q
```

## Apply

```
./aria-continual-learning/apply_continual_learning.sh
```

Reversible: restore `aria_lm/data.py`, `aria_lm/pipeline.py`, and
`tools/__init__.py` from the timestamped `backups/` dir the script
creates, and remove `aria_lm/retrain_trigger.py` +
`tools/continual_learning_tools.py`.
