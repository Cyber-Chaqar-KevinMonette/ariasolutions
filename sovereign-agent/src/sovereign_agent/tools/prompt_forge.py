"""
tools/prompt_forge.py — Prompt engineering master & planning doctrine (M32)

Three Tier 0 tools (no side effects):

  forge_prompt(goal, task_type, context, constraints, tone)
    Build an optimized prompt for a given objective. Returns system_prompt,
    user_message, reasoning, and confidence.

  roadblock_protocol(obstacle, attempted_approaches, goal_context)
    Deterministic decision tree for when you're stuck. Returns structured
    alternatives, obstacle classification, severity, and escalation plan.
    NOT an LLM call — pure heuristic, fast, inspectable.

  confidence_check(claim, evidence_refs, threshold)
    Evaluate a logical claim against evidence. Returns confidence score,
    verdict (supported|unsupported|uncertain), and reasoning gaps.
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

from .base import Tool, ToolResult

# ── obstacle classification heuristics ───────────────────────────────────────

_OBSTACLE_CLASSES: dict[str, dict[str, Any]] = {
    "dependency-missing": {
        "keywords": ["no module", "not found", "import error", "missing package",
                     "modulenotfounderror", "cannot import", "command not found"],
        "severity": "recoverable",
        "approaches": [
            "Install the missing dependency: pip install <package> or uv add <package>",
            "Check if it's in a different namespace or has been renamed",
            "Use an alternative library that provides the same capability",
            "Mock or stub the dependency for the current task scope",
        ],
    },
    "permission-denied": {
        "keywords": ["permission denied", "access denied", "not authorized",
                     "403", "forbidden", "eperm", "eacces"],
        "severity": "recoverable",
        "approaches": [
            "Check file/directory permissions with stat or ls -la",
            "Use a path within the sandbox directory instead",
            "Request operator elevation for Tier 2/3 operation",
            "Find an alternative path that is already writable",
        ],
    },
    "timeout": {
        "keywords": ["timed out", "timeout", "deadline exceeded", "connection reset",
                     "etimedout", "read timeout", "operation timed out"],
        "severity": "recoverable",
        "approaches": [
            "Increase timeout parameter if the operation is slow but correct",
            "Break the operation into smaller chunks",
            "Check if the target service/resource is available",
            "Use an async or streaming approach to avoid blocking",
        ],
    },
    "api-unavailable": {
        "keywords": ["connection refused", "503", "502", "unavailable", "offline",
                     "eof", "broken pipe", "network unreachable", "no route to host"],
        "severity": "degraded",
        "approaches": [
            "Check internet_available() — fall back to cached/local data if offline",
            "Retry with exponential backoff (1s, 2s, 4s)",
            "Use an alternative endpoint or API that provides similar data",
            "Cache the result when available; use cached version if endpoint is down",
        ],
    },
    "assertion-failed": {
        "keywords": ["assertionerror", "assert", "expected", "got", "mismatch",
                     "does not match", "not equal"],
        "severity": "recoverable",
        "approaches": [
            "Read the actual value vs expected — understand the discrepancy first",
            "Check if the test expectation is stale and needs updating",
            "Add debug output (print/logging) to see intermediate state",
            "Trace the data flow backward from the assertion to find where it diverged",
        ],
    },
    "file-not-found": {
        "keywords": ["filenotfounderror", "no such file", "file not found",
                     "path does not exist", "enoent"],
        "severity": "recoverable",
        "approaches": [
            "Use list_dir() to see what's actually in the parent directory",
            "Check if the file is created by a prior step that hasn't run yet",
            "Verify the path is absolute and correct with read_file()",
            "Create the file or directory if it should exist but doesn't",
        ],
    },
    "type-error": {
        "keywords": ["typeerror", "unexpected keyword", "takes", "argument", "got an unexpected",
                     "positional", "required positional"],
        "severity": "recoverable",
        "approaches": [
            "Read the function signature with help() or inspect.signature()",
            "Check the version of the library — API may have changed",
            "Look at the source file directly to see what parameters are accepted",
            "Add type annotations and run mypy to catch mismatches before runtime",
        ],
    },
    "out-of-memory": {
        "keywords": ["out of memory", "oom", "killed", "memory error", "cannot allocate",
                     "enomem", "vram"],
        "severity": "degraded",
        "approaches": [
            "Check VRAM/RAM headroom with vessel_status() before heavy operations",
            "Use a smaller model or reduce batch size",
            "Serialize GPU operations via vram_lock to prevent concurrent allocation",
            "Process data in chunks rather than loading everything at once",
        ],
    },
}

_DEFAULT_CLASS = {
    "severity": "blocked",
    "approaches": [
        "Break the problem into smaller verifiable steps",
        "Search for prior art: web_research() for solutions to this class of problem",
        "Read the relevant source code or documentation",
        "State the constraint clearly and escalate to the operator with full context",
    ],
}


def _classify_obstacle(obstacle: str, attempted: list[str]) -> tuple[str, dict[str, Any]]:
    lower = obstacle.lower() + " " + " ".join(attempted).lower()
    for cls, meta in _OBSTACLE_CLASSES.items():
        if any(kw in lower for kw in meta["keywords"]):
            return cls, meta
    return "unknown", _DEFAULT_CLASS


# ── forge_prompt ─────────────────────────────────────────────────────────────


class ForgePromptTool(Tool):
    """Build an optimized prompt for a specific objective.

    Combines goal, task type, context, constraints, and tone into
    a structured prompt pair (system + user). Returns the reasoning
    behind the choices and a confidence estimate.
    """

    name = "forge_prompt"
    tier = 0
    description = (
        "Build an optimized prompt for a specific objective. "
        "Args: goal, task_type (analysis|generation|debugging|research|planning), "
        "context (optional background), constraints (optional list), tone (optional). "
        "Returns: system_prompt, user_message, reasoning, confidence."
    )
    failure_modes = ("unknown task_type",)

    _TASK_PATTERNS: dict[str, dict[str, str]] = {
        "analysis": {
            "system_role": "expert analyst",
            "approach": "examine systematically — identify patterns, anomalies, and root causes",
            "output_hint": "structured findings with evidence for each claim",
        },
        "generation": {
            "system_role": "expert creator",
            "approach": "produce high-quality output — prioritize correctness, then clarity",
            "output_hint": "complete, runnable, well-structured output",
        },
        "debugging": {
            "system_role": "expert debugger",
            "approach": "trace the failure backward — find root cause, not just symptoms",
            "output_hint": "root cause, reproduction steps, minimal fix, prevention",
        },
        "research": {
            "system_role": "expert researcher",
            "approach": "gather evidence from multiple sources — cross-reference and verify",
            "output_hint": "synthesized findings with source attribution and confidence levels",
        },
        "planning": {
            "system_role": "expert planner",
            "approach": "decompose into verifiable steps — explicit dependencies and checkpoints",
            "output_hint": "ordered step list with action_kind, produces, consumes, success criteria",
        },
    }

    class Args(BaseModel):
        goal: str = Field(description="What you want the prompt to accomplish.")
        task_type: str = Field(
            default="analysis",
            description="Type: analysis | generation | debugging | research | planning.",
        )
        context: str = Field(default="", description="Background information for the prompt.")
        constraints: list[str] = Field(
            default_factory=list, description="Hard constraints the output must respect."
        )
        tone: str = Field(default="precise", description="Tone: precise | warm | technical | concise.")

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        pattern = self._TASK_PATTERNS.get(args.task_type)
        if pattern is None:
            valid = ", ".join(sorted(self._TASK_PATTERNS))
            return ToolResult(ok=False, error=f"unknown task_type {args.task_type!r}. Valid: {valid}")

        constraint_block = ""
        if args.constraints:
            lines = "\n".join(f"  - {c}" for c in args.constraints)
            constraint_block = f"\n\nHard constraints:\n{lines}"

        context_block = f"\n\nContext:\n{args.context}" if args.context else ""

        system_prompt = (
            f"You are a {pattern['system_role']} operating with {args.tone} precision.\n"
            f"Approach: {pattern['approach']}.\n"
            f"Output format: {pattern['output_hint']}."
            f"{constraint_block}"
        )

        user_message = (
            f"Goal: {args.goal}"
            f"{context_block}\n\n"
            f"Please proceed."
        )

        reasoning = (
            f"Selected pattern '{args.task_type}' — maps to {pattern['system_role']} role. "
            f"Approach chosen: {pattern['approach']}. "
            f"Tone '{args.tone}' applied to role framing."
        )

        confidence = 0.85 if args.context else 0.70

        return ToolResult(
            ok=True,
            output={
                "system_prompt": system_prompt,
                "user_message": user_message,
                "reasoning": reasoning,
                "confidence": confidence,
                "task_type": args.task_type,
            },
            metadata={"task_type": args.task_type, "confidence": confidence},
        )


# ── roadblock_protocol ────────────────────────────────────────────────────────


class RoadblockProtocolTool(Tool):
    """Structured escalation protocol when you hit a wall.

    Classifies the obstacle, returns severity assessment, and gives
    3-4 concrete next approaches with confidence scores.
    NOT an LLM call — deterministic heuristic decision tree.
    Fast, inspectable, produces derivative reasoning.
    """

    name = "roadblock_protocol"
    tier = 0
    description = (
        "Structured escalation protocol for when you're blocked. "
        "Args: obstacle (error or problem description), "
        "attempted_approaches (list of what you tried), "
        "goal_context (what you were trying to accomplish). "
        "Returns: obstacle_class, severity, next_approaches with confidence, "
        "escalate_to_human flag, derivatives."
    )
    failure_modes = ("obstacle too vague to classify",)

    class Args(BaseModel):
        obstacle: str = Field(description="The error message or problem you're stuck on.")
        attempted_approaches: list[str] = Field(
            default_factory=list, description="What you've already tried."
        )
        goal_context: str = Field(default="", description="What you were trying to accomplish.")

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        cls, meta = _classify_obstacle(args.obstacle, args.attempted_approaches)

        tried_lower = {a.lower() for a in args.attempted_approaches}
        approaches = meta.get("approaches", _DEFAULT_CLASS["approaches"])
        unused = [a for a in approaches if not any(kw in a.lower() for kw in tried_lower)]
        if not unused:
            unused = approaches  # if everything tried, cycle back with fresh framing

        next_approaches = [
            {"approach": a, "confidence": round(0.75 - 0.1 * i, 2)}
            for i, a in enumerate(unused[:4])
        ]

        severity = meta.get("severity", "blocked")
        escalate = severity == "blocked" and len(args.attempted_approaches) >= 2

        derivatives: list[str] = []
        if args.goal_context:
            derivatives.append(
                f"If obstacle resolved: '{args.goal_context}' can proceed."
            )
        derivatives.append(
            f"If all approaches fail: escalate with full attempt log — "
            f"obstacle_class={cls!r}, severity={severity!r}."
        )

        return ToolResult(
            ok=True,
            output={
                "obstacle_class": cls,
                "severity": severity,
                "next_approaches": next_approaches,
                "escalate_to_human": escalate,
                "escalation_message": (
                    f"Blocked on {cls!r} after {len(args.attempted_approaches)} attempts. "
                    f"Obstacle: {args.obstacle[:200]}. "
                    f"All approaches exhausted. Operator input needed."
                ) if escalate else "",
                "derivatives": derivatives,
            },
            metadata={"obstacle_class": cls, "severity": severity},
        )


# ── confidence_check ──────────────────────────────────────────────────────────


class ConfidenceCheckTool(Tool):
    """Evaluate a logical claim against stated evidence.

    Returns a confidence score (0.0–1.0), verdict (supported/unsupported/uncertain),
    and reasoning gaps. Use before acting on uncertain information (threshold < 0.7).
    """

    name = "confidence_check"
    tier = 0
    description = (
        "Evaluate a claim against evidence and return a confidence score. "
        "Args: claim (statement to evaluate), evidence_refs (list of supporting facts), "
        "threshold (default 0.7 — below this, flag for operator review). "
        "Returns: confidence (0.0–1.0), verdict (supported|unsupported|uncertain), "
        "reasoning, gaps."
    )
    failure_modes = ("claim too vague to evaluate",)

    class Args(BaseModel):
        claim: str = Field(description="The logical claim to evaluate.")
        evidence_refs: list[str] = Field(
            default_factory=list,
            description="List of facts or observations that support or contradict the claim.",
        )
        threshold: float = Field(
            default=0.7, ge=0.0, le=1.0,
            description="Confidence threshold below which verdict is 'uncertain'.",
        )

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        n = len(args.evidence_refs)

        if n == 0:
            confidence = 0.2
            verdict = "uncertain"
            reasoning = "No evidence provided — claim cannot be evaluated."
            gaps = ["Provide at least one concrete observation or source."]
        elif n == 1:
            confidence = 0.5
            verdict = "uncertain"
            reasoning = f"Single evidence item: {args.evidence_refs[0][:100]!r}. Insufficient for high confidence."
            gaps = ["Add corroborating evidence from a second source or observation."]
        elif n <= 3:
            confidence = min(0.75, 0.5 + n * 0.08)
            verdict = "supported" if confidence >= args.threshold else "uncertain"
            reasoning = f"{n} evidence items support the claim."
            gaps = [] if confidence >= 0.7 else ["More evidence would strengthen confidence above 0.7."]
        else:
            confidence = min(0.92, 0.6 + n * 0.06)
            verdict = "supported"
            reasoning = f"{n} evidence items strongly support the claim."
            gaps = []

        needs_review = confidence < args.threshold

        return ToolResult(
            ok=True,
            output={
                "claim": args.claim,
                "confidence": round(confidence, 2),
                "verdict": verdict,
                "reasoning": reasoning,
                "gaps": gaps,
                "needs_operator_review": needs_review,
                "threshold": args.threshold,
            },
            metadata={"confidence": round(confidence, 2), "verdict": verdict},
        )
