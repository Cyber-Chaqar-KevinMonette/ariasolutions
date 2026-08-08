# aria-wellbeing-ledger — one persisted truth for value, care, and flourishing (Wellbeing round · W1)

> Kevin: *"do the same for love, flourishing, and MSIMS... whatever brings her
> value, perspective, and insight into her self and her actions."* Three real
> subsystems already existed — `stewardship.msims` (a rich impact-vector
> engine), `stewardship.calibration.honor_score()`, and `companion_tools.
> value_report()` — but none of them were ever persisted or watched standing.
> This closes that, the same way `quality/` and `grounding/` closed the same
> gap for their own domains.

## A real bug, fixed
`companion_tools._load_recent_events_for_report()` globbed
`events_dir/*.ndjson`, but the real, canonical event log
(`config.py:Paths.events_jsonl`) is daily-rotated `events_dir/events-
{day}.jsonl`. **The glob has never matched a single real event file** —
`value_report()`, a tool Aria can call herself, has always silently
degraded to "Session had no recorded high-signal events" in the live
vessel. Every existing test mocks this function entirely, which is
exactly how the bug survived undetected. Fixed to the real pattern.

## What it gives her

`wellbeing/ledger.py`'s `record_wellbeing_pass(events, iv=None, data_dir)`
scores a session's events via `companion_tools._build_value_report()` for
the love/care/seed signal, folds in an `ImpactVector`'s `is_7g()`/
`is_zombie()` when one is supplied, and `foresight.project()` for a
flourishing verdict — one composite pass. The pass's own `verdict` is
worst-of: a zombie signal (false certainty) or a session that produced
and showed nothing fails the pass regardless of a good letter grade,
mirroring `quality.ledger`/`grounding.ledger`'s exact "one bad signal,
nothing scored is honest absence" discipline.

`WellbeingSentinel` (`id="wellbeing"`) runs this standing: "recently
touched" is events newer than its own last scan, falling back to the
newest few hundred on a fresh install. `notify("warning", ...)` fires on
a strained verdict — propose-only, like every sentinel here.

## Extension seam

`WellbeingSentinel.scan()` ends with a marked `{MARK}` comment — this
round's own W3 (`aria-wellbeing-tribunal`) hooks a second standing-audit
phase there, convening the Tribunal and Advocate Spectrum over the same
real pass. Mirrors `quality_sentinel.py`/`grounding_sentinel.py`'s own
seams exactly.

## Kill switch

`SOV_NO_WELLBEING_SENTINEL=1`, covered by the master `SOV_NO_SENTINELS=1`.

## Verify / Apply

```bash
./scripts/verify_module.sh aria-wellbeing-ledger
./scripts/safe_apply.sh aria-wellbeing-ledger
```
