# aria-quality-modes — a quality stance with a real tooth (Quality round · Q4)

> Kevin: *"Maybe quality modes she can go into while in auto mode?? <3"*
> Six of the seven inner stances are inert labels; only `cool-down` has an
> enforced effect. This gives `quality-pass` one too, reusing the exact
> pattern already proven — nothing new invented, patch-only, no new
> payload files.

## What changes

**`modes_crown/stances.py`** — `"quality-pass"` joins `SAFE_STANCES`.
Entering it is a real action, not a label: `set_stance("quality-pass")`
synchronously runs a real quality pass (Q1's `record_quality_pass()`) over
whatever `.py` files are currently changed vs `HEAD` — best-effort; a
failure here degrades to an honest empty/unclear pass, never a crash on
the stance change itself. `quality_gate_clear()` is true iff a quality
pass completed cleanly **since** the stance was entered — compared by
timestamp against when the stance was set, not by wall-clock recency — and
vacuously true whenever the operator isn't in the stance at all.

**`session_bridge.py`'s `_crown_gate()`** — the same shape as the
`cooling_down()` block right beside it: while in `quality-pass` with no
clearing pass yet, new goal dispatches are refused (the running one always
finishes). Wrapped in its own `except ImportError`, so a crown-gate call
degrades cleanly before this patch lands, or if `quality/` was never
applied at all.

**`modes_crown/observatory.py`** — the watching window gains a `quality`
field (the raw latest-pass dict — `value`/`critical_ok`/`ts` — reusing Q1's
ledger shape rather than inventing a new one) beside the existing
`emotion`/`stress`/`⚡ load` fields; renders as `◆ quality  91.5/100` (plus
`· CRITICAL FAILURE` when the last pass wasn't clean).

## Kill switch

Reuses the existing `SOV_NO_STANCES` — no new switch needed. Under it,
`quality-pass` degrades to cosmetic like every other stance (writes become
no-ops; nothing gates).

## Verify / Apply

```bash
./scripts/verify_module.sh aria-quality-modes
./scripts/safe_apply.sh aria-quality-modes
```
