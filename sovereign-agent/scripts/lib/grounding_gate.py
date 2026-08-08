"""scripts/lib/grounding_gate.py — run the grounding gate over a module's
own README, a file, or a literal string. (Grounding round · G2)

Works whether `sovereign_agent.grounding` is staged or already applied to
live src — same "works staged or live" discipline as scrutiny.py /
quality_gate.py.

    python3 scripts/lib/grounding_gate.py --module aria-foo   # aria-foo/README.md
    python3 scripts/lib/grounding_gate.py --file some.md
    python3 scripts/lib/grounding_gate.py --text "some text"
    python3 scripts/lib/grounding_gate.py --module aria-foo --json

Exit 0 on PASS/WARN, 1 on BLOCK — same worst-wins convention as
scrutiny.py/quality_gate.py, so pre_apply_gate.sh can OR the exit codes
together.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _find_repo_root(start: Path) -> Path:
    """Walk up looking for a stable repo-root marker — mirrors
    quality_gate.py's own walk-up exactly, for the same reason: a fixed
    parents[N] count breaks depending on staged vs. promoted location."""
    for candidate in (start, *start.parents):
        if (candidate / "src" / "sovereign_agent" / "cockpit" / "app.py").is_file():
            return candidate
    raise RuntimeError(f"could not locate repo root from {start}")


REPO = _find_repo_root(Path(__file__).resolve())
sys.path.insert(0, str(REPO / "scripts" / "lib"))


def _ensure_engine() -> None:
    """Make sovereign_agent.grounding.gate importable (staged or live) —
    mirrors quality_gate.py's _ensure_engine() exactly, checking the GATE
    submodule specifically (not just the parent package, which already
    imports fine once G1 is live and would short-circuit before G2's
    brand-new gate.py submodule is reachable)."""
    try:
        import sovereign_agent.grounding.gate  # noqa: F401
        return
    except Exception:
        pass
    from aria_conftest import extend_paths

    for mod in ("aria-grounding-ledger", "aria-grounding-gate"):
        p = REPO / mod
        if p.is_dir():
            extend_paths(p, subpkgs=("grounding",))


def _module_text(module: str) -> str:
    readme = REPO / module / "README.md"
    return readme.read_text(encoding="utf-8", errors="replace") if readme.is_file() else ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--module", default="")
    ap.add_argument("--file", default="")
    ap.add_argument("--text", default="")
    ap.add_argument("--confidence", type=float, default=None)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    _ensure_engine()
    from sovereign_agent.grounding.gate import gate

    text = args.text
    if args.file:
        text = Path(args.file).read_text(encoding="utf-8", errors="replace")
    elif args.module:
        text = _module_text(args.module)
    if not text and not (args.module or args.file or args.text):
        print("provide --module, --file, or --text")
        return 2

    verdict = gate(text, claimed_confidence=args.confidence)
    if args.json:
        print(json.dumps(verdict.as_dict(), indent=2))
    else:
        print("── Grounding Gate ──")
        print(f"   {verdict.render()}")
    return 1 if verdict.verdict == "BLOCK" else 0


if __name__ == "__main__":
    raise SystemExit(main())
