"""CLI for the apply queue + quarantine registry.

    python -m sovereign_agent.apply_queue status            # active queue + quarantine summary
    python -m sovereign_agent.apply_queue list              # active queue, in apply order
    python -m sovereign_agent.apply_queue enqueue a b c     # add modules (dependency-sequenced)
    python -m sovereign_agent.apply_queue next              # print the next module's slug (for the sequencer)
    python -m sovereign_agent.apply_queue mark <slug> <status>
    python -m sovereign_agent.apply_queue clear             # archive the queue log, reset
    python -m sovereign_agent.apply_queue quarantine list|show <slug>|clear <slug>

Read-only by default; mutating verbs (enqueue/mark/clear/quarantine) write the
durable queue/quarantine files only — never live ``src/``.
"""
from __future__ import annotations

import sys

from sovereign_agent.apply_queue.store import ApplyQueueStore, QuarantineRegistry


def _fmt_item(it) -> str:
    return f"  [{it.seq:>2}] {it.slug:<32} {it.status}"


def _cmd_status() -> int:
    q = ApplyQueueStore()
    qr = QuarantineRegistry()
    active = q.active()
    quar = qr.active()
    print(f"apply-queue: {len(active)} queued · {len(quar)} quarantined")
    if active:
        print("next up:")
        for it in active[:8]:
            print(_fmt_item(it))
    if quar:
        print("quarantined (need attention):")
        for r in quar:
            print(f"  · {r.slug:<32} {r.reason}")
    return 0


def _cmd_list() -> int:
    for it in ApplyQueueStore().active():
        print(_fmt_item(it))
    return 0


def _cmd_enqueue(slugs: list[str]) -> int:
    if not slugs:
        print("usage: apply_queue enqueue <slug> [slug...]", file=sys.stderr)
        return 2
    slugs = [s if s.startswith("aria-") else f"aria-{s}" for s in slugs]
    q = ApplyQueueStore()
    q.enqueue(slugs)
    print(f"queued {len(slugs)} module(s); active queue is now {len(q.active())}:")
    for it in q.active():
        print(_fmt_item(it))
    return 0


def _cmd_next() -> int:
    active = ApplyQueueStore().active()
    if not active:
        return 1  # empty — sequencer stops
    print(active[0].slug)
    return 0


def _cmd_mark(args: list[str]) -> int:
    if len(args) < 2:
        print("usage: apply_queue mark <slug> <queued|applying|applied|quarantined>", file=sys.stderr)
        return 2
    slug = args[0] if args[0].startswith("aria-") else f"aria-{args[0]}"
    ApplyQueueStore().mark(slug, args[1])  # type: ignore[arg-type]
    print(f"{slug} → {args[1]}")
    return 0


def _cmd_clear() -> int:
    ApplyQueueStore().clear()
    print("apply queue cleared (log archived).")
    return 0


def _cmd_quarantine(args: list[str]) -> int:
    qr = QuarantineRegistry()
    sub = args[0] if args else "list"
    if sub == "list":
        recs = qr.list()
        if not recs:
            print("quarantine: empty 💛")
            return 0
        for r in recs:
            mark = "✓ cleared" if r.status == "cleared" else "⛔ quarantined"
            print(f"  {mark}  {r.slug:<32} {r.reason}  ({r.failed_at})")
        return 0
    if sub == "show" and len(args) >= 2:
        slug = args[1] if args[1].startswith("aria-") else f"aria-{args[1]}"
        rec = qr.show(slug)
        if rec is None:
            print(f"no quarantine record for {slug}")
            return 1
        for k, v in rec.as_dict().items():
            print(f"  {k:<14} {v}")
        return 0
    if sub == "clear" and len(args) >= 2:
        slug = args[1] if args[1].startswith("aria-") else f"aria-{args[1]}"
        ok = qr.clear(slug)
        print(f"{slug}: {'cleared' if ok else 'no such record'}")
        return 0 if ok else 1
    if sub in ("add", "quarantine") and len(args) >= 3:
        slug = args[1] if args[1].startswith("aria-") else f"aria-{args[1]}"
        qr.quarantine(slug, " ".join(args[2:]))
        print(f"{slug} quarantined")
        return 0
    print("usage: apply_queue quarantine list|show <slug>|clear <slug>|add <slug> <reason>", file=sys.stderr)
    return 2


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    cmd = argv[0] if argv else "status"
    rest = argv[1:]
    dispatch = {
        "status": lambda: _cmd_status(),
        "list": lambda: _cmd_list(),
        "enqueue": lambda: _cmd_enqueue(rest),
        "next": lambda: _cmd_next(),
        "mark": lambda: _cmd_mark(rest),
        "clear": lambda: _cmd_clear(),
        "quarantine": lambda: _cmd_quarantine(rest),
    }
    fn = dispatch.get(cmd)
    if fn is None:
        print(__doc__)
        return 2
    return fn()


if __name__ == "__main__":
    raise SystemExit(main())
