"""maturity/reward_feed.py — let real, evidenced behavior move her mood. Nothing else.

Source: the existing reward ledger (`mem_channels/reward.py`), with its constrained vocabulary and
anti-egotism asymmetry (careful-uncertain rewarded, confident-wrong corrected). This module only
*reads* it and turns entries into small, bounded mood nudges:

- **Evidence or nothing.** An entry with no evidence text moves nothing. Good feelings come from
  things that really happened.
- **Diminishing returns.** The k-th entry of the same kind in a window counts 1/(k+1), so logging the
  same win again and again can't pump the mood (no reward farming).
- **Capped.** The total nudge to any dimension per update is at most ±MAX_TOTAL_NUDGE.
- **Mistakes without self-flagellation** (ARIA.md). Corrective entries raise concern at half the weight
  of a win and add a lesson note; they never zero out her satisfaction.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

NUDGE_PER_POINT = 0.01
MAX_TOTAL_NUDGE = 0.12
CORRECTIVE_WEIGHT = 0.5

# Which feelings a verified behavior feeds, beyond satisfaction.
EXTRA_DIMS: dict[str, tuple[str, ...]] = {
    "gap_found": ("curiosity",),
    "uncertainty_named": ("curiosity",),
    "research_completed": ("curiosity", "enthusiasm"),
    "conflict_resolved": ("care",),
    "operator_respected": ("care",),
    "solution_proposed": ("enthusiasm",),
    "self_correction": ("focus",),
    "boundary_held": ("care",),
}


@dataclass
class RewardFeed:
    nudges: dict[str, float] = field(default_factory=dict)
    wins: list[str] = field(default_factory=list)          # behavior kinds that counted, positive
    lessons: list[str] = field(default_factory=list)       # corrective kinds, framed as lessons
    ignored_unevidenced: int = 0


def reward_nudges(entries: list[dict]) -> RewardFeed:
    """Turn reward-ledger entries (dicts with behavior_kind, polarity, points, evidence) into nudges."""
    if not isinstance(entries, list):
        raise ValueError("entries must be a list of reward dicts")
    feed = RewardFeed()
    seen: Counter[str] = Counter()
    raw: dict[str, float] = {}
    for e in entries:
        kind = str(e.get("behavior_kind", ""))
        if not kind:
            continue
        if not str(e.get("evidence") or "").strip():
            feed.ignored_unevidenced += 1
            continue
        weight = 1.0 / (1 + seen[kind])
        seen[kind] += 1
        amount = abs(float(e.get("points", 0.0))) * NUDGE_PER_POINT * weight
        if e.get("polarity") == "corrective":
            raw["concern"] = raw.get("concern", 0.0) + amount * CORRECTIVE_WEIGHT
            if kind not in feed.lessons:
                feed.lessons.append(kind)
            continue
        raw["satisfaction"] = raw.get("satisfaction", 0.0) + amount
        for d in EXTRA_DIMS.get(kind, ()):
            raw[d] = raw.get(d, 0.0) + amount / 2
        if kind not in feed.wins:
            feed.wins.append(kind)
    feed.nudges = {d: round(max(-MAX_TOTAL_NUDGE, min(MAX_TOTAL_NUDGE, v)), 4) for d, v in raw.items()}
    capped = sorted(d for d, v in raw.items() if abs(v) > MAX_TOTAL_NUDGE)
    if feed.ignored_unevidenced or capped:
        from . import safe_emit_event

        safe_emit_event("maturity.rewards_limited", ignored_unevidenced=feed.ignored_unevidenced, capped=capped)
    return feed


def load_recent_rewards(hours: float = 24.0, *, now: datetime | None = None) -> list[dict]:
    """Best-effort read of the reward ledger's recent entries; [] if the ledger isn't available."""
    if hours <= 0:
        raise ValueError("hours must be > 0")
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=hours)
    try:
        from sovereign_agent.db import open_atoms_db
        from sovereign_agent.mem_channels.reward import RewardChannel

        conn = open_atoms_db()
        try:
            entries = RewardChannel(conn).list_recent(limit=200)
        finally:
            conn.close()
    except Exception:  # noqa: BLE001 — no ledger yet means no nudges, not an error
        return []
    out = []
    for r in entries:
        try:
            if datetime.fromisoformat(r.created_at.replace("Z", "+00:00")) < cutoff:
                continue
        except ValueError:
            continue
        out.append({"behavior_kind": r.behavior_kind, "polarity": r.polarity, "points": r.points,
                    "evidence": r.evidence, "created_at": r.created_at})
    return out
