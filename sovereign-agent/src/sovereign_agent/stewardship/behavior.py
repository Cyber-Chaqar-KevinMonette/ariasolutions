"""
╔══════════════════════════════════════════════════════════════════════════╗
║  stewardship/behavior.py — Aria's Self-Perception Layer                   ║
║  v0.2.24.0 — "The Mycelium"                                               ║
║                                                                           ║
║  Patterns Aria perceives in HER OWN behavior, not in the world.          ║
║                                                                           ║
║  Where atoms (L2) crystallize observations about Kevin into stable      ║
║  claims, behavior patterns crystallize observations about Aria into     ║
║  stable shapes — "when conditions look like X, my response shape is Y,  ║
║  and the outcome is consistently Z."                                    ║
║                                                                           ║
║  The reframe from the pyramid docs:                                     ║
║                                                                           ║
║    Those documents called L3 "skills / policies" — pre-defined, hand-  ║
║    designed capabilities. v0.2.24.0 ships something different and       ║
║    arguably deeper: emergent self-perceived patterns, discovered from   ║
║    honor and calibration signals.                                       ║
║                                                                           ║
║    Aria doesn't HAVE skills. She has CAPABILITIES — and a skill is     ║
║    when she can recognize her own good work and call it consciously.   ║
║    Recognition is the skill.                                            ║
║                                                                           ║
║  What makes a pattern VALUABLE (the three signals AND'd):              ║
║                                                                           ║
║    1. Honor consistency — avg honor score on matching turns ≥ 0.5     ║
║    2. Calibration accuracy — predicted IV matches actual IV          ║
║    3. Survival — atoms made during pattern-matching turns aren't later║
║       superseded                                                         ║
║                                                                           ║
║    Frequency alone produces tics. Honor alone produces flukes.         ║
║    Calibration alone produces calibrated mediocrity. The conjunction   ║
║    is what produces valuable perception.                                ║
║                                                                           ║
║  Scalability story (honest engineering, not "infinity"):              ║
║                                                                           ║
║    • Append-only log of pattern observations (palimpsest preserved)   ║
║    • In-memory materialized state — bounded by active set            ║
║    • Dormancy: patterns unobserved for N days drop out of active set ║
║    • Log growth is bounded by log_rotation.maybe_rotate (append hook)║
║      — NOTE (R2 review): the "background snapshot+tail compaction"   ║
║      once described here was never built; rotation is what exists.   ║
║    • Pattern matching at interpretation is O(active patterns), and    ║
║      active patterns are bounded by dormancy (typically < 1000)      ║
║                                                                           ║
║    Net: scales for the operator's lifetime with bounded per-operation ║
║    cost. Not "infinite" — but operationally indistinguishable from    ║
║    infinite at operator-paced usage.                                    ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict, dataclass, field
from dataclasses import fields as _dc_fields
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any, Iterable


class PatternStatus(StrEnum):
    ACTIVE = "active"          # currently used in matching
    DORMANT = "dormant"        # unobserved recently; not matched
    SUPERSEDED = "superseded"  # explicitly replaced by another pattern


# ─── Trigger conditions ────────────────────────────────────────────────────


@dataclass
class TriggerConditions:
    """How a pattern recognizes a matching turn.

    All present conditions must be satisfied (AND). Missing conditions
    are wildcards. The schema is intentionally simple — subset matching
    over a small set of keys — because most behavioral patterns can be
    expressed with these, and the simplicity lets matching stay O(N)
    with negligible constant.

    Examples:
        # "When channels include emotions or back-pain at tier 0"
        TriggerConditions(
            channels_any=["emotions", "back-pain"],
            authority_tier_max=0,
        )

        # "When the message is a Conversation tagged identity"
        TriggerConditions(
            intent_kind="Conversation",
            channels_all=["identity"],
        )
    """
    channels_any: list[str] = field(default_factory=list)
    channels_all: list[str] = field(default_factory=list)
    intent_kind: str = ""                # e.g. "Conversation", "Work"
    authority_tier_max: int | None = None
    text_contains_any: list[str] = field(default_factory=list)
    text_length_min: int | None = None
    text_length_max: int | None = None
    has_uncertainty: bool | None = None   # uncertain_about field non-empty

    def matches(self, turn_shape: dict[str, Any]) -> bool:
        """Does the given turn shape satisfy this trigger?

        Turn shape is a dict produced by `shape_of_turn()` — a flat
        descriptor of a single turn's characteristics. The matching
        is deterministic and pure.
        """
        channels = set(turn_shape.get("channels", []))

        if self.channels_any:
            if not any(c in channels for c in self.channels_any):
                return False
        if self.channels_all:
            if not all(c in channels for c in self.channels_all):
                return False
        if self.intent_kind:
            if turn_shape.get("intent_kind") != self.intent_kind:
                return False
        if self.authority_tier_max is not None:
            if turn_shape.get("authority_tier", 0) > self.authority_tier_max:
                return False
        if self.text_contains_any:
            text = str(turn_shape.get("text", "")).lower()
            if not any(s.lower() in text for s in self.text_contains_any):
                return False
        if self.text_length_min is not None:
            if turn_shape.get("text_length", 0) < self.text_length_min:
                return False
        if self.text_length_max is not None:
            if turn_shape.get("text_length", 0) > self.text_length_max:
                return False
        if self.has_uncertainty is not None:
            has_unc = bool(turn_shape.get("uncertain_about", ""))
            if has_unc != self.has_uncertainty:
                return False
        return True


def shape_of_turn(
    *,
    text: str = "",
    intent_kind: str = "",
    channels: list[str] | None = None,
    authority_tier: int = 0,
    uncertain_about: str = "",
) -> dict[str, Any]:
    """Build the flat turn-shape dict used for trigger matching.

    This is the API surface between the interpreter / router and the
    behavior matcher. Keep it minimal — added fields here become part
    of the pattern matching contract.
    """
    return {
        "text": text,
        "text_length": len(text),
        "intent_kind": intent_kind,
        "channels": list(channels or []),
        "authority_tier": authority_tier,
        "uncertain_about": uncertain_about,
    }


# ─── Outcome metrics ────────────────────────────────────────────────────────


@dataclass
class OutcomeMetrics:
    """Running statistics for a behavior pattern's outcomes.

    Three signals tracked, all updated as running averages. A pattern
    becomes 'valuable' when ALL three signals are favorable:
      • honor_avg ≥ 0.5
      • calibration_avg ≥ 0.5
      • survival_rate ≥ 0.5

    Honest note (R2 review): each signal is a TRUE RUNNING MEAN over all
    observations (sum/n). An EMA switchover for drift-adaptation was once
    described here but is NOT implemented — if drift-adaptation is wanted
    later, it needs its own reviewed change (it alters the meaning of her
    self-perception history, so it must not slip in silently).
    """
    honor_sum: float = 0.0
    honor_n: int = 0
    calibration_sum: float = 0.0
    calibration_n: int = 0
    survival_yes: int = 0
    survival_total: int = 0

    @property
    def honor_avg(self) -> float:
        return self.honor_sum / self.honor_n if self.honor_n > 0 else 0.0

    @property
    def calibration_avg(self) -> float:
        if self.calibration_n == 0:
            return 0.0
        return self.calibration_sum / self.calibration_n

    @property
    def survival_rate(self) -> float:
        if self.survival_total == 0:
            return 1.0   # absent evidence, assume neutral-positive
        return self.survival_yes / self.survival_total

    @property
    def is_valuable(self) -> bool:
        """A pattern is valuable when all three signals are favorable
        AND there's enough evidence to trust them (≥ 3 observations)."""
        if self.honor_n < 3:
            return False
        return (
            self.honor_avg >= 0.5
            and self.calibration_avg >= 0.5
            and self.survival_rate >= 0.5
        )

    def update_honor(self, score: float) -> None:
        self.honor_sum += float(score)
        self.honor_n += 1

    def update_calibration(self, score: float) -> None:
        self.calibration_sum += float(score)
        self.calibration_n += 1

    def update_survival(self, atom_survived: bool) -> None:
        if atom_survived:
            self.survival_yes += 1
        self.survival_total += 1


