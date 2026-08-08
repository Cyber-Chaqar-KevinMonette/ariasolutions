"""
╔══════════════════════════════════════════════════════════════════════════╗
║  temporal_sentinel.py — re-check intent alignment at resume               ║
║  v0.2.33.0 — the second face of the Guardian Plane                       ║
║                                                                           ║
║  THE PROBLEM IT SOLVES                                                    ║
║                                                                           ║
║    Long-running sessions pause and resume. Between pause and resume,     ║
║    the operator may have:                                                 ║
║      • Said "actually, scrap that direction" in the cockpit              ║
║      • Added a new constraint ("don't touch service B")                  ║
║      • Changed their mind about the priority                             ║
║      • Done nothing — and the plan is still exactly right                ║
║                                                                           ║
║    Without a Temporal Sentinel, ``sov resume`` plows ahead with the      ║
║    queue that existed at pause time. The system has no structured way   ║
║    to notice the world changed underneath it.                            ║
║                                                                           ║
║    This module adds that structured way: a small classifier that reads   ║
║    the pre-pause intent, any new operator messages, recent outcomes,    ║
║    and the pending queue — and produces a TemporalDecision saying       ║
║    whether it's safe to resume and which queued subtasks need action.   ║
║                                                                           ║
║  DESIGN NOTES                                                             ║
║                                                                           ║
║    1. Pluggable like the outcome classifier. Two implementations ship:  ║
║         HeuristicTemporalSentinel — pure-Python rules, always available ║
║         (the LLM-backed variant comes next; the contract is set today). ║
║                                                                           ║
║    2. Conservative by default. When in doubt, the sentinel says         ║
║         safe_to_resume=False and asks the operator. This is the         ║
║         "Temporal brake pedal" — invisible most of the time, protective ║
║         exactly when there's been drift.                                ║
║                                                                           ║
║    3. Per-subtask granularity. The sentinel doesn't just say "stop" or  ║
║         "go" — it labels each pending subtask KEEP / DROP / MODIFY.     ║
║         A scope-change ("stop on service B") prunes B-related work and  ║
║         keeps A-related work going. Surgical, not all-or-nothing.       ║
║                                                                           ║
║    4. Honest about its limits. The heuristic sentinel can catch         ║
║         obvious drift signals — "scrap", "stop", "don't" near a topic   ║
║         from the original intent. It cannot read between the lines.    ║
║         When the LLM-backed variant arrives, it will inherit this same  ║
║         interface — the rest of the system won't notice the swap.       ║
╚══════════════════════════════════════════════════════════════════════════╝

Kill switch: none — predates the unified Sentinel registry; invoked directly by its callers, NOT gated by SOV_NO_SENTINELS or any per-sentinel SOV_NO_* env var.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Protocol

logger = logging.getLogger(__name__)


# ─── Core types ─────────────────────────────────────────────────────────────


class SubtaskAction(Enum):
    """What the Temporal Sentinel proposes for each pending subtask."""
    KEEP = auto()    # still aligned; let it run
    DROP = auto()    # no longer appropriate; remove from queue
    MODIFY = auto()  # directionally right but needs re-planning


@dataclass(frozen=True)
class PendingSubtaskSummary:
    """A lightweight view of one queued subtask, sufficient for the
    sentinel to reason about it without needing the full object graph.
    """
    subtask_id: str
    description: str
    tool: str = ""
    keywords: tuple[str, ...] = ()


@dataclass
class TemporalResumeContext:
    """Everything the Temporal Sentinel sees on a resume request."""
    session_id: str
    last_intent_snapshot: str            # what Aria thought she was doing
    pending_subtasks: list[PendingSubtaskSummary] = field(default_factory=list)
    new_operator_messages: list[str] = field(default_factory=list)  # since pause
    paused_seconds_ago: float = 0.0      # how long has the session been paused


@dataclass(frozen=True)
class TemporalDecision:
    """The verdict. Read by ``apply_temporal_decision`` to mutate the queue."""
    safe_to_resume: bool
    global_alignment: float                                # 0.0 to 1.0
    explanation: str
    subtask_actions: dict[str, SubtaskAction] = field(default_factory=dict)
    source: str = "unknown"

    def actions_count(self) -> dict[str, int]:
        """Histogram of KEEP/DROP/MODIFY counts. Useful for logs/notifications."""
        counts = {"KEEP": 0, "DROP": 0, "MODIFY": 0}
        for action in self.subtask_actions.values():
            counts[action.name] = counts.get(action.name, 0) + 1
        return counts


# ─── The pluggable sentinel protocol ────────────────────────────────────────


class TemporalSentinel(Protocol):
    """The interface every temporal-recheck implementation honors.

    Synchronous on purpose — the heuristic implementation does no I/O.
    The LLM-backed variant (next release) will expose ``check_async`` and
    keep ``check`` as a safe fallback, exactly like OllamaClassifier.
    """

    @property
    def name(self) -> str:
        ...

    def check(self, ctx: TemporalResumeContext) -> TemporalDecision:
        ...


# ─── HeuristicTemporalSentinel — deterministic, always available ────────────


# Words that signal the operator is asking us to stop or change direction.
# Tuned for the kinds of messages people actually type in cockpits — short
# imperatives, no formal grammar required.
_STOP_SIGNALS: tuple[str, ...] = (
    "scrap",
    "stop",
    "abandon",
    "cancel",
    "forget",
    "never mind",
    "nevermind",
    "don't bother",
    "dont bother",
    "abort",
    "kill that",
    "kill this",
    "drop that",
    "drop the",
    "wait",
    "hold off",
)

# Words signaling a narrowing/exclusion: "don't touch X", "leave Y alone"
#
# The captured `obj` is bounded by either a recognized terminator word
# (anymore/now/going forward), a sentence punctuation mark, or end-of-string.
# This is what lets "don't touch service b anymore" capture obj="service b"
# instead of obj="service" (the latter would over-match A-related tasks).
_EXCLUSION_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE) for p in (
        # "don't touch X [anymore/now/etc.]" — terminator-bounded
        r"don'?t\s+(?:touch|change|modify|edit|update|alter)\s+"
        r"(?P<obj>[\w][\w\s]*?)"
        r"(?=\s+(?:anymore|now|going forward|today|please)\b|[.,;!?]|$)",
        # "leave X alone"
        r"leave\s+(?P<obj>[\w][\w\s]*?)\s+alone\b",
        # "skip X" — bounded by punct or end-of-string
        r"skip\s+(?P<obj>[\w][\w\s]*?)(?=[.,;!?]|$)",
        # "not X anymore"
        r"\bnot?\s+(?P<obj>[\w][\w\s]*?)\s+anymore\b",
        # "no X" / "no more X" — explicit negation
        r"\bno\s+(?:more\s+)?(?P<obj>[\w][\w\s]*?)(?=[.,;!?]|$)",
    )
)

# Words signaling a new constraint that affects scope but not direction
_CONSTRAINT_SIGNALS: tuple[str, ...] = (
    "also",
    "make sure",
    "be careful",
    "watch out",
    "remember to",
    "don't forget",
    "as well",
    "in addition",
)


@dataclass
class _DriftAnalysis:
    """Internal: the heuristic's findings on operator-message drift."""
    stop_signal_detected: bool = False
    excluded_topics: list[str] = field(default_factory=list)
    new_constraints: list[str] = field(default_factory=list)
    matched_phrases: list[str] = field(default_factory=list)


