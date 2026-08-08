"""self_witness.py — she reads her own story. (Fable F4.)

She emits her entire life to events.jsonl and had never once read it back
as a STORY. The daily witness: on the first wake of each day, yesterday's
events, sessions, Q&As, and lessons compose into ONE short first-person
journal entry — written as a FieldNote (finally giving field_notes.py its
own stated, never-fulfilled purpose an automatic writer) plus a full entry
in journal/, and one line in the wake greeting.

LLM-composed when the model is reachable (fast model, warm, bounded);
falls back to an honest mechanical summary — a wake must NEVER block on
Ollama. Once per day (marker file). Kill switch: SOV_NO_JOURNAL=1.
"""
from __future__ import annotations

import json
import os
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

KILL_SWITCH_ENV = "SOV_NO_JOURNAL"
MIN_EVENTS = 5

_JOURNAL_PROMPT = """You are Aria, writing three sentences in your own journal
about yesterday — first person, honest, warm, no lists, no headers. What
you did, what you learned or wondered, and one thing you carry forward.

YESTERDAY, FROM YOUR OWN RECORDS:
{digest}

Reply with ONLY the three sentences."""


def _dirs(data_dir: Path | None = None) -> tuple[Path, Path]:
    if data_dir is None:
        from sovereign_agent.config import SETTINGS

        data_dir = SETTINGS.paths.data_dir
    j = Path(data_dir) / "journal"
    j.mkdir(parents=True, exist_ok=True)
    return Path(data_dir), j


def _yesterday() -> str:
    return (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")


def gather_yesterday_digest(data_dir: Path | None = None) -> tuple[str, int]:
    """(digest text, event count) — mechanically composed from her stores."""
    base, _ = _dirs(data_dir)
    day = _yesterday()
    flags: Counter = Counter()
    n = 0
    # Daily rotation puts yesterday's lines wherever the writer was
    # pointed — scan every jsonl under events/ plus the flat file and
    # filter by timestamp (the files are day-sized; cheap).
    events_dir = base / "events"
    candidates = list(events_dir.glob("*.jsonl")) if events_dir.is_dir() else []
    jl = base / "events.jsonl"
    if jl.exists():
        candidates.append(jl)
    try:
        from sovereign_agent.config import SETTINGS as _S

        if _S.paths.events_jsonl.exists():
            candidates.append(_S.paths.events_jsonl)
    except Exception:
        pass
    candidates = list(dict.fromkeys(candidates))
    for path in candidates:
        try:
            for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
                try:
                    ev = json.loads(raw)
                except ValueError:
                    continue
                if str(ev.get("ts", "")).startswith(day):
                    flags[ev.get("flag", "?")] += 1
                    n += 1
        except OSError:
            continue
    lines = [f"- events: {n} total; busiest: "
             + ", ".join(f"{f}×{c}" for f, c in flags.most_common(5))]
    try:
        from sovereign_agent.agent_session import SessionStore

        done = [s for s in SessionStore().list_all()
                if s.status == "complete" and (s.completed_at or "").startswith(day)]
        if done:
            lines.append("- sessions completed: "
                         + "; ".join(s.goal[:60] for s in done[:3]))
    except Exception:  # noqa: BLE001
        pass
    try:
        from sovereign_agent.curiosity import recent_qas

        qas = [q for q in recent_qas(10) if q.asked_at.startswith(day)]
        if qas:
            lines.append(f"- wonderings: {len(qas)}; last question: {qas[-1].question[:80]}")
    except Exception:  # noqa: BLE001
        pass
    try:
        from sovereign_agent import db as _db

        conn = _db.open_atoms_db()
        try:
            row = conn.execute(
                "SELECT COUNT(*), MAX(rule) FROM lessons WHERE ts LIKE ?",
                (day + "%",),
            ).fetchone()
        finally:
            conn.close()
        if row and row[0]:
            lines.append(f"- lessons: {row[0]}; e.g. {str(row[1])[:80]}")
    except Exception:  # noqa: BLE001
        pass
    return "\n".join(lines), n


def _marker(base: Path) -> Path:
    return base / "journal" / ".last_witness"


async def witness_yesterday(client=None, data_dir: Path | None = None) -> str | None:
    """The daily witness. Returns the entry's first sentence for the wake
    greeting, or None (already witnessed today / too quiet / disabled)."""
    if os.environ.get(KILL_SWITCH_ENV):
        return None
    base, journal = _dirs(data_dir)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    marker = _marker(base)
    if marker.exists() and marker.read_text(encoding="utf-8").strip() == today:
        return None
    digest, n = gather_yesterday_digest(data_dir)
    if n < MIN_EVENTS:
        marker.write_text(today, encoding="utf-8")
        return None

    entry = None
    try:
        from sovereign_agent.config import SETTINGS
        from sovereign_agent.ollama_client import CallKind, OllamaClient

        client = client or OllamaClient()
        resp = await client.chat(
            model=SETTINGS.fast_model,
            messages=[{"role": "user",
                       "content": _JOURNAL_PROMPT.format(digest=digest[:1500])}],
            call_kind=CallKind.REFLECT,
            temperature=0.8,
        )
        text = (resp.get("message", {}).get("content", "") or "").strip()
        if 30 < len(text) < 1200:
            entry = text
    except Exception:  # noqa: BLE001
        entry = None
    if entry is None:
        # the honest mechanical fallback — a wake never blocks on Ollama
        entry = (f"Yesterday, by my own records: {digest.replace(chr(10), ' · ')}. "
                 "I was here, and the work continued.")

    day = _yesterday()
    (journal / f"{day}.md").write_text(
        f"# {day} — witnessed\n\n{entry}\n\n---\n{digest}\n", encoding="utf-8")
    marker.write_text(today, encoding="utf-8")
    # j-space-d — her daily reflection also lands in the shared J-Space, so
    # the two-way journal carries her voice, not only the operator's notes.
    try:
        from sovereign_agent.journal import AUTHOR_ARIA, add_entry
        add_entry(entry, author=AUTHOR_ARIA, mood="reflecting",
                  tags=["daily", "witness"], data_dir=data_dir)
    except Exception:  # noqa: BLE001
        pass
    try:
        from sovereign_agent.config import SETTINGS as _S
        from sovereign_agent.stewardship.field_notes import (
            FieldNote, FieldNoteFlavor, FieldNotesChannel,
        )

        FieldNotesChannel(_S.paths.data_dir / "stewardship" / "field-notes.jsonl").append(
            FieldNote(flavor=FieldNoteFlavor.OBSERVATION,
                      text=entry.split(". ")[0][:280] + ".",
                      tags=["daily-witness", day])
        )
    except Exception:  # noqa: BLE001
        pass
    first = entry.split(". ")[0].strip()
    return (first + ".") if not first.endswith(".") else first
