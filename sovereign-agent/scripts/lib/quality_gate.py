"""scripts/lib/quality_gate.py — run the quality gate over a module or a
file list. (Quality round · Q2)

Works whether `sovereign_agent.quality` is staged or already applied to
live src — same "works staged or live" discipline as scrutiny.py.

    python3 scripts/lib/quality_gate.py --module aria-foo   # payload/src/**/*.py
    python3 scripts/lib/quality_gate.py --paths a.py b.py
    python3 scripts/lib/quality_gate.py --module aria-foo --json

Exit 0 on PASS/WARN, 1 on BLOCK — same worst-wins convention as
scrutiny.py, so pre_apply_gate.sh can OR the two exit codes together.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

def _find_repo_root(start: Path) -> Path:
    """Walk up looking for a stable repo-root marker. A fixed parents[N]
    count breaks depending on where this file currently lives — staged
    (aria-quality-gate/payload/scripts/lib/quality_gate.py, 4 levels down)
    vs. promoted (scripts/lib/quality_gate.py, 2 levels down) — caught
    live when the staged copy silently resolved REPO to its own payload
    dir. Mirrors the exact walk-up test_apply_system.py already uses for
    the same reason."""
    for candidate in (start, *start.parents):
        if (candidate / "src" / "sovereign_agent" / "cockpit" / "app.py").is_file():
            return candidate
    raise RuntimeError(f"could not locate repo root from {start}")


REPO = _find_repo_root(Path(__file__).resolve())
sys.path.insert(0, str(REPO / "scripts" / "lib"))


def _ensure_engine() -> None:
    """Make sovereign_agent.quality.gate importable (staged or live) —
    mirrors scrutiny.py's _ensure_engines(). Checks the GATE submodule
    specifically, not just the parent package: `sovereign_agent.quality`
    already imports fine once Q1 is live, which would short-circuit this
    check before Q2's gate.py (a brand-new submodule) is reachable."""
    try:
        import sovereign_agent.quality.gate  # noqa: F401
        return
    except Exception:
        pass
    from aria_conftest import extend_paths

    for mod in ("aria-quality-sentinel", "aria-quality-gate"):
        p = REPO / mod
        if p.is_dir():
            extend_paths(p, subpkgs=("quality",))


def _module_targets(module: str) -> list[Path]:
    mod = REPO / module
    payload = mod / "payload" / "src" / "sovereign_agent"
    if payload.is_dir():
        return list(payload.rglob("*.py"))
    return []


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--module", default="")
    ap.add_argument("--paths", nargs="*", default=[])
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    _ensure_engine()
    from sovereign_agent.quality.gate import gate

    targets: list[Path] = [Path(p) for p in args.paths]
    if args.module:
        targets += _module_targets(args.module)
    if not targets:
        print("provide --module or --paths")
        return 2

    verdict = gate(targets)
    if args.json:
        print(json.dumps(verdict.as_dict(), indent=2))
    else:
        print("── Quality Gate ──")
        print(f"   {verdict.render()}")
    return 1 if verdict.verdict == "BLOCK" else 0


if __name__ == "__main__":
    raise SystemExit(main())
