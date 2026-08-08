"""
sovereign_agent.planner — plan-then-execute over N items.

Kevin's pattern, stated:

    "If I have 100 files: read each file FIRST, plan the best path for
    each, THEN plan how to proceed with all 100 in the most leveraged way."

This module formalises that into two passes:

    Phase 1 (per-item):     read + analyze + draft an item-level plan
    Phase 2 (cross-cutting): synthesize across all plans — find synergies,
                              dependencies, batching wins, ordering
    Phase 3 (execute):      run in the synthesized order with tracking

A naive loop processes file 1 → execute, file 2 → execute, etc. It misses
that file 47 is a near-duplicate of file 12 (could share work), or that
files 80-100 depend on file 5 (should be done first). The planner exposes
that structure before any execution starts, so the operator can audit
the plan before authorising the batch.

This is not a workflow engine. It is a tiny, honest primitive. Use it
when batch coherence matters more than raw throughput.
"""
from .batch import (
    BatchPlanner,
    BatchReport,
    ItemPlan,
    CrossCuttingPlan,
    ExecutionResult,
)

__all__ = [
    "BatchPlanner",
    "BatchReport",
    "ItemPlan",
    "CrossCuttingPlan",
    "ExecutionResult",
]
