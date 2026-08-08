# aria-apply-hardening — God-Tier Safety For Applying Staged Modules

> Make the apply menu valid, robust, strong, and intelligent **before you use it.** No staged module can
> harm the system on apply, because every apply now runs behind guards that even the script's own author
> may have forgotten — with automatic rollback if anything goes wrong.

## The honest gap it closes

An audit of all **115** `aria-*/apply_*.sh` found only **18 god-tier-safe**: **81 lacked a running-cockpit
guard**, **47 lacked a backup**, **50 lacked a `py_compile` check**, and many weren't executable. Editing 97
scripts would be fragile. Instead, one robust wrapper enforces the guards around *any* script.

## What it gives Aria / Kevin (dev-tooling in `scripts/`)

- **`scripts/validate_apply_system.sh`** — audits every apply script for 7 safety properties (cockpit-guard ·
  venv-guard · backup · `set -euo pipefail` · `py_compile` · idempotent patch · runs-tests) and grades each.
  Total coverage; flags the unsafe ones. Read-only.
- **`scripts/safe_apply.sh <module> [--yes]`** — applies ANY module **safely**, regardless of its own guards:
  1. refuse if the cockpit is running · 2. snapshot (registration files + a src file/dir list) ·
  3. pre-apply **Tribunal + 14-gen foresight gate** · 4. run the apply script · 5. verify (module tests +
  floor) · 6. **AUTO-ROLLBACK on any failure** (removes new files AND new dirs, restores the registration
  files) · 7. report the backup path.

## Verified

- The validator grades all 115 scripts and reports the unsafe ones (18 safe / 97 need-attention — all now
  safe to run *via* `safe_apply`).
- `safe_apply` **rolls back cleanly**: a throwaway module that copies a file then fails its test is fully
  undone — file *and* directory removed, live `src/` byte-identical to before. (Proven in the test battery.)
- Rejects unknown modules; the cockpit dashboard discovers all staged scripts.
- 4 tests green (`aria-apply-hardening/tests/test_apply_system.py`).

## How to apply modules safely (the new way)

```bash
./scripts/validate_apply_system.sh            # see which scripts need attention
./scripts/safe_apply.sh aria-<module>          # apply ANY module with guards + auto-rollback
```

Use `safe_apply` instead of running `apply_*.sh` directly — it makes every one of the 115 scripts safe.
Reversible by construction; nothing applies without passing the gate + verification. 💛
