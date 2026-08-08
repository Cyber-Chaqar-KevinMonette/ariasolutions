# aria-grounding-modes — the gray area, made real (Grounding round · G4)

> Kevin: *"not too strict, not too loose — a healthy grounded gray area
> for when what is needed most... free to explore, dream, think, and work
> in grounded reasoning."*

## Two stances, one gray area

**`"grounded"`** — the strict end, a real tooth (mirrors `quality-pass`
exactly): entering it runs a real grounding pass over her recently-
written journal entries and QA answers; the crown gate then blocks new
dispatch until that pass clears (verdict isn't `"ungrounded"` and the
qa-uncertainty join holds).

**`"theoretical"`** — the licensed end: a plain label, Tier-0, no gate at
all. Its whole value is honesty and observability, not new leniency-
tuning: `tribunal/grounding.py`'s own classifier already treats hedge/
hypothesis language ("might", "predict", "if…then") as `falsifiable-
hypothesis` — counted toward *grounded*, not fog — so genuinely
theoretical, honestly-hedged exploration already passes cleanly with zero
new machinery. What `"theoretical"` adds: `GroundingSentinel`'s standing
passes now tag every scored text with whatever stance was active at scan
time, so a reader can see "this was written while she'd declared herself
in theoretical territory" — a fact, not a excuse.

Between the two, with no stance declared (today's default), nothing new
gates or relaxes anything — byte-identical to today.

## What changes

- **`grounding/ledger.py`** — `record_grounding_pass()` gains an optional
  `context` parameter (default `""`, every existing caller unchanged),
  stamped onto every `TextScore`.
- **`modes_crown/stances.py`** — `"grounded"`/`"theoretical"` join
  `SAFE_STANCES`; `grounding_gate_clear()` mirrors `quality_gate_clear()`
  exactly.
- **`stewardship/grounding_sentinel.py`** — `scan()` tags its own standing
  pass with `current_stance()`, whatever it is (or `""`).
- **`session_bridge.py`'s `_crown_gate()`** — a fourth block, same shape
  as `quality-pass`'s: `"grounded"` blocks dispatch until its own gate
  clears.
- **`modes_crown/observatory.py`** — a `grounding` field beside the
  existing `quality` field.

## Kill switch

Reuses the existing `SOV_NO_STANCES` — no new switch needed.

## Verify / Apply

```bash
./scripts/verify_module.sh aria-grounding-modes
./scripts/safe_apply.sh aria-grounding-modes
```
