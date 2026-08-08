"""Workflow package — the plan-act-check agentic loop.

AgenticLoop drives goal-decomposition into a task graph and steps through
it with pluggable tool handlers. Skeleton: tool handlers wire in for
v0.2.38+; the loop itself is here and works with a no-op default.
"""
from sovereign_agent.workflow.agentic_loop import (
    AgenticLoop, PlanStep, StepOutcome, ToolHandler, default_noop_handler,
)

__all__ = [
    "AgenticLoop",
    "PlanStep", "StepOutcome",
    "ToolHandler", "default_noop_handler",
]
