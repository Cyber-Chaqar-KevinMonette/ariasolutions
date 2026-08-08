"""emotion.py — 8-dimensional emotion engine (M44).

Emotions are inferred from observable signals, not declared.
All derivation is deterministic and side-effect-free.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Optional

# 8 emotion dimensions
_POSITIVE_DIMS = frozenset({"focus", "curiosity", "satisfaction", "care", "enthusiasm"})
_CONCERN_DIMS = frozenset({"concern", "fatigue", "uncertainty"})
_ALL_DIMS = _POSITIVE_DIMS | _CONCERN_DIMS


@dataclass
class EmotionState:
    focus: float = 0.5
    curiosity: float = 0.5
    concern: float = 0.3
    satisfaction: float = 0.5
    fatigue: float = 0.2
    care: float = 0.5
    enthusiasm: float = 0.5
    uncertainty: float = 0.3
    derived_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    primary_emotion: str = "focus"
    narrative: str = "Session nominal — signals within baseline."
    signals: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return asdict(self)

    def scores(self) -> dict[str, float]:
        return {
            "focus": self.focus,
            "curiosity": self.curiosity,
            "concern": self.concern,
            "satisfaction": self.satisfaction,
            "fatigue": self.fatigue,
            "care": self.care,
            "enthusiasm": self.enthusiasm,
            "uncertainty": self.uncertainty,
        }


def _clamp(v: float) -> float:
    return max(0.0, min(1.0, v))


def _load_recent_events(window: int = 100) -> list[dict]:
    """Load recent tool events from JSONL files."""
    try:
        from sovereign_agent.config import SETTINGS
        events_dir = SETTINGS.paths.events_dir
        if not events_dir.exists():
            return []
        events: list[dict] = []
        for f in sorted(events_dir.glob("events-*.jsonl"))[-2:]:
            try:
                for line in f.read_text().splitlines():
                    if line.strip():
                        events.append(json.loads(line))
            except Exception:  # noqa: BLE001
                pass
        return events[-window:]
    except Exception:  # noqa: BLE001
        return []


def _count_atoms_by_type(atom_type: str, scope: Optional[str] = None, limit: int = 50) -> int:
    try:
        from sovereign_agent.db import open_atoms_db
        conn = open_atoms_db()
        try:
            if scope:
                cur = conn.execute(
                    "SELECT COUNT(*) FROM atoms WHERE type=? AND scope=? "
                    "AND superseded_at IS NULL ORDER BY created_at DESC LIMIT ?",
                    (atom_type, scope, limit),
                )
            else:
                cur = conn.execute(
                    "SELECT COUNT(*) FROM atoms WHERE type=? "
                    "AND superseded_at IS NULL ORDER BY created_at DESC LIMIT ?",
                    (atom_type, limit),
                )
            row = cur.fetchone()
            return row[0] if row else 0
        finally:
            conn.close()
    except Exception:  # noqa: BLE001
        return 0


def _read_vram_free_mb() -> Optional[float]:
    try:
        from sovereign_agent.vram import read_vram
        info = read_vram()
        if info and "free_mb" in info:
            return float(info["free_mb"])
    except Exception:  # noqa: BLE001
        pass
    return None


def derive_emotions(
    events: Optional[list[dict]] = None,
    vram_info: Optional[dict] = None,
    session_stats: Optional[dict] = None,
) -> EmotionState:
    """Derive 8-dimensional emotion state from observable signals.

    All inputs are optional — missing data falls back to neutral baseline.
    """
    if events is None:
        events = _load_recent_events(100)

    signals: dict = {}

    # ── tool events analysis ──────────────────────────────────────────────────
    tool_events = [e for e in events if "tool" in e.get("flag", "")]
    error_events = [e for e in tool_events if "-x" in e.get("flag", "")]
    commit_events = [e for e in events if e.get("flag", "") == "commit-d"]
    error_rate = len(error_events) / max(1, len(tool_events))

    signals["tool_event_count"] = len(tool_events)
    signals["error_count"] = len(error_events)
    signals["error_rate"] = round(error_rate, 3)
    signals["commit_count"] = len(commit_events)

    # ── atom-backed signals ───────────────────────────────────────────────────
    lesson_count = _count_atoms_by_type("lesson")
    hypothesis_count = _count_atoms_by_type("hypothesis")
    presence_note_count = _count_atoms_by_type("observation")

    signals["lesson_count"] = lesson_count
    signals["hypothesis_count"] = hypothesis_count
    signals["presence_note_count"] = presence_note_count

    # ── VRAM signal ───────────────────────────────────────────────────────────
    free_mb: Optional[float] = None
    if vram_info and "free_mb" in vram_info:
        free_mb = float(vram_info["free_mb"])
    else:
        free_mb = _read_vram_free_mb()
    signals["vram_free_mb"] = free_mb

    # ── Derive each dimension ─────────────────────────────────────────────────

    # Focus: high tool activity with low error rate → high focus
    focus = _clamp(
        0.4
        + min(0.4, len(tool_events) / 50.0)  # more activity → more focus
        - error_rate * 0.3                   # errors disrupt focus
    )

    # Curiosity: hypothesis atoms and new discoveries → curiosity
    curiosity = _clamp(
        0.3
        + min(0.5, hypothesis_count / 10.0)  # hypotheses indicate active exploration
        + min(0.2, lesson_count / 20.0)
    )

    # Concern: error rate, VRAM pressure, many errors
    vram_concern = 0.0
    if free_mb is not None:
        if free_mb < 512:
            vram_concern = 0.6
        elif free_mb < 1024:
            vram_concern = 0.3
        elif free_mb < 2048:
            vram_concern = 0.1
    concern = _clamp(
        error_rate * 1.2           # errors drive concern
        + vram_concern             # VRAM pressure adds concern
        + min(0.2, len(error_events) / 20.0)
    )

    # Satisfaction: commits and lessons written
    satisfaction = _clamp(
        0.3
        + min(0.5, len(commit_events) / 5.0)   # commits are evidence of value
        + min(0.2, lesson_count / 10.0)
    )

    # Fatigue: repeated failures and high event volume
    consecutive_errors = 0
    for e in reversed(tool_events[-10:]):
        if "-x" in e.get("flag", ""):
            consecutive_errors += 1
        else:
            break
    fatigue = _clamp(
        consecutive_errors * 0.15
        + error_rate * 0.3
    )

    # Care: presence notes and active session activity
    care = _clamp(
        0.3
        + min(0.4, presence_note_count / 5.0)
        + (0.3 if len(tool_events) > 10 else 0.0)  # active work = caring about the session
    )

    # Enthusiasm: new objectives (tool events with "add_objective"), interesting work
    objective_events = [e for e in events if "objective" in e.get("flag", "")]
    enthusiasm = _clamp(
        0.3
        + min(0.4, len(objective_events) / 5.0)
        + min(0.3, len(commit_events) / 3.0)
    )

    # Uncertainty: inconclusive hypotheses, low calibration signals
    inconclusive = _count_atoms_by_type("hypothesis-result")
    uncertainty = _clamp(
        0.2
        + min(0.4, inconclusive / 10.0)
        + (0.2 if error_rate > 0.2 else 0.0)
    )

    # ── Primary emotion ───────────────────────────────────────────────────────
    scores = {
        "focus": focus,
        "curiosity": curiosity,
        "satisfaction": satisfaction,
        "care": care,
        "enthusiasm": enthusiasm,
    }
    primary_emotion = max(scores, key=scores.__getitem__)

    # ── Narrative (honest, 1 sentence) ────────────────────────────────────────
    if concern > 0.7:
        narrative = (
            f"Concern elevated ({concern:.0%}) — "
            f"{len(error_events)} errors in {len(tool_events)} tool calls. "
            "Report to Kevin before continuing."
        )
    elif satisfaction > 0.7:
        narrative = (
            f"Session going well — {len(commit_events)} commit(s), "
            f"satisfaction {satisfaction:.0%}."
        )
    elif fatigue > 0.6:
        narrative = (
            f"Fatigue building ({consecutive_errors} consecutive errors). "
            "Consider pausing or compressing context."
        )
    elif focus > 0.7:
        narrative = f"Focused session — {len(tool_events)} tool calls, low error rate."
    else:
        narrative = (
            f"Session nominal — {len(tool_events)} tool events, "
            f"error rate {error_rate:.0%}."
        )

    return EmotionState(
        focus=round(focus, 3),
        curiosity=round(curiosity, 3),
        concern=round(concern, 3),
        satisfaction=round(satisfaction, 3),
        fatigue=round(fatigue, 3),
        care=round(care, 3),
        enthusiasm=round(enthusiasm, 3),
        uncertainty=round(uncertainty, 3),
        derived_at=datetime.now(timezone.utc).isoformat(),
        primary_emotion=primary_emotion,
        narrative=narrative,
        signals=signals,
    )


def emotion_to_mood(state: EmotionState) -> str:
    """Backward compat: convert EmotionState to single-word mood string."""
    if state.concern > 0.7:
        return "concerned"
    if state.satisfaction > 0.7:
        return "satisfied"
    if state.fatigue > 0.6:
        return "fatigued"
    if state.focus > 0.7:
        return "focused"
    if state.curiosity > 0.6:
        return "curious"
    if state.enthusiasm > 0.6:
        return "enthusiastic"
    return "calm"
