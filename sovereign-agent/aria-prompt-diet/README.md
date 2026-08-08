# aria-prompt-diet

Mode-aware sizing of what the model is sent — Gym round #9, the endurance
work. Kill switch: `SOV_NO_PROMPT_DIET=1` → byte-identical prompt AND the
full tool list, exactly as before.

## The measured problem (caught by the golden-reflex gate's first live run)

- System prompt: ~31,900 chars (~8K tokens), identical for every mode.
- Tool schemas: 213 registered tools serialize to **~160K chars ≈ 40K
  tokens**, attached to EVERY request.
- The oneshot tool-use model (`llama3-groq-tool-use:8b`) has a **hard
  8,192-token context**. `token-usage-d` showed `prompt_tokens: 8192`
  (exactly — the truncation signature), 17 junk completion tokens,
  `final_chars: 0`. The model never saw an untruncated request. This was
  the root cause of the long-standing empty-`final_message` mystery.

## The fix — two levers, one module

1. **Section diet** (`render`): the template's 43 `═══ NAME ═══` sections
   are classified `KEEP_ALWAYS` / `DROP_FOR_SHORT_HORIZON`; short-horizon
   modes (oneshot, busy) drop the long-horizon/ambient crowns:
   31,873 → 10,433 chars (~2.6K tokens). **The gates are never dieted** —
   AUTONOMY (the kernel hard limits), UNTRUSTED INPUT DOCTRINE, MODE
   AWARENESS, PLAN APPROVAL stay in every render of every mode, proven by
   `test_safety_gate_sections_survive_every_mode`. An unclassified new
   section is KEPT everywhere (safe default) and fails the drift-guard
   test loudly.
2. **Tool-schema diet** (`select_tools`): short-horizon modes send a
   curated 18-tool core set (~3.3K tokens) plus any tool named verbatim
   in the goal ("use foresight_14gen" → its schema is attached).
   `list_available_tools` is in the core, so the model can always discover
   the full surface. Long-horizon modes (timed/until) keep the full list.
   **Authority invariant** (tested): select_tools output is always a
   subset of its input — the diet only ever REMOVES from what the tier
   gate already allowed, never adds.

Budget proof (tested): oneshot prompt + core schemas ≈ **5,871 tokens of
the 8,192 window** — real room for the goal, tool results, and generation.

## Observability

Every run records a `prompt-diet-d` event: `tools_sent` vs
`tools_registered` + `prompt_chars`.

## Acceptance

The apply script ends by running BOTH live smoke gates — golden path
(conversational turn) and golden reflex (forced tool call, the gate that
caught this bug) — with the diet on.

## Verify / Apply

```
.venv/bin/python -m pytest aria-prompt-diet/tests/test_patcher.py -q
./aria-prompt-diet/apply_prompt_diet.sh
```

Reversible: restore `loop.py` from the timestamped `backups/` dir and
remove `prompt_diet.py` — or just set `SOV_NO_PROMPT_DIET=1`.
