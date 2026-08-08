"""success_patterns — she learns which workflows succeed, and matches new
goals against her own wins.

Kevin's ask: workflow-success pattern matching. Every finished work session
already leaves a review (review_journal) — this module distills the part
worth *matching on* into one NDJSON line per session:

    {ts, session_id, goal, tokens, outcome, subtasks_done, subtasks_total,
     duration_s}

and `match_goal("build a restock bot")` returns her top prior successes for
a similar goal — deterministic normalized-token overlap (Jaccard-style), no
LLM, so it works identically on a 7B model and never hallucinates a memory.

**Advisory only** (propose-don't-act): these patterns inform her and Kevin
("the last 3 times we did something like this, X worked"); they never
auto-select an approach. The chat bridge is "what usually works?".

Storage: `<data>/success_patterns.ndjson`, append-only, torn-line-resilient,
bounded on read (last MAX_RECORDS lines are considered).
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

__all__ = [
    "SuccessRecord",
    "record_outcome",
    "load_records",
    "match_goal",
    "compose_success_report",
    "is_success_query",
    "patterns_path",
]

MAX_RECORDS = 2000        # read-window bound — the file may be longer

_WORD_RE = re.compile(r"[a-z0-9]{3,}")
# words too common to carry signal between goals
_STOP = {"the", "and", "for", "with", "that", "this", "from", "into", "then",
         "them", "make", "build", "create", "add", "new", "her", "his", "our",
         "your", "please", "want", "need", "should", "would", "will", "can"}


@dataclass
class SuccessRecord:
    goal: str
    outcome: str                  # done | halted | failed | budget | unknown
    session_id: str = ""
    subtasks_done: int = 0
    subtasks_total: int = 0
    duration_s: float = 0.0
    tokens: list[str] = field(default_factory=list)
    ts: float = 0.0

    @property
    def succeeded(self) -> bool:
        return self.outcome == "done"


def patterns_path(data_dir: Path | None = None) -> Path:
    if data_dir is None:
        from sovereign_agent.config import SETTINGS
        data_dir = SETTINGS.paths.data_dir
    return Path(data_dir) / "success_patterns.ndjson"


def goal_tokens(goal: str) -> list[str]:
    """The matchable essence of a goal — lowered content words, deduped,
    order-preserving."""
    seen: list[str] = []
    for w in _WORD_RE.findall((goal or "").lower()):
        if w not in _STOP and w not in seen:
            seen.append(w)
    return seen


def _duration_s(created_at: str, updated_at: str) -> float:
    from datetime import datetime
    try:
        a = datetime.fromisoformat(created_at)
        b = datetime.fromisoformat(updated_at)
        return max(0.0, (b - a).total_seconds())
    except Exception:  # noqa: BLE001
        return 0.0


def record_outcome(session, data_dir: Path | None = None) -> SuccessRecord | None:
    """Distill one finished SessionState into a pattern record. Defensive
    getattr access; never raises (called from the session close-out path,
    which must not break — same contract as _write_session_review)."""
    try:
        goal = str(getattr(session, "goal", "") or "")
        if not goal.strip():
            return None
        subtasks = list(getattr(session, "subtasks", []) or [])
        done = sum(1 for s in subtasks
                   if str(getattr(s, "status", "")) == "done")
        status = str(getattr(session, "status", "") or "unknown")
        rec = SuccessRecord(
            goal=goal[:300],
            outcome=status if status in ("done", "halted", "failed", "budget")
            else ("done" if status == "completed" else status or "unknown"),
            session_id=str(getattr(session, "session_id", "") or ""),
            subtasks_done=done,
            subtasks_total=len(subtasks),
            duration_s=_duration_s(str(getattr(session, "created_at", "")),
                                   str(getattr(session, "updated_at", ""))),
            tokens=goal_tokens(goal),
            ts=time.time(),
        )
        path = patterns_path(data_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(asdict(rec), ensure_ascii=False) + "\n")
        return rec
    except Exception:  # noqa: BLE001
        return None


def load_records(data_dir: Path | None = None) -> list[SuccessRecord]:
    path = patterns_path(data_dir)
    if not path.is_file():
        return []
    out: list[SuccessRecord] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()[-MAX_RECORDS:]
    except Exception:  # noqa: BLE001
        return []
    known = {f for f in SuccessRecord(goal="x", outcome="done").__dict__}
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
            out.append(SuccessRecord(**{k: v for k, v in data.items() if k in known}))
        except Exception:  # noqa: BLE001 — torn line, skip
            continue
    return out


def match_goal(goal: str, *, data_dir: Path | None = None,
               top_k: int = 3) -> list[tuple[float, SuccessRecord]]:
    """Top prior SUCCESSES similar to this goal, scored by token overlap
    (|∩| / |∪| over content words). Deterministic; empty list when nothing
    clears a modest floor."""
    want = set(goal_tokens(goal))
    if not want:
        return []
    scored: list[tuple[float, SuccessRecord]] = []
    for rec in load_records(data_dir):
        if not rec.succeeded:
            continue
        have = set(rec.tokens)
        if not have:
            continue
        overlap = len(want & have)
        if overlap == 0:
            continue
        score = overlap / len(want | have)
        if score >= 0.15:
            scored.append((score, rec))
    scored.sort(key=lambda t: (t[0], t[1].ts), reverse=True)
    return scored[:top_k]


def _fmt_duration(s: float) -> str:
    if s <= 0:
        return "?"
    if s < 90:
        return f"{s:.0f}s"
    if s < 5400:
        return f"{s / 60:.0f}m"
    return f"{s / 3600:.1f}h"


def compose_success_report(goal: str = "", data_dir: Path | None = None) -> str:
    """Chat answer for 'what usually works?' — grounded in her real wins."""
    records = load_records(data_dir)
    if not records:
        return ("No workflow history distilled yet — as work sessions finish, "
                "I'll learn which approaches succeed and match new goals "
                "against my own wins.")
    wins = [r for r in records if r.succeeded]
    if goal.strip():
        matches = match_goal(goal, data_dir=data_dir)
        if not matches:
            return (f"Nothing in my {len(wins)} recorded win(s) looks like "
                    f"that goal yet — this would be new ground for us.")
        lines = [f"🧭 Prior wins that look like this ({len(matches)}):"]
        for score, rec in matches:
            lines.append(f"  • [b]{rec.goal[:70]}[/b] — "
                         f"{rec.subtasks_done}/{rec.subtasks_total} subtasks, "
                         f"{_fmt_duration(rec.duration_s)} "
                         f"[dim](similarity {score:.0%})[/dim]")
        lines.append("Advisory only — these inform, they never auto-pick.")
        return "\n".join(lines)
    rate = (100.0 * len(wins) / len(records)) if records else 0.0
    lines = [f"🧭 Workflow patterns: {len(records)} session(s) distilled, "
             f"{len(wins)} succeeded ({rate:.0f}%)."]
    for rec in wins[-3:][::-1]:
        lines.append(f"  • [b]{rec.goal[:70]}[/b] — "
                     f"{_fmt_duration(rec.duration_s)}, "
                     f"{rec.subtasks_done}/{rec.subtasks_total} subtasks")
    lines.append("Ask with a goal (e.g. 'what usually works for a restock "
                 "bot?') and I'll match it against my wins.")
    return "\n".join(lines)


# Precise, feature-specific triggers (lesson 16; verified by the collision
# matrix in tests/test_bridge_patterns.py).
_SUCCESS_TRIGGERS = (
    "what usually works", "what worked before", "what has worked",
    "success patterns", "workflow patterns", "past wins",
    "similar to before", "have we done this before", "done something like this",
)


def is_success_query(text: str) -> bool:
    if not text:
        return False
    from sovereign_agent.bridge_patterns import match_any
    return match_any(text, _SUCCESS_TRIGGERS)
