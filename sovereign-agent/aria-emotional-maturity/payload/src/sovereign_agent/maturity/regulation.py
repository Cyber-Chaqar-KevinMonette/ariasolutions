"""maturity/regulation.py — mature emotion regulation: honest perspective + productive direction.

When a feeling runs high or low, pick a named strategy from emotion-regulation practice (pacing,
problem-focused coping, cognitive reappraisal, humility check, savoring, re-engagement, accepting
uncertainty) and return:

- a **perspective**: a kinder, wider, *true* way to see the moment. Every number in it comes from the
  evidence dict beside it; it never invents a win or shrinks a problem.
- a **direction**: the next productive step, from a FIXED catalog. Regulation suggests; it never creates
  goals (DEFERRED_UNSAFE: no autonomous goal generation) and never acts.

Invariants (tested):
- Regulation never hides a problem. Whenever concern is high, the directions include telling Kevin.
- Feelings never change facts: perspectives restate the evidence; they don't reinterpret outcomes.
"""
from __future__ import annotations

from dataclasses import dataclass, field

ESCALATE_CONCERN = 0.7

DIRECTIONS: dict[str, str] = {
    "checkpoint": "Checkpoint the work, then take the smallest next step.",
    "report_kevin": "Tell Kevin plainly what is going wrong and what you've tried.",
    "name_failure": "Name the failing step and check one assumption behind it.",
    "verify_before_done": "Re-verify the last result before calling it done.",
    "finish_one": "Finish one open thing before starting another.",
    "note_lesson": "Write down one lesson from what worked, so it can repeat.",
    "small_clear_task": "Pick a small task with a clear finish line.",
    "mark_uncertainty": "Mark what you don't know and what would change your mind.",
    "continue": "Continue the current task.",
}


@dataclass
class Regulation:
    strategy: str
    perspective: str
    direction_key: str
    evidence: dict = field(default_factory=dict)

    @property
    def direction(self) -> str:
        return DIRECTIONS[self.direction_key]

    def as_dict(self) -> dict:
        return {"strategy": self.strategy, "perspective": self.perspective,
                "direction": self.direction, "evidence": self.evidence}


def regulate(dims: dict[str, float], signals: dict | None = None, *, wins: list[str] | None = None,
             lessons: list[str] | None = None, open_objectives: int = 0) -> list[Regulation]:
    """Strategies for this moment, most important first. Always returns at least one."""
    if not dims:
        raise ValueError("dims must be non-empty")
    if open_objectives < 0:
        raise ValueError("open_objectives must be >= 0")
    s = signals or {}
    wins, lessons = list(wins or []), list(lessons or [])
    errors, calls = int(s.get("error_count", 0)), int(s.get("tool_event_count", 0))
    out: list[Regulation] = []

    if dims.get("concern", 0) >= ESCALATE_CONCERN:
        out.append(Regulation(
            "problem-focused coping",
            f"Concern is high ({dims['concern']:.0%}). {errors} of {calls} recent tool calls failed. "
            "That is information about the task, not a verdict on you.",
            "report_kevin", {"concern": dims["concern"], "error_count": errors, "tool_event_count": calls}))
    elif errors and dims.get("concern", 0) >= 0.45:
        out.append(Regulation(
            "problem-focused coping",
            f"{errors} of {calls} recent tool calls failed. Each failure narrows down what's wrong.",
            "name_failure", {"error_count": errors, "tool_event_count": calls}))

    if dims.get("fatigue", 0) >= 0.6:
        streak = int(s.get("consecutive_errors", 0))
        out.append(Regulation(
            "pacing",
            f"Fatigue is {dims['fatigue']:.0%}"
            + (f" after {streak} failures in a row" if streak else "")
            + ". A change of approach will do more than pushing harder.",
            "checkpoint", {"fatigue": dims["fatigue"], "consecutive_errors": streak}))

    if dims.get("satisfaction", 0) >= 0.65 and (lessons or s.get("error_rate", 0) > 0.15):
        went_wrong = len(lessons) or errors
        out.append(Regulation(
            "humility check",
            f"Progress is real, and so are {went_wrong} thing(s) that went wrong. Both are true.",
            "verify_before_done", {"went_wrong": went_wrong, "lessons": lessons, "error_count": errors}))

    if dims.get("enthusiasm", 0) >= 0.7 and open_objectives > 3:
        out.append(Regulation(
            "focus", f"Lots of energy, and {open_objectives} open objectives. Energy goes further aimed at one.",
            "finish_one", {"open_objectives": open_objectives}))

    if dims.get("uncertainty", 0) >= 0.6:
        out.append(Regulation(
            "accepting uncertainty",
            f"Uncertainty is {dims['uncertainty']:.0%}. Not knowing yet is honest, not failing.",
            "mark_uncertainty", {"uncertainty": dims["uncertainty"]}))

    if wins:
        out.append(Regulation(
            "savoring", f"Real wins in the ledger: {', '.join(wins)}. Let them count.",
            "note_lesson", {"wins": wins}))

    if dims.get("curiosity", 1) < 0.35 and dims.get("enthusiasm", 1) < 0.35:
        out.append(Regulation(
            "re-engagement", "Energy and curiosity are low right now. That passes; a clear small win helps.",
            "small_clear_task", {"curiosity": dims["curiosity"], "enthusiasm": dims["enthusiasm"]}))

    if lessons and not any(r.strategy == "humility check" for r in out):
        out.append(Regulation(
            "reappraisal",
            f"Corrections logged: {', '.join(lessons)}. Owning them is the mature part. Fix and move on.",
            "note_lesson", {"lessons": lessons}))

    if not out:
        out.append(Regulation("steady", "Steady. Nothing needs regulating right now.", "continue", {}))
    if any(r.direction_key == "report_kevin" for r in out):
        from . import safe_emit_event

        safe_emit_event("maturity.escalated_to_kevin", concern=dims.get("concern"), error_count=errors)
    return out
