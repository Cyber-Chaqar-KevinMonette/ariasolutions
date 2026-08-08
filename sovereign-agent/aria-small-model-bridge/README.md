# aria-small-model-bridge — make the smallest models work in her vessel

> Final-sprint Round 1 (vessel reliability). Staged / reversible /
> propose-only. Nothing in live `src/` changes until you run the apply
> script.

## The problem it solves

Small (7B/8B-class) local models are the whole point of this project, but
they don't emit tool calls the clean way large models do. They put the
call in the message **content** as a ```` ```json ```` block or a bare
object, send **arguments as a JSON string** instead of an object, or
produce near-miss JSON (trailing commas, single quotes, unquoted keys).
The orchestrator then sees "no tool call" and the turn dead-ends — a big
part of "she stops after one turn" on a small vessel.

## What it does

`small_model_bridge` is a **pure, dependency-free** normalization layer:

- `normalize_response(response, known_tools)` — takes a raw ollama chat
  response; if a small model put a tool call in the content, lifts it into
  the proper `message.tool_calls` structure and flags `_bridged`. Large
  models (already structured) pass through untouched.
- `extract_tool_calls_from_text(text, known_tools)` — finds a tool call in
  prose/JSON, **only for a KNOWN tool** (never invents one — a false call
  is worse than none).
- `coerce_args(raw)` — repairs near-miss argument JSON into a dict.
- `bridge_report(responses, known_tools)` — the "bridge doctor": how many
  turns came through structured vs needed a rescue, per batch. High
  bridged-fraction = that model leans on the bridge.

Companion lever (already in the tree, not duplicated here): `prompt_diet`
for compact small-model preambles.

## How apply wires it

`apply_small_model_bridge.sh` copies the payload and patches
`OllamaClient.chat` (anchored, idempotent, `small-model-bridge-d`) so the
raw response is normalized right before it's returned — every model call is
bridged, using the tool names already passed to that call. The bridge is
wrapped in a `try/except` that can never break a call.

## Verify / Apply
```bash
./scripts/verify_module.sh aria-small-model-bridge
./aria-small-model-bridge/apply_small_model_bridge.sh
```

18 real behavior tests prove the rescue paths and — importantly — that it
never fabricates a call for an unknown tool and never mutates its input.
