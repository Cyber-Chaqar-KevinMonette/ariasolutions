"""`python -m sovereign_agent.consistency` — the one-truth sweep, plain.

Usage:
  python -m sovereign_agent.consistency scan     # run every join check, print verdicts
  python -m sovereign_agent.consistency health   # cached health only (no scan)

`sov truth` is the same sweep behind the cockpit-side CLI.
"""
from __future__ import annotations

import sys


def render_results(results) -> str:
    lines: list[str] = []
    total = 0
    for r in results:
        mark = "✓" if r.ok else "✗"
        note = f" — {r.note}" if r.note else ""
        lines.append(f" {mark} {r.check_id:<16} checked={r.checked}{note}")
        for f in r.findings:
            total += 1
            lines.append(f"     · {f.subject}: {f.problem}")
            lines.append(f"       propose: {f.proposal}")
    clean = sum(1 for r in results if r.ok)
    lines.append(f" ── {clean}/{len(results)} joins agree · "
                 f"{total} disagreement(s) — proposals only, nothing repaired ──")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    cmd = argv[0] if argv else "scan"
    if cmd == "scan":
        from sovereign_agent.config import SETTINGS
        from sovereign_agent.consistency.sentinel import ConsistencySentinel

        sentinel = ConsistencySentinel(SETTINGS.paths.data_dir)
        if not sentinel.is_enabled():
            print("one-truth sentinel disabled by kill switch")
            return 0
        from sovereign_agent.consistency.checks import run_all

        results = run_all()
        print(render_results(results))
        sentinel.scan()   # persist the catalog so health reflects this sweep
        return 0
    if cmd == "health":
        from sovereign_agent.config import SETTINGS
        from sovereign_agent.consistency.sentinel import ConsistencySentinel

        h = ConsistencySentinel(SETTINGS.paths.data_dir).health_status()
        print(f"[{h.level}] {h.summary}")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
