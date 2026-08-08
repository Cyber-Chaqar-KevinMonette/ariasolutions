"""handoff.py — never-empty-handed continuity.

Kevin, 2026-08-02: "make sure it never /clears and ends up empty handed. "
"But it prepares its own handoff documents... for when she /clears... "
"She must always come back not empty-handed, but prepared to continue "
"working strong." Codified as doctrine in mos_canon.py's
mos-proactive-handoff / mos-continuity-of-care clauses; this module is
the mechanism those clauses describe.

Reuses compression.py's existing event classifier (HIGH-VALUE preserved
verbatim / MEDIUM summarized / LOW just counted) — exactly the shape of
a good handoff, not a new summarization algorithm. `min_age_seconds=0`
is passed deliberately: compress_events' default 300s "safety margin"
exists to avoid compressing events that might still be settling in a
LONG-RUNNING background process; a handoff is the opposite case — we
explicitly want everything from the current session, including the last
few seconds, captured now.

Two halves:
  write_handoff()          — called before a /clear wipes anything.
  latest_unread_handoff()  — called on cockpit mount; surfaced once,
                              then marked read so it doesn't repeat.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .compression import compress_events

__all__ = [
    "handoffs_dir", "render_handoff_markdown", "write_handoff",
    "latest_unread_handoff", "mark_handoff_read",
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def handoffs_dir(data_dir: Path) -> Path:
    d = Path(data_dir) / "handoffs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _pointer_path(data_dir: Path) -> Path:
    return handoffs_dir(data_dir) / "_latest_unread.json"


def render_handoff_markdown(events: list[dict[str, Any]], *, reason: str = "") -> str:
    """Pure — no I/O. What actually gets written to the handoff file."""
    ctx = compress_events(events, min_age_seconds=0)
    lines = [
        f"# Handoff — {_now_iso()}",
        "",
        f"Reason: {reason or 'session cleared'}",
        f"Events considered: {ctx.preserved_count + ctx.compressed_count}",
        "",
        ctx.summary,
        "",
        "---",
        "She comes back from this not empty-handed — read the HIGH-VALUE "
        "section above before assuming a shared frame; nothing here "
        "replaces re-establishing intent with the operator directly "
        "(mos-continuity-of-care).",
    ]
    return "\n".join(lines)


def write_handoff(data_dir: Path, events: list[dict[str, Any]], *,
                  reason: str = "") -> Path:
    """Write a real handoff before a session is cleared. Returns the file
    path. Sets the unread pointer so the next boot surfaces it once."""
    from ulid import ULID

    out_dir = handoffs_dir(data_dir)
    path = out_dir / f"handoff-{ULID()!s}.md"
    text = render_handoff_markdown(events, reason=reason)

    tmp = path.with_suffix(".md.tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)

    pointer = _pointer_path(data_dir)
    pointer.write_text(
        json.dumps({"path": str(path), "read": False, "written_at": _now_iso()}),
        encoding="utf-8",
    )
    return path


def latest_unread_handoff(data_dir: Path) -> Path | None:
    """The most recent handoff not yet surfaced, or None. Never raises —
    a missing/corrupt pointer just means nothing pending."""
    pointer = _pointer_path(data_dir)
    if not pointer.is_file():
        return None
    try:
        data = json.loads(pointer.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if data.get("read"):
        return None
    path = Path(data.get("path", ""))
    return path if path.is_file() else None


def mark_handoff_read(data_dir: Path) -> None:
    """Idempotent — safe to call even if nothing is pending."""
    pointer = _pointer_path(data_dir)
    if not pointer.is_file():
        return
    try:
        data = json.loads(pointer.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return
    data["read"] = True
    tmp = pointer.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    tmp.replace(pointer)
