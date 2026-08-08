"""backlog_gate.py — Backlog quality pre-flight checker (M60).

BacklogGate.check(task, existing) returns a GateResult.
BacklogGate.filter_backlog(tasks) returns (kept, flagged) — never deletes.
Flagged tasks get status='flagged' + notes explaining why.
"""
from __future__ import annotations

from dataclasses import dataclass, field


VAGUE_PHRASES = frozenset({
    "do something",
    "be helpful",
    "check things",
    "run tasks",
    "do useful work",
    "help",
    "assist",
    "continue",
    "keep going",
    "work on stuff",
})

_MAX_GOAL_LENGTH = 500
_DUPLICATE_THRESHOLD = 0.8


@dataclass
class GateResult:
    passed: bool
    issues: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)


def _token_set(text: str) -> frozenset[str]:
    return frozenset(w.lower() for w in text.split() if len(w) > 2)


def _jaccard(a: frozenset, b: frozenset) -> float:
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


class BacklogGate:
    """Quality gate for backlog tasks before autonomous execution."""

    def check(self, task_goal: str, existing_goals: list[str]) -> GateResult:
        """Check a single task goal against gate rules.

        Args:
            task_goal: The goal string to check.
            existing_goals: Goals of other tasks to check for duplicates.

        Returns:
            GateResult with passed=True if all rules pass.
        """
        issues: list[str] = []
        suggestions: list[str] = []
        goal = task_goal.strip()

        # Rule 1: NoEmptyGoal
        if not goal:
            issues.append("empty goal — task will be skipped by scheduler")
            suggestions.append("Provide a specific, actionable goal string.")
            return GateResult(passed=False, issues=issues, suggestions=suggestions)

        # Rule 2: NoVague
        goal_lower = goal.lower()
        for phrase in VAGUE_PHRASES:
            if phrase in goal_lower and len(goal) < 80:
                issues.append(f"vague goal (contains '{phrase}') — too generic to produce value")
                suggestions.append("Be specific: name the tool, output, or outcome expected.")
                break

        # Rule 3: NoDuplicate (cap at 50 comparisons)
        tokens = _token_set(goal)
        for other in existing_goals[:50]:
            other_tokens = _token_set(other)
            if _jaccard(tokens, other_tokens) >= _DUPLICATE_THRESHOLD:
                issues.append(f"duplicate goal (>{_DUPLICATE_THRESHOLD*100:.0f}% token overlap with: '{other[:60]}...')")
                suggestions.append("Merge with the similar existing task or make this one more specific.")
                break

        # Rule 4: NoTooLong
        if len(goal) > _MAX_GOAL_LENGTH:
            issues.append(f"goal too long ({len(goal)} chars, max {_MAX_GOAL_LENGTH}) — may confuse the model")
            suggestions.append("Split into multiple smaller tasks or summarize the goal concisely.")

        return GateResult(passed=len(issues) == 0, issues=issues, suggestions=suggestions)

    def filter_backlog(
        self, tasks: list
    ) -> tuple[list, list[tuple]]:
        """Check all pending tasks. Returns (kept, flagged_with_results).

        Does NOT delete tasks. Flagged tasks have their status set to 'flagged'
        and their notes updated with gate findings.

        Args:
            tasks: list of BacklogTask objects (must have .goal, .status, .notes attributes).

        Returns:
            (kept, flagged_with_results) where flagged_with_results is
            [(task, GateResult), ...] for each flagged task.
        """
        kept = []
        flagged = []
        # Collect goals of non-flagged pending tasks for duplicate check
        prior_goals: list[str] = []

        for task in tasks:
            if task.status != "pending":
                kept.append(task)
                continue

            result = self.check(task.goal, prior_goals)
            if result.passed:
                kept.append(task)
                prior_goals.append(task.goal)
            else:
                task.status = "flagged"
                issues_txt = "; ".join(result.issues)
                task.notes = f"[gate] {issues_txt}"
                flagged.append((task, result))

        return kept, flagged


__all__ = ["BacklogGate", "GateResult", "VAGUE_PHRASES"]
