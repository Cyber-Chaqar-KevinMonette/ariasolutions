"""
sovereign_agent.qa — Aria's master builder/tester/hardener surface.

The codebase already has rigorous tests. What this module adds is the
*reporting and scoring* surface: structured outputs the operator (and
Aria herself) can read to answer "what's the quality of this module?"

Three pieces:

  1. ``runner`` — runs pytest (optionally scoped to a path), captures
     pass/fail counts, durations, and any failures into a TestReport
     with a 0-100 quality score across multiple dimensions.

  2. ``hardening`` — applies a checklist of MOS-aligned hardening
     criteria to a target module (does it validate inputs? does it
     have idempotency? does it expose observability? does it have a
     rollback path?) and emits a HardeningReport with a 0-100 score.

  3. ``edge_cases`` — given a target callable or module, generates a
     standard battery of adversarial inputs (boundary values, empties,
     malformed types, unicode tricks, injection patterns, race-
     simulation harnesses) and renders them as an EdgeCasePlan.

Reports are the artifact. Automation is deliberately deferred: report
first, fix second, automation only after the data justifies it.
"""
from .edge_cases import EdgeCasePlan, EdgeCase, generate_edge_cases
from .hardening import HardeningReport, HardeningCheck, harden_module
from .quality_score import QualityScore, score_test_report, score_hardening_report
from .runner import TestReport, TestFailure, run_tests

__all__ = [
    "EdgeCase",
    "EdgeCasePlan",
    "HardeningCheck",
    "HardeningReport",
    "QualityScore",
    "TestFailure",
    "TestReport",
    "generate_edge_cases",
    "harden_module",
    "run_tests",
    "score_hardening_report",
    "score_test_report",
]
