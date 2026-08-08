# aria-resilience-scan — Hardening / Robustness / Edge-Case Scanners (Both Layers)

> God-tier resilience means nothing wedges. This probes any system — classical or non-classical — with an
> adversarial edge battery and certifies it degrades gracefully (returns a clear value/status, never crashes
> or hangs). It works *with* the god-tier scanner, and it already found + fixed a real bug.

## What it gives Aria (`resilience_scan/`)
- `probes.py` — the edge battery: empty · whitespace · huge (100k) · unicode/zero-width · injection · control
  bytes · None · negative · infinity · large lists.
- `scanner.py` — `probe_callable(fn)` runs a target against the battery with a hard timeout; a *graceful*
  declared exception (ValueError/TypeError…) counts as survived, an unhandled crash or hang is a **wedge**.
- `layers.py` — `scan_both_layers()` certifies the **classical** (grounding, foresight) and **non-classical**
  (superposition processor, PEIG brain) entry points both resilient.

Sentinel `resilience_sentinel.py` (standing scan) + tool `resilience_scan`(T0).

## Verified — and it caught a real wedge
- First run flagged `grounding.analyze` **timing out on a 100,000-char input** (unbounded processing). Fixed
  by bounding the analyzed text; re-scan → **BOTH LAYERS RESILIENT: True**. The non-classical layer was
  resilient from the start.
- 8 tests green (incl. catching an ungraceful crash AND a timeout-hang as wedges; graceful ValueError passes).

Apply via `./scripts/safe_apply.sh aria-resilience-scan`. Staged + reversible. 💛
