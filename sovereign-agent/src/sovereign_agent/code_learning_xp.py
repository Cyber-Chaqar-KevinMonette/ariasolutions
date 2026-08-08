"""code_learning_xp — visible progress for learning to code.

code-school-d (Kevin, 2026-08-04). Same shape as `game_dev_xp.py`:
append-only NDJSON, named constants rather than hidden numbers, and every
award tied to a real event with an honest note. Nothing here estimates or
guesses a score.

The weighting is the pedagogy, so it's stated plainly:

  XP_LESSON_READ (5)     — deliberately small. Reading is passive, and
                           rewarding it teaches the wrong loop. It counts,
                           barely.
  XP_DRILL_PASSED (25)   — you wrote code and it ran correctly. This is the
                           unit of actual learning.
  XP_DRILL_RECOVERED(35) — failed, then came back and passed. Worth MORE
                           than a first-try pass: the drills you struggle
                           with are the ones you're actually learning, and a
                           system that scores only clean successes quietly
                           teaches you to avoid hard things.
  XP_REVIEW_HELD (15)    — a spaced-repetition review passed days later.
                           Recall after forgetting is what retention is.
  XP_STREAK_DAY (20)     — a day with at least one drill. Showing up is the
                           whole game for a self-taught programmer.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

__all__ = [
    "XP_LESSON_READ", "XP_DRILL_PASSED", "XP_DRILL_RECOVERED",
    "XP_REVIEW_HELD", "XP_STREAK_DAY", "XP_PER_LEVEL",
    "award", "total_xp", "level_for", "recent_events", "summary",
    "ledger_path",
]

XP_LESSON_READ = 5
XP_DRILL_PASSED = 25
XP_DRILL_RECOVERED = 35
XP_REVIEW_HELD = 15
XP_STREAK_DAY = 20

XP_PER_LEVEL = 200          # linear, like game_dev_xp: level = xp // 200 + 1

_EVENT_XP = {
    "lesson_read": XP_LESSON_READ,
    "drill_passed": XP_DRILL_PASSED,
    "drill_recovered": XP_DRILL_RECOVERED,
    "review_held": XP_REVIEW_HELD,
    "streak_day": XP_STREAK_DAY,
}


def ledger_path(data_dir: Path) -> Path:
    p = Path(data_dir) / "code_learning_xp.ndjson"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def award(data_dir: Path, event_type: str, note: str = "", *,
          track: str = "", now: float | None = None) -> dict | None:
    """Append one real event. Unknown event types are REFUSED, not scored at
    a guess — an invented number is worse than no number."""
    xp = _EVENT_XP.get(event_type)
    if xp is None:
        return None
    rec = {"ts": time.time() if now is None else now, "event": event_type,
           "xp": xp, "track": track, "note": note}
    try:
        with open(ledger_path(data_dir), "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
    except Exception:  # noqa: BLE001 — a ledger hiccup must never block learning
        return rec
    return rec


def _events(data_dir: Path) -> list[dict]:
    path = ledger_path(data_dir)
    if not path.is_file():
        return []
    out = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:  # noqa: BLE001 — one bad line ≠ lose the ledger
                continue
    except Exception:  # noqa: BLE001
        return []
    return out


def total_xp(data_dir: Path, track: str | None = None) -> int:
    return sum(int(e.get("xp", 0)) for e in _events(data_dir)
               if not track or e.get("track") == track)


def level_for(xp: int) -> int:
    return max(0, int(xp or 0)) // XP_PER_LEVEL + 1


def recent_events(data_dir: Path, n: int = 10) -> list[dict]:
    return _events(data_dir)[-max(1, n):][::-1]


def summary(data_dir: Path, track: str | None = None) -> dict:
    evs = [e for e in _events(data_dir)
           if not track or e.get("track") == track]
    xp = sum(int(e.get("xp", 0)) for e in evs)
    counts: dict[str, int] = {}
    for e in evs:
        counts[e.get("event", "?")] = counts.get(e.get("event", "?"), 0) + 1
    return {"xp": xp, "level": level_for(xp), "events": len(evs),
            "by_event": counts,
            "into_level": xp % XP_PER_LEVEL,
            "to_next": XP_PER_LEVEL - (xp % XP_PER_LEVEL)}