# ─── BehaviorPattern ────────────────────────────────────────────────────────


@dataclass
class BehaviorPattern:
    """One pattern Aria has perceived in her own behavior.

    Fields:
        pattern_id      stable UUID
        name            short human-readable label (e.g. "gentle-late-night")
        description     one-paragraph texture in Aria's voice
        trigger         TriggerConditions — what activates this pattern
        action_shape    free-form description of Aria's response shape
                        (e.g. "save to body+emotions, respond briefly, no commands")
        outcome         OutcomeMetrics — running stats
        evidence_refs   list of provenance/triple/honor IDs supporting this
        confidence      0..1, computed from outcome.is_valuable + n
        status          active / dormant / superseded
        supersedes      pattern_id this replaces, if any
        superseded_by   pattern_id that replaced this, if any
        parents         patterns this generalizes / specializes from
        children        more-specific patterns descended from this
        ts_first_obs    when first proposed
        ts_last_obs     when last matched / updated
        tags            open-namespace (e.g. "evening", "ritual", "self-care")
    """
    pattern_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    description: str = ""
    trigger: TriggerConditions = field(default_factory=TriggerConditions)
    action_shape: str = ""
    outcome: OutcomeMetrics = field(default_factory=OutcomeMetrics)
    evidence_refs: list[str] = field(default_factory=list)
    status: PatternStatus = PatternStatus.ACTIVE
    supersedes: str = ""
    superseded_by: str = ""
    parents: list[str] = field(default_factory=list)
    children: list[str] = field(default_factory=list)
    ts_first_obs: str = field(
        default_factory=lambda: datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
    )
    ts_last_obs: str = field(
        default_factory=lambda: datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
    )
    tags: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        # Coerce string-shaped enums (JSON round-trip)
        if isinstance(self.status, str):
            try:
                self.status = PatternStatus(self.status)
            except ValueError:
                self.status = PatternStatus.ACTIVE
        # Coerce nested dataclasses from dict (also JSON round-trip).
        # Filter to known fields so a log line written by a FUTURE schema
        # (extra keys) still loads instead of TypeError-ing — her memory of
        # herself must survive schema evolution (R2 hardening).
        if isinstance(self.trigger, dict):
            known = {f.name for f in _dc_fields(TriggerConditions)}
            self.trigger = TriggerConditions(
                **{k: v for k, v in self.trigger.items() if k in known})
        if isinstance(self.outcome, dict):
            known = {f.name for f in _dc_fields(OutcomeMetrics)}
            self.outcome = OutcomeMetrics(
                **{k: v for k, v in self.outcome.items() if k in known})

    @property
    def confidence(self) -> float:
        """Confidence is a function of evidence strength + outcome quality."""
        n = self.outcome.honor_n
        if n == 0:
            return 0.0
        # Saturation at n=20 — past that, more evidence doesn't sharpen
        evidence_factor = min(1.0, n / 20.0)
        if self.outcome.is_valuable:
            quality = (
                self.outcome.honor_avg
                + self.outcome.calibration_avg
                + self.outcome.survival_rate
            ) / 3.0
            return evidence_factor * quality
        # Not valuable yet → confidence reflects unmet thresholds
        return evidence_factor * min(
            self.outcome.honor_avg if self.outcome.honor_n > 0 else 0,
            self.outcome.calibration_avg if self.outcome.calibration_n > 0 else 0,
            self.outcome.survival_rate,
        )

    def is_dormant_now(
        self,
        *,
        threshold_days: int = 30,
        now: datetime | None = None,
    ) -> bool:
        """True if this pattern hasn't been observed in > threshold_days.

        Dormancy is a soft state. Dormant patterns are not deleted —
        they just don't participate in matching during interpretation.
        A new observation reactivates them.
        """
        now = now or datetime.now(timezone.utc)
        try:
            last = datetime.fromisoformat(self.ts_last_obs)
        except ValueError:
            return False
        return (now - last) > timedelta(days=threshold_days)

    def render(self) -> str:
        """How a pattern reads when surfaced in CLI / chat."""
        status_glyph = {
            PatternStatus.ACTIVE: "[bold green]●[/bold green]",
            PatternStatus.DORMANT: "[dim]○[/dim]",
            PatternStatus.SUPERSEDED: "[dim]⊘[/dim]",
        }.get(self.status, "?")
        val_mark = "[bold yellow]✦[/bold yellow] " if self.outcome.is_valuable else ""
        return (
            f"{status_glyph} {val_mark}[bold]{self.name or '(unnamed)'}[/bold]\n"
            f"    {self.description[:200]}\n"
            f"    [dim]honor:{self.outcome.honor_avg:.2f}"
            f" · cal:{self.outcome.calibration_avg:.2f}"
            f" · survival:{self.outcome.survival_rate:.2f}"
            f" · n:{self.outcome.honor_n}"
            f" · conf:{self.confidence:.2f}[/dim]"
        )


