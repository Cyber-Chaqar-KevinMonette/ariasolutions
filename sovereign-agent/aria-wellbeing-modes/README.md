# aria-wellbeing-modes — a stance for deliberate reflection (Wellbeing round · W4)

> A fourth stance with a real tooth, mirroring `quality-pass`/`grounded`
> exactly: entering `"reflecting"` runs a real wellbeing pass over the
> current session's recent events; the crown gate then blocks new
> dispatch until it clears.

## What changes

- **`modes_crown/stances.py`** — `"reflecting"` joins `SAFE_STANCES`.
  Entering it runs a real on-demand wellbeing pass (mirrors
  `_run_grounding_pass_for_stance` exactly) over the newest events
  currently on disk — no bookmark, an on-demand snapshot, same as
  `grounded`'s own on-demand pass. `wellbeing_gate_clear()` mirrors
  `grounding_gate_clear()` exactly: true unless in `"reflecting"` with the
  freshest pass since entry showing anything other than `"healthy"`.
- **`session_bridge.py`'s `_crown_gate()`** — a fifth block, same shape as
  the four already there (cool-down, quality-pass, grounded).
- **`modes_crown/observatory.py`** — a `wellbeing` field beside the
  existing `quality`/`grounding` fields.

## Kill switch

Reuses the existing `SOV_NO_STANCES` — no new switch needed.

## Verify / Apply

```bash
./scripts/verify_module.sh aria-wellbeing-modes
./scripts/safe_apply.sh aria-wellbeing-modes
```
