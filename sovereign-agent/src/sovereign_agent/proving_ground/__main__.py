"""CLI: python -m sovereign_agent.proving_ground [offline|trend]
(The live suite = the smoke gates; see handoff/06_RUNBOOK.md.)"""
from __future__ import annotations

import asyncio
import sys


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    cmd = args[0] if args else "offline"
    from sovereign_agent.proving_ground import latest_scores, run_offline_suite, trend

    if cmd == "offline":
        result = asyncio.run(run_offline_suite())
        print(f"proving ground {result.suite} · score {result.score:.0%}")
        for tid, t in result.tasks.items():
            mark = "✓" if t["pass"] else "✗"
            print(f"  {mark} {tid:20} {t['ms']:5}ms  {t['note']}")
        print(f"trend: {trend()}")
        return 0 if result.score == 1.0 else 1
    if cmd == "trend":
        for r in latest_scores():
            print(f"  {r['ts'][:19]}  {r['kind']:7}  {r['score']:.0%}")
        print(f"trend: {trend()}")
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
