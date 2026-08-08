"""drills — exercises that are graded by RUNNING the code, plus the
spaced-repetition schedule that makes them stick.

Reading a lesson produces the feeling of learning. Writing code that passes
a test produces the thing itself. Every lesson that can have a drill has
one, and the drill is checked by executing the submission (see runner.py),
never by matching text.

Spaced repetition is the other half. A drill passed on Monday returns on
Thursday, then next week, then next month. Without it Kevin will feel
progress and retain very little; with it, one timestamp per drill buys most
of the retention literature's benefit.

Pure: scheduling and grading decisions are data -> data, so the whole thing
is testable without running a subprocess or waiting three days.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

__all__ = [
    "Drill", "DRILLS", "by_id", "for_track",
    "INTERVALS_DAYS", "next_interval_days", "schedule_after",
    "record_attempt", "due_drills", "progress", "state_path",
]

# Expanding intervals. The first is deliberately short — a drill you passed
# once and never saw again was entertainment, not learning.
INTERVALS_DAYS: tuple[float, ...] = (1.0, 3.0, 7.0, 21.0, 60.0)


@dataclass(frozen=True)
class Drill:
    id: str
    track: str
    lesson: str                    # the lesson this reinforces
    prompt: str                    # what to write
    starter: str = ""              # signature / skeleton shown to the learner
    tests: str = ""                # hidden pytest-style asserts, run by runner
    hint: str = ""
    tags: list[str] = field(default_factory=list)


DRILLS: list[Drill] = [
    Drill(
        id="fix-the-swallow",
        track="python", lesson="swallowed-exception",
        prompt="Write `safe_call(fn, log)` that calls `fn()` and returns its "
               "result. If `fn` raises, it must append the exception's "
               "*message* to the `log` list and return None — never let the "
               "exception escape, and never lose it silently.",
        starter="def safe_call(fn, log):\n    ...\n",
        tests="""
ok = safe_call(lambda: 42, [])
assert ok == 42, f"should return the value, got {ok!r}"

log = []
out = safe_call(lambda: (_ for _ in ()).throw(ValueError("boom")), log)
assert out is None, "a failing call must return None"
assert len(log) == 1, f"the failure must be recorded, log={log!r}"
assert "boom" in str(log[0]), f"record the message, got {log[0]!r}"
""",
        hint="try / except Exception as exc — append, then return None.",
    ),
    Drill(
        id="check-the-output",
        track="python", lesson="health-check-ignored-the-output",
        prompt="Write `is_healthy(bot)` for a dict with keys `sources` "
               "(int), `queue` (int) and `webhook` (str or None). It returns "
               "True only if the bot has at least one source AND a non-empty "
               "webhook. A bot that cannot deliver is NOT healthy, however "
               "good its internals look.",
        starter="def is_healthy(bot):\n    ...\n",
        tests="""
assert is_healthy({"sources": 3, "queue": 0, "webhook": "https://x"}) is True
assert is_healthy({"sources": 3, "queue": 0, "webhook": None}) is False, \\
    "no delivery target means it cannot possibly be healthy"
assert is_healthy({"sources": 3, "queue": 0, "webhook": ""}) is False, \\
    "an empty webhook is the same as none"
assert is_healthy({"sources": 0, "queue": 0, "webhook": "https://x"}) is False
""",
        hint="Both conditions matter. An empty string is falsy.",
    ),
    Drill(
        id="find-the-duplicate",
        track="python", lesson="duplicate-registration",
        prompt="Write `first_duplicate(names)` returning the first name that "
               "appears more than once, or None. This is the check that "
               "would have caught /buy being declared twice.",
        starter="def first_duplicate(names):\n    ...\n",
        tests="""
assert first_duplicate(["a", "b", "c"]) is None
assert first_duplicate(["buy", "level", "buy"]) == "buy"
assert first_duplicate([]) is None
assert first_duplicate(["x", "x", "y", "y"]) == "x", "FIRST duplicate"
""",
        hint="Track what you've seen; return as soon as one repeats.",
    ),
    Drill(
        id="validate-the-reference",
        track="python", lesson="phantom-role",
        prompt="Write `unknown_roles(config, known)` where `config` maps a "
               "channel name to a list of role names. Return a sorted list "
               "of every role mentioned that isn't in `known`. This is the "
               "check that would have caught the phantom 'Staff'.",
        starter="def unknown_roles(config, known):\n    ...\n",
        tests="""
known = {"Aria", "Support"}
assert unknown_roles({"admin": ["Aria", "Staff"]}, known) == ["Staff"]
assert unknown_roles({"admin": ["Aria"]}, known) == []
out = unknown_roles({"a": ["Ghost"], "b": ["Aria", "Phantom"]}, known)
assert out == ["Ghost", "Phantom"], f"sorted + deduped, got {out!r}"
assert unknown_roles({}, known) == []
""",
        hint="Collect into a set, then sort.",
    ),
    Drill(
        id="name-not-position",
        track="python", lesson="slice-assumed-position",
        prompt="Write `without(items, unwanted)` returning a list with every "
               "entry equal to `unwanted` removed, order preserved. The "
               "point: say what you mean by NAME. `items[1:]` would break "
               "the moment the order changed.",
        starter="def without(items, unwanted):\n    ...\n",
        tests="""
