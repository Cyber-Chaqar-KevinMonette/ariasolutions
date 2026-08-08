# aria-universal-scanner — the Universal Scanner Kernel (Workstream H1)

> Kevin's ask, distilled from `Plans/`: *"could we design a universal scanner?"* — yes, as a small,
> sharp kernel plus a plugin roster, not one omniscient rule. This is that kernel: it composes the 15
> registered sentinels + D's path sentinel under one pre-flight gate. It replaces none of them.

## What it is

Two layers, both propose-only, Tier 1:

1. **`kernel_check(op)`** — 8 cheap, hard-coded, in-process checks against Aria's actual kernel:
   deferred-unsafe boundary language, authority-tier consistency, consent, provenance (named actor),
   declared reversibility, a signal-check nudge (informational only, never blocks), domain presence,
   and a non-empty description. No I/O, fast enough to run on every turn.
2. **`run(op)`** — `kernel_check()` first (short-circuits on a hard fail); otherwise fans out to
   every registered sentinel (`stewardship.registry.scan_all`) and, when the operation names a staged
   module (`domain="module:<slug>"`), D's path sentinel (`path_scan.scan_one`). Every plugin verdict
   folds into one via worst-wins: `PASS` < `SOFT_FAIL_RETRY` < `HARD_FAIL_BLOCK`.

## Payload
- `src/sovereign_agent/universal_scanner/kernel.py` — `OperationDescriptor`, `KernelVerdict`,
  `kernel_check`, `run`.
- `src/sovereign_agent/universal_scanner/__main__.py` — `python -m sovereign_agent.universal_scanner
  check --what "..." [--who NAME] [--domain D] [--tool NAME]...` (layer 1 only; call `run()` from
  Python for the full fan-out, since that needs a `data_dir`/`repo_root`).

## Use
```bash
.venv/bin/python -m sovereign_agent.universal_scanner check --what "read the sentinel health report" \
    --who Kevin --reversible true
# exit 0 = PASS, 1 = SOFT_FAIL_RETRY, 2 = HARD_FAIL_BLOCK
```
```python
from pathlib import Path
from sovereign_agent.universal_scanner import OperationDescriptor, run

op = OperationDescriptor(who="Kevin", what="apply aria-foo", domain="module:foo", reversible=True)
verdict = run(op, data_dir=Path("~/.local/share/sovereign-agent").expanduser(), repo_root=Path("."))
print(verdict.summary())
```

## Verify / Apply
```bash
./scripts/verify_module.sh aria-universal-scanner   # before apply (read-only)
./aria-universal-scanner/apply_universal_scanner.sh # cockpit stopped
```

## Roadmap
J's Tier-A scanner harvest (secret-leak, anchor-integrity, import-cycle, authority-tier-drift,
bare-except, mutable-default-arg) plugs into this kernel's fan-out the moment both exist — no changes
needed to `run()` itself, since `stewardship.registry.scan_all` already picks up any newly-registered
sentinel automatically. Wiring `run()` into `safe_apply.sh` as an additional pre-flight layer (beside
D's existing step-0 path-scan gate) is a natural follow-up once Kevin wants the full-kernel check on
every apply, not just the path check.
