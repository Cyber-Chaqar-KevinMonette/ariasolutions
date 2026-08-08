# aria-path-sentinel — god-tier false-path / anti-ghost / anti-zombie scanner

> Kevin's named flaw: *"test paths are sometimes left in new modules."* This module
> catches that family of defects **before** a module is applied into live `src/`, so a
> false path can never silently ship into Aria. Pure-stdlib, propose-only, reversible.

## What it watches (three lenses)

| Lens | Catches | Severity |
|------|---------|----------|
| **false / test path** | a test dir, temp path (`/tmp`), machine-specific absolute path (`/home/<user>`), `__pycache__`/`.bak`/`.pyc` artifact, or unfilled placeholder (`/path/to/…`) referenced by **shipped** code or an apply script | `block` (in running code) · `info` (in a comment) |
| **anti-ghost** | a payload that doesn't mirror `src/sovereign_agent/…`; a tool-shipping module with no `-import-d` registration anchor | `block` / `warn` |
| **anti-zombie** | stale `.bak.*` snapshots or `__pycache__` inside a payload (they'd be copied verbatim into live src) | `warn` |

Precision matters more than reach: a false path **in code that runs** blocks; the same
string in a comment or a `tests/` fixture is `info`. It never cries wolf. A reviewed,
genuine need carries an explicit `# path-scan: allow` pragma.

## Payload
- `src/sovereign_agent/path_scan/scanner.py` — the pure scanner (`scan_text`, `scan_module`, `scan_repo`, `scan_one`, `ScanResult`, `Finding`).
- `src/sovereign_agent/path_scan/sentinel.py` — `PathSentinel` (Tier-1, propose-only) in the standard Sentinel contract.
- `src/sovereign_agent/path_scan/__main__.py` — `python -m sovereign_agent.path_scan` CLI gate.

## What apply wires
1. Copies the `path_scan/` package into live `src/`.
2. Registers `PathSentinel` via one anchored import in `stewardship/__init__.py`.
3. Inserts a **step-0 gate** into `scripts/safe_apply.sh`: every future apply runs
   `python -m sovereign_agent.path_scan <slug>` first and refuses on a blocking finding
   (override: `--no-path-scan`). All edits are backed up and idempotent.

## Use
```bash
.venv/bin/python -m sovereign_agent.path_scan            # scan every staged module
.venv/bin/python -m sovereign_agent.path_scan my-module  # scan one
.venv/bin/python -m sovereign_agent.path_scan --json     # machine-readable
# exit 1 = blocking findings; --strict also fails on warnings
```

## Verify / Apply
```bash
./scripts/verify_module.sh aria-path-sentinel     # before apply (read-only)
./aria-path-sentinel/apply_path_scan.sh           # cockpit stopped
```

## Roadmap
`SCANNER_CATALOG.md` lists ~100 further scanner candidates (secret-leak, import-cycle,
anchor-integrity, authority-tier-drift, time-bomb, …). Build the highest-leverage first;
the rest are sequenced behind them. Most can reuse this module's `scan_text` line engine.