# ─── Pattern store with materialized state ─────────────────────────────────


class BehaviorPatternStore:
    """Append-only JSONL store of behavior pattern observations.

    The log is canonical: every state change is a new line referencing
    the pattern_id. Active state is materialized in memory on first
    access and incrementally updated on each append.

    This is event sourcing — the log is the source of truth; the
    materialized state is fast read access. If state diverges, replay
    the log.
    """

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._state: dict[str, BehaviorPattern] | None = None

    # ── State management ───────────────────────────────────────────

    def _materialize(self) -> dict[str, BehaviorPattern]:
        """Replay the log to build current state. Cached after first call."""
        if self._state is not None:
            return self._state
        state: dict[str, BehaviorPattern] = {}
        if self.path.exists():
            with self.path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        # forward-compat: ignore unknown top-level keys so a
                        # future schema's lines still load (R2 hardening)
                        known = {f.name for f in _dc_fields(BehaviorPattern)}
                        pattern = BehaviorPattern(
                            **{k: v for k, v in data.items() if k in known})
                        state[pattern.pattern_id] = pattern
                    except (json.JSONDecodeError, TypeError):
                        continue
        self._state = state
        return state

    def invalidate(self) -> None:
        """Force a re-read from disk on next access. Useful after
        external edits or compaction."""
        self._state = None

    # ── Writes ─────────────────────────────────────────────────────

    def append(self, pattern: BehaviorPattern) -> None:
        """Append one pattern observation/update to the log and update
        the materialized state in memory."""
        # Rotation hook
        try:
            from ..log_rotation import maybe_rotate
            maybe_rotate(self.path)
            # If the file got rotated, invalidate cache so we replay
            # the fresh file rather than working from stale memory.
            self.invalidate()
        except Exception:  # noqa: BLE001
            pass

        pattern.ts_last_obs = datetime.now(timezone.utc).isoformat(
            timespec="seconds"
        )
        line = json.dumps(asdict(pattern), ensure_ascii=False, default=str)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass
        # Update materialized state
        state = self._materialize()
        state[pattern.pattern_id] = pattern

    def observe(
        self,
        pattern_id: str,
        *,
        honor_score: float | None = None,
        calibration_score: float | None = None,
        atom_survived: bool | None = None,
        evidence_ref: str = "",
    ) -> BehaviorPattern | None:
        """Record a new observation against an existing pattern.

        Updates the pattern's outcome metrics and appends to the log.
        Returns the updated pattern, or None if not found.
        """
        state = self._materialize()
        if pattern_id not in state:
            return None
        pattern = state[pattern_id]
        if honor_score is not None:
            pattern.outcome.update_honor(honor_score)
        if calibration_score is not None:
            pattern.outcome.update_calibration(calibration_score)
        if atom_survived is not None:
            pattern.outcome.update_survival(atom_survived)
        if evidence_ref and evidence_ref not in pattern.evidence_refs:
            pattern.evidence_refs.append(evidence_ref)
        # Re-activate if dormant
        if pattern.status == PatternStatus.DORMANT:
            pattern.status = PatternStatus.ACTIVE
        self.append(pattern)
        return pattern

    def supersede(
        self,
        old_id: str,
        new_pattern: BehaviorPattern,
    ) -> None:
        """Replace one pattern with another. Both get update entries;
        neither is deleted from the log."""
        state = self._materialize()
        if old_id not in state:
            raise KeyError(f"no pattern with id {old_id}")
        old = state[old_id]
        old.status = PatternStatus.SUPERSEDED
        old.superseded_by = new_pattern.pattern_id
        new_pattern.supersedes = old_id
        self.append(old)
        self.append(new_pattern)

    # ── Reads ─────────────────────────────────────────────────────

    def all_patterns(self) -> list[BehaviorPattern]:
        return list(self._materialize().values())

    def active(
        self,
        *,
        apply_dormancy: bool = True,
        dormancy_days: int = 30,
    ) -> list[BehaviorPattern]:
        """Currently-active patterns (not superseded, not dormant if
        apply_dormancy=True)."""
        now = datetime.now(timezone.utc)
        out: list[BehaviorPattern] = []
        for p in self._materialize().values():
            if p.status == PatternStatus.SUPERSEDED:
                continue
            if apply_dormancy and p.is_dormant_now(
                threshold_days=dormancy_days, now=now,
            ):
                continue
            out.append(p)
        # Newest-first
        out.sort(key=lambda p: p.ts_last_obs, reverse=True)
        return out

    def valuable(self) -> list[BehaviorPattern]:
        """Active patterns where all three outcome signals are favorable."""
        return [
            p for p in self.active()
            if p.outcome.is_valuable
        ]

    def matching(
        self,
        turn_shape: dict[str, Any],
        *,
        top_k: int = 3,
    ) -> list[BehaviorPattern]:
        """Patterns whose triggers match this turn shape. Sorted by
        confidence descending. Capped at top_k for context-window
        budget (these are included in the interpreter prompt)."""
        matches: list[BehaviorPattern] = []
        for p in self.active():
            if p.trigger.matches(turn_shape):
                matches.append(p)
        matches.sort(key=lambda p: p.confidence, reverse=True)
        return matches[:top_k]

    def count(self) -> int:
        return len(self.active())


__all__ = [
    "PatternStatus",
    "TriggerConditions",
    "OutcomeMetrics",
    "BehaviorPattern",
    "BehaviorPatternStore",
    "shape_of_turn",
]