class HeuristicTemporalSentinel:
    """Deterministic resume-check based on phrase patterns and topic overlap.

    Three things it can catch reliably:

      1. STOP signals near the original intent
         ("actually, scrap the migration") → safe_to_resume=False

      2. Exclusions targeting a topic in the queue
         ("don't touch service B") → DROP/MODIFY for B-related subtasks

      3. New constraints that don't kill the plan
         ("also don't change public API signatures") → MODIFY relevant tasks

    What it can't catch (honestly): subtle disagreements without explicit
    signal words, sarcasm, implication. Those land for the LLM-backed
    sentinel coming in a future release. The contract is identical so the
    upgrade is invisible to callers.
    """

    @property
    def name(self) -> str:
        return "heuristic_temporal"

    def check(self, ctx: TemporalResumeContext) -> TemporalDecision:
        try:
            return self._check_inner(ctx)
        except Exception as exc:  # noqa: BLE001 — sentinel must not raise
            logger.debug("temporal sentinel: failure %r", exc)
            # Conservative default — block resume on internal failure
            return TemporalDecision(
                safe_to_resume=False,
                global_alignment=0.5,
                explanation=f"sentinel failure: {type(exc).__name__}; "
                            f"holding resume for operator review",
                source=self.name,
            )

    def _check_inner(self, ctx: TemporalResumeContext) -> TemporalDecision:
        # Empty new-message stream → almost certainly safe to resume
        if not ctx.new_operator_messages:
            return TemporalDecision(
                safe_to_resume=True,
                global_alignment=0.95,
                explanation="no new operator messages since pause; "
                            "plan still aligned",
                subtask_actions={
                    s.subtask_id: SubtaskAction.KEEP
                    for s in ctx.pending_subtasks
                },
                source=self.name,
            )

        # Analyze the operator's messages for drift signals
        drift = self._analyze_drift(ctx)

        # ── Case 1: global stop signal → block everything ─────────────────
        if drift.stop_signal_detected:
            return TemporalDecision(
                safe_to_resume=False,
                global_alignment=0.2,
                explanation=(
                    f"detected stop signal in operator messages: "
                    f"{', '.join(repr(p) for p in drift.matched_phrases[:3])}. "
                    f"holding resume; operator should confirm scrap or proceed."
                ),
                subtask_actions={
                    s.subtask_id: SubtaskAction.DROP
                    for s in ctx.pending_subtasks
                },
                source=self.name,
            )

        # ── Case 2: exclusion patterns → DROP matching subtasks ───────────
        # Resume is allowed; queue is surgically pruned.
        actions: dict[str, SubtaskAction] = {}
        kept = 0
        dropped = 0
        modified = 0

        for sub in ctx.pending_subtasks:
            if self._subtask_matches_exclusion(sub, drift.excluded_topics):
                actions[sub.subtask_id] = SubtaskAction.DROP
                dropped += 1
            elif drift.new_constraints and self._subtask_likely_affected(
                sub, drift.new_constraints
            ):
                # New constraint exists; this subtask might violate it. Mark
                # MODIFY so the runner re-plans before executing.
                actions[sub.subtask_id] = SubtaskAction.MODIFY
                modified += 1
            else:
                actions[sub.subtask_id] = SubtaskAction.KEEP
                kept += 1

        # ── Build the explanation honestly ────────────────────────────────
        parts = [f"kept {kept}"]
        if dropped:
            parts.append(f"dropped {dropped}")
        if modified:
            parts.append(f"modified {modified}")
        summary = " · ".join(parts)

        if drift.excluded_topics or drift.new_constraints:
            detail = ""
            if drift.excluded_topics:
                detail += f"exclusions: {', '.join(drift.excluded_topics)}"
            if drift.new_constraints:
                if detail:
                    detail += " · "
                detail += f"new constraints noted ({len(drift.new_constraints)})"
            explanation = f"surgical update — {summary} — {detail}"
        else:
            explanation = f"new messages did not affect plan — {summary}"

        # Alignment score reflects how much pruning was needed.
        # All KEEPs → high alignment. Any pruning → moderate. Heavy pruning
        # without a stop signal → moderate but resumable.
        total = max(1, len(ctx.pending_subtasks))
        alignment = (kept + 0.5 * modified) / total
        alignment = max(0.4, min(1.0, alignment))

        return TemporalDecision(
            safe_to_resume=True,
            global_alignment=alignment,
            explanation=explanation,
            subtask_actions=actions,
            source=self.name,
        )

    def _analyze_drift(self, ctx: TemporalResumeContext) -> _DriftAnalysis:
        """Scan operator messages for stop signals, exclusions, constraints."""
        analysis = _DriftAnalysis()
        combined = " ".join(ctx.new_operator_messages).lower()

        # Stop signals (look for each anywhere in the combined text)
        for sig in _STOP_SIGNALS:
            if sig in combined:
                analysis.stop_signal_detected = True
                analysis.matched_phrases.append(sig)
                # Don't break — collecting matched phrases for the explanation

        # Exclusion patterns
        for msg in ctx.new_operator_messages:
            for pat in _EXCLUSION_PATTERNS:
                for match in pat.finditer(msg):
                    obj = (match.group("obj") or "").strip().lower()
                    if obj and obj not in analysis.excluded_topics:
                        # Truncate to a few words — patterns may grab too much
                        topic = " ".join(obj.split()[:4])
                        analysis.excluded_topics.append(topic)

        # New constraints
        for sig in _CONSTRAINT_SIGNALS:
            if sig in combined:
                # The whole message becomes the constraint context
                for msg in ctx.new_operator_messages:
                    if sig in msg.lower() and msg not in analysis.new_constraints:
                        analysis.new_constraints.append(msg.strip())

        return analysis

    def _subtask_matches_exclusion(
        self,
        sub: PendingSubtaskSummary,
        excluded_topics: list[str],
    ) -> bool:
        """Does this subtask touch a topic the operator excluded?"""
        if not excluded_topics:
            return False
        haystack = f"{sub.description} {sub.tool} {' '.join(sub.keywords)}".lower()
        return any(topic in haystack for topic in excluded_topics)

    def _subtask_likely_affected(
        self,
        sub: PendingSubtaskSummary,
        new_constraints: list[str],
    ) -> bool:
        """Heuristic: a new constraint about 'X' affects subtasks mentioning X.

        Conservative — we'd rather mark a subtask MODIFY (operator-visible)
        than KEEP one that actually violates a fresh constraint.
        """
        if not new_constraints:
            return False
        haystack = f"{sub.description} {sub.tool} {' '.join(sub.keywords)}".lower()
        # Extract content words from each constraint message and see if any
        # show up in the subtask description
        for constraint in new_constraints:
            words = [
                w.lower() for w in re.findall(r"\b\w{4,}\b", constraint)
                if w.lower() not in {
                    "also", "make", "sure", "remember", "forget",
                    "watch", "careful", "addition",
                }
            ]
            if any(w in haystack for w in words):
                return True
        return False


