"""`python -m sovereign_agent.memory_compact` — audit / preview / run / cold.

Usage:
  python -m sovereign_agent.memory_compact audit
  python -m sovereign_agent.memory_compact preview <store> [days]
  python -m sovereign_agent.memory_compact run <store> [days]
  python -m sovereign_agent.memory_compact cold <store>

`sov compact ...` is the same machinery behind the cockpit-side CLI.
"""
from __future__ import annotations

import sys

from .compact import DEFAULT_BEFORE_DAYS


def render_audit(audit: dict) -> str:
    lines = [" store              records      MB   /day  compactable"]
    for s in audit["stores"]:
        mb = s["bytes"] / (1024 * 1024)
        can = "yes" if s["compactable"] else f"no — {s['reason']}"
        mark = " " if s["exists"] else "·"
        lines.append(f" {mark}{s['store_id']:<18}{s['records']:>8}  {mb:>6.2f}  "
                     f"{s['records_per_day']:>5}  {can}")
    j = audit["journal"]
    lines.append(f"  journal (dir)     {j['files']:>5} files  "
                 f"{j['bytes'] / (1024 * 1024):>6.2f}  bounded by design (1/day)")
    lines.append(f" ── total {audit['total_records']:,} records / "
                 f"{audit['total_bytes'] / (1024 * 1024):.2f} MB ──")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    cmd = argv[0] if argv else "audit"
    if cmd == "audit":
        from .stores import audit_all

        print(render_audit(audit_all()))
        return 0
    if cmd in ("preview", "run") and len(argv) >= 2:
        from . import compact as engine

        store = argv[1]
        days = int(argv[2]) if len(argv) > 2 else DEFAULT_BEFORE_DAYS
        try:
            if cmd == "preview":
                plan = engine.preview(store, before_days=days)
                print(f" would move {plan.to_move}/{plan.total_records} records "
                      f"(< {plan.cutoff}) into {len(plan.periods)} cold month(s): "
                      f"{plan.periods} · ~{plan.bytes_to_move / 1024:.1f} KiB "
                      f"({plan.unparseable_kept_hot} undatable stay hot)")
            else:
                result = engine.run(store, before_days=days)
                print(f" moved {result.moved} · kept {result.kept} hot · "
                      f"periods {result.periods}")
                if result.backup:
                    print(f" reversible: backup at {result.backup}")
        except engine.CompactError as exc:
            print(f" REFUSED: {exc}")
            return 1
        return 0
    if cmd == "cold" and len(argv) >= 2:
        from pathlib import Path

        from sovereign_agent.config import SETTINGS

        from .compact import iter_cold_records
        from .stores import REGISTRY

        spec = REGISTRY.get(argv[1])
        if spec is None:
            print(f" unknown store {argv[1]!r}")
            return 1
        store_dir = (Path(SETTINGS.paths.data_dir) / spec.rel_path).parent
        n = 0
        for rec in iter_cold_records(argv[1], store_dir):
            n += 1
        print(f" {n} record(s) in cold storage for {argv[1]!r} — verbatim, on disk")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
