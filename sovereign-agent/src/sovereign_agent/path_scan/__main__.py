"""CLI gate: `python -m sovereign_agent.path_scan [module] [--json] [--strict]`

  • no args            → scan every staged aria-* module
  • a module name      → scan just that one (with or without the aria- prefix)
  • --json             → emit the machine-readable ScanResult
  • --strict           → exit 1 on warnings too (default: exit 1 only on blocks)

Exit codes:  0 = clear to apply · 1 = blocking findings (or warnings under --strict)

This is what safe_apply calls at step 0 — a false path can never silently ship.
"""
from __future__ import annotations

import json
import sys

from .scanner import scan_one, scan_repo


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    as_json = "--json" in args
    strict = "--strict" in args
    positional = [a for a in args if not a.startswith("-")]

    if positional and positional[0] == "triage":  # path-scan-triage-d
        from .scanner import _default_repo_root
        from .triage import triage_report

        report = triage_report(_default_repo_root())
        if as_json:
            print(json.dumps(report, indent=2))
        else:
            c = report["counts"]
            print(f"triage: {c['applied']} applied · {c['pending']} pending · "
                  f"{c['unknown']} unknown")
            for status in ("pending", "unknown"):
                for name in report[status]:
                    print(f"  {status:8s} {name}")
        return 0

    result = scan_one(None, positional[0]) if positional else scan_repo(None)

    if as_json:
        print(json.dumps(result.as_dict(), indent=2))
    else:
        print(f"path-scan: {result.summary()}")
        for f in result.blocks + result.warns:
            tag = "BLOCK" if f.severity == "block" else "warn "
            loc = f"{f.module}/{f.path}:{f.line}" if f.line else f"{f.module}/{f.path}"
            print(f"  {tag} {f.kind:28s} {loc}")
            if f.excerpt:
                print(f"        {f.excerpt}")
        if result.clean and not result.warns:
            print("  ✓ no false / ghost / zombie paths")

    if result.blocks:
        return 1
    if strict and result.warns:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
