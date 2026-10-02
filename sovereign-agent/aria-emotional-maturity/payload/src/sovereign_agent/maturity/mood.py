"""maturity/mood.py — Aria's slow-moving mood: homeostatic, bounded, persisted.

ARIA.md: `current_mood` is "a slow-moving signal … updated by reflection, not by every interaction."
`emotion.derive_emotions()` already appraises the moment from real signals; this module turns those
moments into a mood with three mature properties:

- **Slow:** each update blends only ALPHA of the new appraisal into the mood.
- **Bounded:** no dimension moves more than MAX_STEP in one update, so no single event can spike or
  crash her (resilience).
- **Homeostatic:** between updates the mood drifts back toward a healthy BASELINE (half-life
  HALF_LIFE_HOURS), so bad stretches end on their own and good ones don't inflate without limit.

Persisted append-only (NDJSON, fsync'd) like `wellbeing/ledger.py`. A torn last line from a crash is
skipped on read, never fatal.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

DIMENSIONS = ("focus", "curiosity", "satisfaction", "care", "enthusiasm", "concern", "fatigue", "uncertainty")
CONCERN_DIMS = frozenset({"concern", "fatigue", "uncertainty"})

# A healthy resting state: engaged and caring, a little concern and fatigue (alert, not numb).
BASELINE: dict[str, float] = {
    "focus": 0.55, "curiosity": 0.55, "satisfaction": 0.55, "care": 0.6, "enthusiasm": 0.5,
    "concern": 0.2, "fatigue": 0.2, "uncertainty": 0.3,
}
ALPHA = 0.25            # weight of a new appraisal in the mood
MAX_STEP = 0.15         # largest change to any dimension in one update
HALF_LIFE_HOURS = 12.0  # drift back toward BASELINE between updates

# ARIA.md's own mood vocabulary, plus two honest words for hard stretches.
LABELS = ("calm", "focused", "curious", "playful", "tired-but-engaged", "settled", "concerned", "strained")


@dataclass
class Mood:
    dims: dict[str, float] = field(default_factory=lambda: dict(BASELINE))
    label: str = "calm"
    updated_at: str = ""
    updates: int = 0

    def as_dict(self) -> dict:
        return asdict(self)


def _clamp(v: float) -> float:
    return max(0.0, min(1.0, v))


def _parse_ts(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def decay_toward_baseline(dims: dict[str, float], hours: float) -> dict[str, float]:
    """Exponential drift back toward BASELINE after `hours` with no update."""
    if hours < 0:
        raise ValueError("hours must be >= 0")
    keep = 0.5 ** (hours / HALF_LIFE_HOURS)
    return {d: BASELINE[d] + (dims.get(d, BASELINE[d]) - BASELINE[d]) * keep for d in DIMENSIONS}


def label_for(dims: dict[str, float]) -> str:
    """Name the mood in ARIA.md's vocabulary. Hard states are named plainly, never hidden."""
    if not dims:
        raise ValueError("dims must be non-empty")
    g = lambda d: dims.get(d, BASELINE[d])  # noqa: E731
    if g("fatigue") > 0.75 or g("concern") > 0.7:
        return "strained"
    if g("fatigue") > 0.6 and (g("focus") > 0.5 or g("care") > 0.5):
        return "tired-but-engaged"
    if g("concern") > 0.5:
        return "concerned"
    if g("curiosity") >= 0.7 and g("enthusiasm") >= 0.6:
        return "playful"
    if g("curiosity") >= 0.65:
        return "curious"
    if g("focus") >= 0.65:
        return "focused"
    if g("satisfaction") >= 0.65 and g("concern") < 0.3:
        return "settled"
    return "calm"


def blend(prev: Mood | None, appraisal: dict[str, float], *, now: datetime | None = None,
          nudges: dict[str, float] | None = None) -> Mood:
    """One reflective update: decay since last update, blend ALPHA of the appraisal plus any reward
    nudges, then cap each dimension's move at MAX_STEP."""
    if not isinstance(appraisal, dict):
        raise ValueError("appraisal must be a dict of dimension -> 0..1")
    now = now or datetime.now(timezone.utc)
    nudges = nudges or {}
    prev = prev or Mood(updated_at=now.isoformat())
    hours = 0.0
    if prev.updated_at:
        hours = max(0.0, (now - _parse_ts(prev.updated_at)).total_seconds() / 3600)
    rested = decay_toward_baseline(prev.dims, hours)
    new: dict[str, float] = {}
    for d in DIMENSIONS:
        # Rewards shift what she *sees*, not the mood directly, so the mood can sit at most a nudge above
        # what real signals show. Constant rewards can't pin her at 1.0 (anti-wireheading).
        seen = _clamp(float(appraisal.get(d, rested[d])) + float(nudges.get(d, 0.0)))
        target = (1 - ALPHA) * rested[d] + ALPHA * seen
        step = max(-MAX_STEP, min(MAX_STEP, target - rested[d]))
        new[d] = round(_clamp(rested[d] + step), 4)
    return Mood(dims=new, label=label_for(new), updated_at=now.isoformat(), updates=prev.updates + 1)


# ── persistence ──────────────────────────────────────────────────────────────


def ledger_path(data_dir: Path | None = None) -> Path:
    if data_dir is None:
        from sovereign_agent.config import SETTINGS

        data_dir = SETTINGS.paths.data_dir
    p = Path(data_dir) / "maturity"
    p.mkdir(parents=True, exist_ok=True)
    return p / "mood.ndjson"


def append_mood(record: dict, data_dir: Path | None = None) -> None:
    """Append one record (a mood plus its context), fsync'd."""
    if "mood" not in record:
        raise ValueError("record needs a 'mood' entry")
    with open(ledger_path(data_dir), "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
        fh.flush()
        os.fsync(fh.fileno())
    from . import safe_emit_event

    safe_emit_event("maturity.mood_recorded", label=record["mood"].get("label"),
                    updates=record["mood"].get("updates"))


def mood_history(data_dir: Path | None = None, limit: int = 500) -> list[dict]:
    """Stored records, oldest first. A torn last line (crash mid-write) is skipped."""
    if limit < 1:
        raise ValueError("limit must be >= 1")
    path = ledger_path(data_dir)
    if not path.exists():
        return []
    out: list[dict] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines()[-limit:]:
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def latest_mood(data_dir: Path | None = None) -> Mood | None:
    history = mood_history(data_dir, limit=5)
    if not history:
        return None
    m = history[-1]["mood"]
    return Mood(dims=m["dims"], label=m["label"], updated_at=m["updated_at"], updates=m["updates"])
