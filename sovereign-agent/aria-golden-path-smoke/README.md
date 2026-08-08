# aria-golden-path-smoke — the plan's own capstone gate

The plan's own standing "finished, complete, whole" end-to-end proof:
*"boots the agent loop headless (no TUI), sends one representative
operator turn end-to-end, asserts a coherent response + a clean
events.jsonl + no unhandled exception. Run it once after every
workstream lands and once more at the very end as the finished,
complete, whole gate."*

## A real, live bug this build caught on its very first real run

Building this smoke test immediately caught a genuine, 2+-week-old
production bug: `sov run` (the CLI's entry to `agent_loop()`) crashed on
**every single invocation**, in every mode, before ever reaching the
model — `SYSTEM_PROMPT_TEMPLATE.format(...)` raised
`KeyError: 'title, action_kind, action_input'` because the template's
`workflow_create` documentation example used literal `{curly braces}`
that Python's `str.format()` tried to parse as a field name.

**Introduced 2026-06-19, never caught, because the existing test for
this function *explicitly acknowledged the conflict in a comment and
tested around it instead of fixing it*** — `tests/test_loop_utils.py`
had `test_system_prompt_is_callable()` (checks the function exists) but
never actually *called* `_system_prompt(mode)`. Root-cause fixed:
escaped the literal braces to `{{title, action_kind, action_input}}` in
`loop.py`, and rewrote the test to actually call `_system_prompt()` for
every `Mode` value and assert it renders. Independently confirmed via
`events.jsonl`: a real scheduled daily-eval task (`sched-daily-eval-
202607030700`) hit this exact same crash in production earlier the same
day this was found — not a hypothetical, a live failure.

This is exactly why the plan calls this the capstone gate — it's the one
check that actually exercises the assembled system end-to-end rather than
its pieces in isolation, and it found something real on its first run.

## What this ships

`scripts/golden_path_smoke.sh` — a new standalone script (not a patch to
anything existing):
1. Preflight: Ollama must be reachable, or this is an honest FAILURE
   (not a silent skip) — the gate is meaningless without a live model.
2. Snapshots `events.jsonl`'s line count before the run.
3. Runs `sov run "<goal>" --json --quiet` — the real headless entry point
   to `agent_loop()`, no TUI.
4. Asserts exit code 0 (no unhandled exception).
5. Asserts the JSON response's `final_message` is non-empty (coherent,
   not silence).
6. Asserts `events.jsonl` grew (the event stream is alive, not stalled).

Accepts an optional custom goal as `$1`; defaults to a safe, cheap,
representative turn ("Say hello and confirm you are working.").

## Deliberately NOT part of the normal `pytest tests/` sweep

This makes a real Ollama call (~30-40s, network + LLM dependency) —
folding it into the otherwise fast, deterministic, fully-offline test
suite would make every `pytest tests/` run slower and flakier. Instead:
- `tests/test_patcher.py` (staging) / the structural checks in
  `tests/test_golden_path_smoke_live.py` (promoted) verify the script's
  shape — existence, valid bash syntax, correct assertion structure —
  fast and always run, no Ollama needed.
- The actual end-to-end invocation is gated behind
  `RUN_GOLDEN_PATH_LIVE=1`, opt-in only. If Ollama isn't reachable when
  that flag IS set, the test skips with an honest reason — it never
  fakes a pass.
- The apply script itself runs the real gate once, for real, as the
  final proof that it was installed correctly.

## Tests

`tests/test_patcher.py` (8 tests, staging) — the payload script exists,
has valid bash syntax, uses strict mode (`set -euo pipefail`), checks
Ollama reachability before anything else, correctly treats a non-zero
exit / empty final_message / stalled events.jsonl as failures, accepts a
custom goal argument.

`tests/test_golden_path_smoke_live.py` (promoted to live `tests/`):
structural checks always run; the real end-to-end run is opt-in
(`RUN_GOLDEN_PATH_LIVE=1`) and skips honestly if Ollama is unreachable.

Reversible: delete `scripts/golden_path_smoke.sh` (or restore from the
backup if one existed).
