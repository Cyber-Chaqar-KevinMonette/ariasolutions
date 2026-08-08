"""CLI for the Universal Scanner Kernel.

    python -m sovereign_agent.universal_scanner check --what "..." [--who NAME] [--intent "..."]
        [--domain DOMAIN] [--tool NAME]... [--reversible true|false] [--requires-consent]
        [--consent-given] [--json]

Runs kernel_check() only (layer 1, no I/O) — for the full fan-out (layer 2), call
`sovereign_agent.universal_scanner.run()` from Python with a data_dir/repo_root.
Exit 0 = PASS, 1 = SOFT_FAIL_RETRY, 2 = HARD_FAIL_BLOCK.
"""
from __future__ import annotations

import argparse
import json
import sys

from sovereign_agent.universal_scanner import OperationDescriptor, kernel_check


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m sovereign_agent.universal_scanner")
    sub = parser.add_subparsers(dest="cmd", required=True)

    check = sub.add_parser("check", help="run kernel_check() on a described operation")
    check.add_argument("--what", required=True)
    check.add_argument("--who", default="operator")
    check.add_argument("--intent", default="")
    check.add_argument("--domain", default="")
    check.add_argument("--tool", action="append", dest="tools", default=[])
    check.add_argument("--reversible", choices=("true", "false"), default=None)
    check.add_argument("--requires-consent", action="store_true")
    check.add_argument("--consent-given", action="store_true")
    check.add_argument("--json", action="store_true")

    args = parser.parse_args(argv)

    op = OperationDescriptor(
        who=args.who,
        what=args.what,
        intent=args.intent,
        domain=args.domain,
        tools=tuple(args.tools),
        reversible=None if args.reversible is None else args.reversible == "true",
        requires_consent=args.requires_consent,
        consent_given=args.consent_given,
    )
    result = kernel_check(op)

    if args.json:
        print(json.dumps({"verdict": result.verdict, "reasons": result.reasons}, indent=2))
    else:
        print(result.summary())

    return {"PASS": 0, "SOFT_FAIL_RETRY": 1, "HARD_FAIL_BLOCK": 2}[result.verdict]


if __name__ == "__main__":
    sys.exit(main())
