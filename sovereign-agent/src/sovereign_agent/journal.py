"""journal — the J-Space: Aria's reflective journal, and a two-way space.

Kevin's ask: "give her a nice J-Space for her to leverage." Distinct from
everything nearby:
  • self_witness  — an auto-generated daily "yesterday" digest
  • field-notes   — operational observations (a memory channel)
  • review journal — per-work-session records (what/how/verify)

The J-Space is none of those. It's a durable, dated, human-readable
JOURNAL where **she** writes free reflections not tied to any task, and
**you** can write back — a genuine two-way space, a relationship, not a log.

Storage: an append-only NDJSON at `<data>/journal/journal.ndjson`, one
entry per line: {id, ts, author, text, mood, tags}. Simple, durable,
greppable, easy to back up. Pure add/read/render; the reliability-critical
part (the store) is trivially testable.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

__all__ = [
    "add_entry",
    "recent_entries",
    "render_journal",
    "journal_path",
    "is_journal_read_query",
    "is_journal_write_command",
    "AUTHOR_ARIA",
    "AUTHOR_HUMAN",
]

AUTHOR_ARIA = "aria"
AUTHOR_HUMAN = "kevin"

_READ_TRIGGERS = (
    "read your journal", "show me your journal", "what's in your journal",
    "whats in your journal", "your journal", "read the journal",
    "show your journal", "open your journal", "j-space", "jspace",
    "what have you been reflecting", "your reflections",
)


def journal_path(data_dir: Path | None = None) -> Path:
    if data_dir is None:
        from sovereign_agent.config import SETTINGS
        data_dir = SETTINGS.paths.data_dir
    return Path(data_dir) / "journal" / "journal.ndjson"


def _new_id() -> str:
    import uuid
    return "j" + uuid.uuid4().hex[:10]


def add_entry(
    text: str,
    *,
    author: str = AUTHOR_ARIA,
    mood: str = "",
    tags: list[str] | None = None,
    data_dir: Path | None = None,
) -> dict:
    """Append one journal entry. fsync'd so a reflection is never half-lost."""
    entry = {
        "id": _new_id(),
        "ts": datetime.now(timezone.utc).isoformat(),
        "author": (author or AUTHOR_ARIA).strip().lower()[:32] or AUTHOR_ARIA,
        "text": (text or "").strip(),
        "mood": (mood or "").strip()[:40],
        "tags": [str(t).strip()[:40] for t in (tags or []) if str(t).strip()][:8],
    }
    path = journal_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        fh.flush()
        os.fsync(fh.fileno())
    return entry


def recent_entries(limit: int = 20, data_dir: Path | None = None) -> list[dict]:
    """The most recent entries, newest last (chronological). Never raises."""
    path = journal_path(data_dir)
    if not path.is_file():
        return []
    out: list[dict] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:  # noqa: BLE001 — skip a corrupt line, never fail
                continue
    except Exception:  # noqa: BLE001
        return []
    return out[-limit:]


def _fmt_ts(ts: str) -> str:
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:  # noqa: BLE001
        return ts[:16]


def render_journal(entries: list[dict]) -> str:
    """A warm, readable render of journal entries (her voice + yours)."""
    if not entries:
        return ("My journal is empty so far. This is my J-Space — a place for "
                "reflections, not tasks. Say `/journal <your words>` to write "
                "in it with me, and I'll add my own reflections too. 💛")
    lines = ["◊ **J-Space** — our journal", ""]
    for e in entries:
        who = e.get("author", "aria")
        mark = "🖊" if who == AUTHOR_ARIA else "💬"
        when = _fmt_ts(e.get("ts", ""))
        mood = e.get("mood", "")
        head = f"{mark} **{who}** · [dim]{when}[/dim]" + (f" · _{mood}_" if mood else "")
        lines.append(head)
        for para in (e.get("text", "") or "(empty)").split("\n"):
            lines.append(f"  {para}")
        tags = e.get("tags") or []
        if tags:
            lines.append("  [dim]" + " ".join(f"#{t}" for t in tags) + "[/dim]")
        lines.append("")
    return "\n".join(lines)


def is_journal_read_query(text: str) -> bool:
    if not text:
        return False
    from sovereign_agent.bridge_patterns import match_any
    return match_any(text, _READ_TRIGGERS)


def is_journal_write_command(text: str) -> tuple[bool, str]:
    """Detect an explicit 'write this in your journal: <text>' request from
    the human. Returns (True, entry_text) or (False, '')."""
    if not text:
        return False, ""
    t = text.strip()
    low = t.lower()
    for prefix in ("write in your journal", "journal this", "add to your journal",
                   "note in your journal", "journal:"):
        if low.startswith(prefix):
            body = t[len(prefix):].lstrip(" :–-").strip()
            if body:
                return True, body
    return False, ""
