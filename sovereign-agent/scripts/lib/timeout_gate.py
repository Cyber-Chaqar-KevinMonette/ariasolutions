"""scripts/lib/timeout_gate.py — run the timeout gate over recent events.
(Timeout round · T2)

Works whether `sovereign_agent.timeouts` is staged or already applied to
live src — same "works staged or live" discipline as the other gate
CLIs. Unlike quality_gate/grounding_gate/integrity_gate, this gate does
not take --module/--file/--text — it checks the shared event log
directly, so it takes no positional target at all.

    python3 scripts/lib/timeout_gate.py
    python3 scripts/lib/timeout_gate.py --json

Exit 0 on PASS/WARN, 1 on BLOCK — same worst-wins convention as the other
gate CLIs, so pre_apply_gate.sh can OR the exit codes together.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _find_repo_root(start: Path) -> Path:
    for candidate in (start, *start.parents):
        if (candidate / "src" / "sovereign_agent" / "cockpit" / "app.py").is_file():
            return candidate
    raise RuntimeError(f"could not locate repo root from {start}")


REPO = _find_repo_root(Path(__file__).resolve())
sys.path.insert(0, str(REPO / "scripts" / "lib"))


def _ensure_engine() -> None:
    try:
        import sovereign_agent.timeouts.gate  # noqa: F401
        return
    except Exception:
        pass
    from aria_conftest import extend_paths

    for mod in ("aria-timeout-ledger", "aria-timeout-gate"):
        p = REPO / mod
        if p.is_dir():
            extend_paths(p, subpkgs=("timeouts",))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    _ensure_engine()
    from sovereign_agent.timeouts.gate import gate

    verdict = gate()
    if args.json:
        print(json.dumps(verdict.as_dict(), indent=2))
    else:
        print("── Timeout Gate ──")
        print(f"   {verdict.render()}")
    return 1 if verdict.verdict == "BLOCK" else 0


if __name__ == "__main__":
    raise SystemExit(main())