assert without(["TRACKERS", "WARFRAME", "OSRS"], "TRACKERS") == ["WARFRAME", "OSRS"]
got = without(["WARFRAME", "OSRS"], "TRACKERS")
assert got == ["WARFRAME", "OSRS"], f"absent target changes nothing, got {got!r}"
assert without(["A", "B", "A"], "A") == ["B"], "removes every occurrence"
assert without([], "X") == []
""",
        hint="A comprehension with a condition.",
    ),
    Drill(
        id="monotone-curve",
        track="python", lesson="curve-not-monotone",
        prompt="Write `is_monotone(costs)` returning True only if every "
               "entry is strictly greater than the one before it. This is "
               "the property test that caught the broken level curve.",
        starter="def is_monotone(costs):\n    ...\n",
        tests="""
assert is_monotone([50, 60, 70, 80]) is True
assert is_monotone([100, 60, 70]) is False, "the real bug: it dipped"
assert is_monotone([50, 50]) is False, "strictly greater, not equal"
assert is_monotone([5]) is True
assert is_monotone([]) is True
""",
        hint="Compare each pair with zip(costs, costs[1:]).",
    ),
    Drill(
        id="verify-at-destination",
        track="aisys", lesson="logs-are-not-truth",
        prompt="Write `really_delivered(run, channel_messages)`. `run` is a "
               "dict like {'sent': True, 'id': 'abc'}. `channel_messages` is "
               "a list of ids actually present at the destination. Return "
               "True only if the run claims sent AND the id is really there. "
               "Claiming success is not evidence of success.",
        starter="def really_delivered(run, channel_messages):\n    ...\n",
        tests="""
assert really_delivered({"sent": True, "id": "a"}, ["a", "b"]) is True
assert really_delivered({"sent": True, "id": "a"}, []) is False, \\
    "claimed sent but nothing arrived — the exact bug"
assert really_delivered({"sent": False, "id": "a"}, ["a"]) is False
assert really_delivered({}, ["a"]) is False, "missing keys must not crash"
""",
        hint="Use .get() so a malformed run is False rather than an exception.",
    ),
]

DRILLS_BY_ID = {d.id: d for d in DRILLS}


def by_id(drill_id: str) -> Drill | None:
    return DRILLS_BY_ID.get((drill_id or "").strip().lower())


def for_track(track: str) -> list[Drill]:
    return [d for d in DRILLS if d.track == (track or "").lower()]


# ── spaced repetition ───────────────────────────────────────────────────
def next_interval_days(streak: int) -> float:
    """Days until the next review after `streak` consecutive passes."""
    if streak <= 0:
        return INTERVALS_DAYS[0]
    return INTERVALS_DAYS[min(streak, len(INTERVALS_DAYS)) - 1]


def schedule_after(streak: int, *, now: float) -> float:
    return now + next_interval_days(streak) * 86400.0


# ── store ───────────────────────────────────────────────────────────────
def state_path(data_dir: Path) -> Path:
    p = Path(data_dir) / "code_school_progress.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _read(data_dir: Path) -> dict:
    path = state_path(data_dir)
    if not path.is_file():
        return {}
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:  # noqa: BLE001 — corrupt progress must never block a drill
        return {}


def _write(data_dir: Path, data: dict) -> None:
    path = state_path(data_dir)
    tmp = path.with_suffix(".json.tmp")
    try:
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        with open(tmp, "r+", encoding="utf-8") as fh:
            fh.flush()
            os.fsync(fh.fileno())
        tmp.replace(path)
    except Exception:  # noqa: BLE001
        pass


def record_attempt(data_dir: Path, drill_id: str, passed: bool, *,
                   now: float | None = None) -> dict:
    """Record one attempt and reschedule.

    A failure resets the streak to 0 and brings the drill back tomorrow —
    it does NOT erase history, because `attempts` and `passes` are what show
    honest progress. Struggling on something hard is learning, and the XP
    layer scores it accordingly.
    """
    now = time.time() if now is None else now
    data = _read(data_dir)
    rec = data.get(drill_id) or {"attempts": 0, "passes": 0, "streak": 0}
    rec["attempts"] = int(rec.get("attempts", 0)) + 1
    if passed:
        rec["passes"] = int(rec.get("passes", 0)) + 1
        rec["streak"] = int(rec.get("streak", 0)) + 1
    else:
        rec["streak"] = 0
    rec["last_ts"] = now
    rec["last_passed"] = bool(passed)
    rec["due_ts"] = schedule_after(rec["streak"], now=now)
    data[drill_id] = rec
    _write(data_dir, data)
    return rec


def due_drills(data_dir: Path, track: str | None = None, *,
               now: float | None = None) -> list[Drill]:
    """What to practise right now: never-attempted first, then overdue.

    New material before review is deliberate — a learner who opens the app
    and sees only repeats loses the thread of the course.
    """
    now = time.time() if now is None else now
    data = _read(data_dir)
    pool = for_track(track) if track else list(DRILLS)
    fresh = [d for d in pool if d.id not in data]
    due = [d for d in pool
           if d.id in data and float(data[d.id].get("due_ts", 0)) <= now]
    due.sort(key=lambda d: float(data[d.id].get("due_ts", 0)))
    return fresh + due


def progress(data_dir: Path, track: str | None = None) -> dict:
    data = _read(data_dir)
    pool = for_track(track) if track else list(DRILLS)
    done = [d for d in pool if int((data.get(d.id) or {}).get("passes", 0)) > 0]
    attempts = sum(int((data.get(d.id) or {}).get("attempts", 0)) for d in pool)
    return {"total": len(pool), "passed": len(done), "attempts": attempts,
            "remaining": len(pool) - len(done)}
