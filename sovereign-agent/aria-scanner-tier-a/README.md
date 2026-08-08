# aria-scanner-tier-a — the Tier-A scanner harvest (Workstream J)

> D's `SCANNER_CATALOG.md` named the 10 highest-leverage scanners of the ~100 candidate roster and
> sequenced them behind the anti-ghost/anti-zombie/anti-false-path suite. This module builds 6 of
> them — the cheapest, highest-value ones — reusing D's precision discipline: a real defect in code
> that runs blocks; the same pattern in a comment, placeholder, or reviewed line never cries wolf.

## The 6 scanners

| # | Scanner | Catches | Severity |
|---|---------|---------|----------|
| 1 | **secret-leak** | API keys, AWS/Slack key shapes, password literals, private-key blocks in shipped code | `block` |
| 2 | **anchor-integrity** | a `-import-d`/`-all-d` anchor an `apply_*.sh` references but that doesn't exist in its target; a tool imported into `tools/__init__.py` but missing from `__all__` | `block` |
| 3 | **import-cycle** | circular imports within `sovereign_agent.*` (AST import graph, DFS cycle detection) | `warn` |
| 4 | **authority-tier-drift** | `ToolMeta(tier=3, ...)` missing `requires_approval=True` — statically, before the module is ever applied (authority.py's `register_tool()` enforces the same invariant at runtime, but only once the code executes; this catches it earlier) | `block` |
| 5 | **bare-except** | `except:` / `except Exception: pass` swallowing errors silently | `warn` |
| 6 | **mutable-default-arg** | `def f(x=[])` / `={}` foot-guns | `warn` |

## Real findings on this repo (self-scan, 2026-07-03)

Not hypothetical — a full scan of live `src/sovereign_agent/` (420 files) found:
- **141 bare-except instances**, **1 real import cycle** (`schedule` ↔ `mode_controller`)
- **0 blocks** (no secrets, no mutable defaults, no authority-tier-drift) — a clean bill on the
  highest-severity checks
- **Anchor-integrity caught a genuine gap in this session's own earlier fix**: `aria-tools-all-export-fix`
  resolved the *runtime* problem (7 tools now export correctly) but did so under its own idempotency
  marker rather than the original `calibration-all-d`/`self-portrait-all-d` anchors that
  `aria-honor-calibration`/`aria-self-portrait`'s own apply scripts still look for — worth reconciling
  before those two modules are ever (re-)applied, so they don't attempt a duplicate patch. Noted for K.

## Payload
- `src/sovereign_agent/scanner_tier_a/scanner.py` — all 6 scanners (`scan_secrets`,
  `scan_anchor_integrity`, `scan_all_exports`, `scan_import_cycles`, `scan_authority_tier_drift`,
  `scan_bare_except`, `scan_mutable_defaults`), plus `scan_file`/`scan_tree` aggregators.

## Use
```python
from pathlib import Path
from sovereign_agent.scanner_tier_a import scan_tree, scan_anchor_integrity

result = scan_tree(Path("src/sovereign_agent"))
print(result.summary())                       # "420 files · 0 block · 142 warn · 142 total"

anchor_findings = scan_anchor_integrity(Path("."))   # repo root
```

## Verify / Apply
```bash
./scripts/verify_module.sh aria-scanner-tier-a   # before apply (read-only)
./aria-scanner-tier-a/apply_scanner_tier_a.sh    # cockpit stopped
```

## Composes with H1
Once both `aria-universal-scanner` (H1) and this module are applied, `stewardship.registry.scan_all`
picks up any newly-registered sentinel automatically — no code change needed in H1's `run()`. The
remaining ~94 scanners in `SCANNER_CATALOG.md` are sequenced behind this Tier-A set.