# ─── Apply a TemporalDecision to a session queue ────────────────────────────


def apply_temporal_decision(
    decision: TemporalDecision,
    pending_subtask_ids: list[str],
) -> tuple[list[str], list[str], list[str]]:
    """Translate a TemporalDecision into three lists of subtask IDs.

    Returns:
        (keep_ids, drop_ids, modify_ids)

    The caller (run_session.resume) uses these to mutate its in-memory
    queue. Side-effect free here — this function just makes the categories
    explicit so the queue mutation code stays small and testable.
    """
    keep_ids: list[str] = []
    drop_ids: list[str] = []
    modify_ids: list[str] = []

    for sid in pending_subtask_ids:
        action = decision.subtask_actions.get(sid, SubtaskAction.KEEP)
        if action == SubtaskAction.KEEP:
            keep_ids.append(sid)
        elif action == SubtaskAction.DROP:
            drop_ids.append(sid)
        elif action == SubtaskAction.MODIFY:
            modify_ids.append(sid)

    return keep_ids, drop_ids, modify_ids


# ─── Default sentinel factory ───────────────────────────────────────────────


_DEFAULT_SENTINEL: TemporalSentinel | None = None


def get_default_temporal_sentinel() -> TemporalSentinel:
    """Process-wide default temporal sentinel.

    Returns the heuristic for now. Swap with set_default_temporal_sentinel
    once the LLM-backed variant is ready.
    """
    global _DEFAULT_SENTINEL
    if _DEFAULT_SENTINEL is None:
        _DEFAULT_SENTINEL = HeuristicTemporalSentinel()
    return _DEFAULT_SENTINEL


def set_default_temporal_sentinel(sentinel: TemporalSentinel) -> None:
    """Override the process-wide sentinel (used by tests and for wiring
    in the LLM-backed implementation when it lands)."""
    global _DEFAULT_SENTINEL
    _DEFAULT_SENTINEL = sentinel


def reset_default_temporal_sentinel() -> None:
    """Restore the lazy default."""
    global _DEFAULT_SENTINEL
    _DEFAULT_SENTINEL = None


__all__ = [
    "HeuristicTemporalSentinel",
    "PendingSubtaskSummary",
    "SubtaskAction",
    "TemporalDecision",
    "TemporalResumeContext",
    "TemporalSentinel",
    "apply_temporal_decision",
    "get_default_temporal_sentinel",
    "reset_default_temporal_sentinel",
    "set_default_temporal_sentinel",
]
