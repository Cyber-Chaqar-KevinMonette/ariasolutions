"""CLI: python -m sovereign_agent.loose_threads [scan|list|disposition <symbol> <verdict> [reason...]]"""
from __future__ import annotations

import sys


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    cmd = args[0] if args else "scan"
    if cmd == "scan":
        from pathlib import Path

        import sovereign_agent
        from sovereign_agent.config import SETTINGS
        from sovereign_agent.loose_threads.sentinel import LooseThreadsSentinel

        s = LooseThreadsSentinel(data_dir=SETTINGS.paths.data_dir)
        report = s.scan()
        print(report.summary)
        for t in report.details.get("threads", [])[:40]:
            print(f"  {t['kind']:8} {t['symbol']}:{t['lineno']}")
        return 0
    if cmd == "disposition" and len(args) >= 3:
        from sovereign_agent.loose_threads import DispositionLedger

        rec = DispositionLedger().disposition(args[1], args[2], " ".join(args[3:]))
        print(f"  ✓ {rec['symbol']} → {rec['verdict']} {rec['reason']}")
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
