# aria-golden-reflex

The tool-calling end-to-end gate — Gym round #8.

## The gap

`scripts/golden_path_smoke.sh` proves ONE plain conversational turn — its
default goal ("say hello") deliberately needs no tools, so the deeper
loop — authority gate → tool dispatch → tool result feeding back into the
model → a coherent answer built on it — had no end-to-end proof at all.

## The gate

`scripts/golden_reflex_smoke.sh` (same discipline as the golden-path
gate: real Ollama call, honest failure when unreachable, deliberately
outside `pytest tests/`): runs `sov run` with a goal engineered to force
a T0 tool call (`read_lessons`), then asserts from **events.jsonl** — not
from the model's prose —
1. exit 0,
2. a `tool-start-d` dispatch event emitted during THIS run,
3. a matching `<tool>-d` result event following it (feedback happened),
4. non-empty `final_message`.

Sequenced deliberately BEFORE aria-prompt-diet: the diet's acceptance
criterion is that BOTH smoke gates still pass with the diet on.

## Verify / Apply

```
.venv/bin/python -m pytest aria-golden-reflex/tests/ -q
./aria-golden-reflex/apply_golden_reflex.sh   # ends by running the real gate
```

Reversible: `rm scripts/golden_reflex_smoke.sh`.
