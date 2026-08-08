# aria-wellbeing-gate — persistence at the source, real teeth (Wellbeing round · W2)

> Today `value_report()` computes a real self-audit — accomplishments,
> acts of care, seeds planted, a letter grade — and throws it away the
> moment the tool call returns. Nothing ever checked whether the result
> was actually good, either.

## What it gives her

`wellbeing/gate.py`'s `gate(events, iv=None, decision_text=None)` renders
a real PASS/WARN/BLOCK verdict: BLOCK on an `ImpactVector`'s `is_zombie()`
(false certainty caught), or a session that graded "D" with zero
accomplishments AND zero care shown — the concrete, measurable form of
Weakness Register RISK-004 ("unproven value"). WARN when a flourishing
verdict was computed (only when real decision text is given — never
scored on a generic session summary) and it isn't `"carry-forward"`. PASS
otherwise, honest PASS on empty input.

Wired directly into `companion_tools.py`'s `ValueReportTool.execute()` —
the exact real, load-bearing call site she already invokes herself: right
after `_build_value_report()` builds the report, `record_wellbeing_pass()`
persists it, so every self-audit becomes standing history instead of
vanishing. Best-effort — a ledger failure never breaks the tool call
itself, and the tool's own return value is unchanged.

## Kill switch

`SOV_NO_WELLBEING_GATE=1` — degrades to PASS with a note, never silently
BLOCKs while claiming to have checked something it didn't.

## Verify / Apply

```bash
./scripts/verify_module.sh aria-wellbeing-gate
./scripts/safe_apply.sh aria-wellbeing-gate
```
