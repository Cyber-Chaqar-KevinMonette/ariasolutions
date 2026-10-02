"""maturity/checkin.py — one reflective check-in: appraise → reward → mood → regulate → inner voice.

Composes what already exists (`emotion.derive_emotions` for the honest appraisal of the moment, the
reward ledger for verified behavior) with this package's mood, regulation and report. The result's
`inner_voice` is a short block Aria (or a cloud model speaking as Aria) can carry in its system prompt.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .mood import Mood, append_mood, blend, latest_mood, mood_history
from .regulation import Regulation, regulate
from .report import MaturityReport, maturity_report
from .reward_feed import RewardFeed, load_recent_rewards, reward_nudges

INNER_VOICE_MAX_CHARS = 700
HONESTY_LINE = "Feelings never change facts: report results and problems plainly."


@dataclass
class CheckIn:
    mood: Mood
    appraisal: dict[str, float]
    signals: dict
    feed: RewardFeed
    regulations: list[Regulation]
    report: MaturityReport
    inner_voice: str
    persisted: bool = False
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "mood": self.mood.as_dict(), "appraisal": self.appraisal, "signals": self.signals,
            "wins": self.feed.wins, "lessons": self.feed.lessons,
            "ignored_unevidenced_rewards": self.feed.ignored_unevidenced,
            "regulations": [r.as_dict() for r in self.regulations],
            "maturity": self.report.as_dict(), "inner_voice": self.inner_voice, "persisted": self.persisted,
        }


def _consecutive_errors(events: list[dict]) -> int:
    streak = 0
    for e in reversed([e for e in events if "tool" in e.get("flag", "")][-10:]):
        if "-x" not in e.get("flag", ""):
            break
        streak += 1
    return streak


def inner_voice(mood: Mood, regulations: list[Regulation]) -> str:
    """A short, honest self-note for a system prompt. Bounded length; always ends with the honesty line."""
    if not regulations:
        raise ValueError("regulations must be non-empty")
    top = regulations[0]
    text = (f"Inner state (slow-moving, from real signals): {mood.label}. "
            f"Perspective: {top.perspective} Direction: {top.direction}")
    room = INNER_VOICE_MAX_CHARS - len(HONESTY_LINE) - 1
    return (text if len(text) <= room else text[: room - 1].rstrip() + "…") + " " + HONESTY_LINE


def emotional_checkin(*, events: list[dict] | None = None, rewards: list[dict] | None = None,
                      now: datetime | None = None, persist: bool = True, data_dir: Path | None = None,
                      open_objectives: int = 0) -> CheckIn:
    """Run one check-in. `events`/`rewards` default to Aria's real logs; pass them to test or replay."""
    if open_objectives < 0:
        raise ValueError("open_objectives must be >= 0")
    from sovereign_agent.emotion import _load_recent_events, derive_emotions

    now = now or datetime.now(timezone.utc)
    events = _load_recent_events(100) if events is None else events
    state = derive_emotions(events=events)
    signals = dict(state.signals, consecutive_errors=_consecutive_errors(events))
    feed = reward_nudges(load_recent_rewards(now=now) if rewards is None else rewards)
    mood = blend(latest_mood(data_dir), state.scores(), now=now, nudges=feed.nudges)
    regulations = regulate(mood.dims, signals, wins=feed.wins, lessons=feed.lessons,
                           open_objectives=open_objectives)
    voice = inner_voice(mood, regulations)
    record = {"mood": mood.as_dict(), "signals": {k: signals.get(k) for k in
              ("tool_event_count", "error_count", "error_rate", "commit_count", "consecutive_errors")},
              "wins": feed.wins, "lessons": feed.lessons, "strategy": regulations[0].strategy,
              "inner_voice": voice}   # read by cloud_persona so cloud models carry her current state
    persisted = False
    if persist:
        append_mood(record, data_dir)
        persisted = True
        from . import safe_emit_event  # best-effort emit_event

        safe_emit_event("maturity.checkin", label=mood.label, strategy=regulations[0].strategy)
    history = mood_history(data_dir) if persist else [*mood_history(data_dir), record]
    return CheckIn(mood, state.scores(), signals, feed, regulations, maturity_report(history), voice, persisted)
