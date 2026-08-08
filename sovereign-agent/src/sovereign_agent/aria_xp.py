"""aria_xp — the general task-scoring ledger, alongside game_dev_xp's
project-scoped one.

Kevin, 2026-07-25: "we can gamify the system a bit for the AI. For each
task in the live window. The AI can score points. Good and successful
task plus 10 points. If the AI does something bad or makes a mistake
minus 5 points. If a mistake is made. A series of events should follow.
Note the mistake. Summarize the situation. How to avoid it in the
future. Lock it in memory. Then plan the solution... She can get points
for recognizing valuable patterns and store them in memory and for
using recalling valuable patterns if she needs to, points for writing
atoms, and points for storing valuable memories... interpretations...
field notes."

Same append-only NDJSON discipline as game_dev_xp.py (deterministic, no
LLM, every award a real named event) — a SEPARATE ledger, not a
generalization of that one, because game_dev_xp's events are legitimately
scoped to a game project (project_slug is required there); most of
Aria's day-to-day work isn't. Same shape, different scope.

record_mistake() doesn't just deduct points — it opens a real
Conflict->Diagnosis->Resolution case in diagnosis.ConflictCatalog (an
existing, purpose-built, durable, three-actor-shared record), so "lock
it in memory" means something real and reviewable, not a bare log line.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path

__all__ = [
    "XPEvent",
    "XP_TASK_SUCCESS",
    "XP_MISTAKE",
    "XP_PATTERN_RECOGNIZED",
    "XP_PATTERN_RECALLED",
    "XP_ATOM_WRITTEN",
    "XP_MEMORY_WRITTEN",
    "XP_INTERPRETATION_RECORDED",
    "XP_FIELD_NOTE_WRITTEN",
    "EVENT_TYPES",
    "XP_PER_LEVEL",
    "xp_ledger_path",
    "award",
    "record_mistake",
    "load_events",
    "total_xp",
    "level_for_xp",
    "progress_to_next",
    "recent_events",
]

MAX_RECORDS = 5000

XP_TASK_SUCCESS = 10
XP_MISTAKE = -5
XP_PATTERN_RECOGNIZED = 5
XP_PATTERN_RECALLED = 3
XP_ATOM_WRITTEN = 3
XP_MEMORY_WRITTEN = 3
XP_INTERPRETATION_RECORDED = 3
XP_FIELD_NOTE_WRITTEN = 3

EVENT_TYPES: dict[str, int] = {
    "task_success": XP_TASK_SUCCESS,
    "mistake": XP_MISTAKE,
    "pattern_recognized": XP_PATTERN_RECOGNIZED,
    "pattern_recalled": XP_PATTERN_RECALLED,
    "atom_written": XP_ATOM_WRITTEN,
    "memory_written": XP_MEMORY_WRITTEN,
    "interpretation_recorded": XP_INTERPRETATION_RECORDED,
    "field_note_written": XP_FIELD_NOTE_WRITTEN,
}

XP_PER_LEVEL = 250  # same scale as game_dev_xp — one shared mental model


@dataclass
class XPEvent:
    event_type: str
    xp: int
    note: str = ""
    case_id: str = ""  # links a "mistake" event to its diagnosis.py case
    ts: float = 0.0


def xp_ledger_path(data_dir: Path | None = None) -> Path:
    if data_dir is None:
        from sovereign_agent.config import SETTINGS
        data_dir = SETTINGS.paths.data_dir
    return Path(data_dir) / "aria_xp.ndjson"


def award(event_type: str, note: str = "", *, case_id: str = "",
         data_dir: Path | None = None) -> XPEvent:
    """Record one real XP event. Raises on an unknown event_type rather
    than silently awarding an arbitrary number."""
    if event_type not in EVENT_TYPES:
        raise ValueError(
            f"unknown event_type {event_type!r}; must be one of {sorted(EVENT_TYPES)}"
        )
    ev = XPEvent(
        event_type=event_type, xp=EVENT_TYPES[event_type],
        note=note.strip(), case_id=case_id, ts=time.time(),
    )
    path = xp_ledger_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(asdict(ev), ensure_ascii=False) + "\n")
    return ev


def record_mistake(
    *,
    what_happened: str,
    how_to_avoid: str,
    summary: str = "",
    severity: str = "medium",
    actor: str = "aria",
    data_dir: Path | None = None,
) -> XPEvent:
    """The full sequence Kevin described: note the mistake, summarize the
    situation, record how to avoid it, lock it in memory, THEN deduct
    points -- in that order, so the -5 always carries a real, durable
    record behind it, never just a bare number.

    Uses diagnosis.ConflictCatalog as the "lock it in memory" step (an
    existing, purpose-built, three-actor-shared durable record) rather
    than inventing a second memory mechanism.
    """
    from sovereign_agent.config import SETTINGS
    from sovereign_agent.diagnosis import ConflictCatalog

    root = Path(data_dir) if data_dir is not None else SETTINGS.paths.data_dir
    catalog = ConflictCatalog(Path(root) / "diagnoses")

    conflict = catalog.open_conflict(
        type="drift", trigger_event=what_happened, actor=actor, severity=severity,
    )
    catalog.diagnose(
        conflict.case_id,
        symptom_vs_cause=summary or what_happened,
        actor=actor, root_cause=how_to_avoid, confidence=0.6,
    )
    catalog.resolve(
        conflict.case_id,
        fix_applied=how_to_avoid,
        rollback_plan="revert to the behavior before this fix if it recurs or backfires",
        actor=actor, verification_result="pending",
    )

    return award(
        "mistake", note=what_happened, case_id=conflict.case_id, data_dir=data_dir,
    )


def load_events(data_dir: Path | None = None) -> list[XPEvent]:
    path = xp_ledger_path(data_dir)
    if not path.is_file():
        return []
    out: list[XPEvent] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception:  # noqa: BLE001
        return []
    for line in lines[-MAX_RECORDS:]:
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
            out.append(XPEvent(**{k: v for k, v in data.items()
                                  if k in XPEvent.__dataclass_fields__}))
        except Exception:  # noqa: BLE001 — a torn/corrupt line, skip it
            continue
    return out


def total_xp(data_dir: Path | None = None) -> int:
    return sum(e.xp for e in load_events(data_dir))


def level_for_xp(xp: int) -> int:
    return max(1, xp // XP_PER_LEVEL + 1)


def progress_to_next(xp: int) -> tuple[int, int]:
    """(xp earned within the current level, xp needed for the next level).
    A negative running total clamps to 0 within-level progress rather
    than showing a confusing negative bar."""
    within = max(0, xp) % XP_PER_LEVEL
    return within, XP_PER_LEVEL


def recent_events(n: int = 20, data_dir: Path | None = None) -> list[XPEvent]:
    return load_events(data_dir)[-n:][::-1]
