"""movie_dev_xp — the visible point system for Movie Studio work.

movie-studio-d (Kevin, 2026-07-28): same gamification doctrine as
game_dev_xp.py, applied to film production instead of game dev. Same
append-only NDJSON shape as success_patterns.py, and the same "never
hallucinates a number" discipline: deterministic, no LLM, every award is a
real named event with an honest note, not a magic score.

XP values are named constants, not hidden numbers:
  - XP_TREATMENT_DRAFTED   — a real treatment/script outline written
  - XP_STORYBOARD_GENERATED — a real storyboard/key-art still generated
  - XP_PITCH_ACCEPTED      — a drafted pitch was picked and became a project
  - XP_MILESTONE           — a real, judged milestone (the required `note`
                              explains why it counts)
  - XP_SHIPPED             — a real finished/shared cut

Storage: `<data>/movie_dev_xp.ndjson`, append-only, torn-line-resilient,
bounded on read — mirrors game_dev_xp.py exactly. Deliberately a SEPARATE
ledger from game_dev_xp.py (different craft, different XP curve) and from
the general aria_xp.py bar (that one drives the persistent cockpit
gamification strip, not per-project work) — never conflate the three.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path

__all__ = [
    "XPEvent",
    "XP_TREATMENT_DRAFTED",
    "XP_STORYBOARD_GENERATED",
    "XP_PITCH_ACCEPTED",
    "XP_MILESTONE",
    "XP_SHIPPED",
    "EVENT_TYPES",
    "xp_ledger_path",
    "award",
    "load_events",
    "total_xp",
    "level_for_xp",
    "progress_to_next",
    "recent_events",
    "XP_PER_LEVEL",
]

MAX_RECORDS = 5000  # read-window bound — the file may be longer

XP_TREATMENT_DRAFTED = 15
XP_STORYBOARD_GENERATED = 10
XP_PITCH_ACCEPTED = 20
XP_MILESTONE = 50
XP_SHIPPED = 250

EVENT_TYPES: dict[str, int] = {
    "treatment_drafted": XP_TREATMENT_DRAFTED,
    "storyboard_generated": XP_STORYBOARD_GENERATED,
    "pitch_accepted": XP_PITCH_ACCEPTED,
    "milestone": XP_MILESTONE,
    "shipped": XP_SHIPPED,
}

XP_PER_LEVEL = 250  # linear: level = xp // XP_PER_LEVEL + 1


@dataclass
class XPEvent:
    project_slug: str
    event_type: str
    xp: int
    note: str = ""
    ts: float = 0.0


def xp_ledger_path(data_dir: Path | None = None) -> Path:
    if data_dir is None:
        from sovereign_agent.config import SETTINGS
        data_dir = SETTINGS.paths.data_dir
    return Path(data_dir) / "movie_dev_xp.ndjson"


def award(project_slug: str, event_type: str, note: str = "",
          data_dir: Path | None = None) -> XPEvent:
    """Record one real XP event. Raises on an unknown event_type rather
    than silently awarding an arbitrary number."""
    if event_type not in EVENT_TYPES:
        raise ValueError(
            f"unknown event_type {event_type!r}; must be one of "
            f"{sorted(EVENT_TYPES)}"
        )
    if not (project_slug or "").strip():
        raise ValueError("award requires a project_slug")
    ev = XPEvent(
        project_slug=project_slug,
        event_type=event_type,
        xp=EVENT_TYPES[event_type],
        note=note.strip(),
        ts=time.time(),
    )
    path = xp_ledger_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(asdict(ev), ensure_ascii=False) + "\n")
    return ev


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


def total_xp(project_slug: str | None = None, data_dir: Path | None = None) -> int:
    """Grand total across all projects if project_slug is None, else just
    that project's total."""
    events = load_events(data_dir)
    if project_slug is not None:
        events = [e for e in events if e.project_slug == project_slug]
    return sum(e.xp for e in events)


def level_for_xp(xp: int) -> int:
    return max(1, xp // XP_PER_LEVEL + 1)


def progress_to_next(xp: int) -> tuple[int, int]:
    """(xp earned within the current level, xp needed for the next level)."""
    within = xp % XP_PER_LEVEL
    return within, XP_PER_LEVEL


def recent_events(n: int = 20, project_slug: str | None = None,
                  data_dir: Path | None = None) -> list[XPEvent]:
    events = load_events(data_dir)
    if project_slug is not None:
        events = [e for e in events if e.project_slug == project_slug]
    return events[-n:][::-1]  # most recent first
