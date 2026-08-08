# aria-small-model-confidence — keep a small model from silently giving up

> Final-sprint Round 1 (vessel reliability), companion to
> `aria-small-model-bridge`. Staged / reversible / propose-only.

## The problem it solves

The bridge fixes *how* a small model's tool call is shaped. This fixes
*whether it keeps going*. Small (7B/8B) models mid-task tend to **stop
prematurely** (empty answer, work still remaining), **hedge into paralysis**
("I can't", "as an AI I cannot", "I don't have access"), or **narrate
instead of act** ("I would call read_session...") without emitting the
call. None of these mean the model is unable — it's under-equipped and
under-confident.

## What it does

`small_model_confidence` is a **pure, dependency-free** detector +
decision layer:

- `assess_turn(response, *, work_remains, reprompts_so_far, available_tools)`
  → a `TurnDecision`: `accept` (fine / done / acting) or `reprompt` with a
  concrete **equipping nudge**.
- `detect_giving_up(response)` — hedge/give-up phrasing **and** no tool
  call (a hedge that still calls a tool is fine — it's acting).
- `is_empty_answer(response)` — no tool call and no real content.
- `equipping_nudge(reason, available_tools)` — a short re-prompt that names
  the tools the model actually has (small models forget their own toolbox)
  and reframes it as capable.

**Two safety properties, tested:** it never overrides a genuinely finished
task (`work_remains=False` → always accept), and it **caps re-prompts**
(`MAX_REPROMPTS`) so it can never loop forever — a stalled model is
accepted once the budget is spent.

## How apply wires it

`apply_small_model_confidence.sh` installs the payload package. Wiring
`assess_turn()` into the live `/work` session loop (`agent_session.py`) is
a **documented, deliberate follow-up** — it touches the already-load-bearing
run loop, so it's kept as a separate reviewed step rather than an automatic
text patch. The pure library is fully usable and tested on its own now.

## Verify / Apply
```bash
./scripts/verify_module.sh aria-small-model-confidence
./aria-small-model-confidence/apply_small_model_confidence.sh
```

17 real behavior tests green.
