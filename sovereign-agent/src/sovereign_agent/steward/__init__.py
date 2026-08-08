"""
sovereign_agent.steward — Aria's hygiene and health surface.

The steward is the part of Aria that asks "is my home in order?"

It does NOT modify state by default. It produces reports. The operator
(or, in tightly-scoped automated paths, the qa/auto-repair surface that
we have deliberately deferred) decides what to do with the findings.

Three pieces:

  1. ``audit_all`` — runs every channel's ``audit()`` method that exposes
     one, plus global invariants (orphan atoms, idempotency uniqueness,
     chain integrity), and rolls them into a single ``StewardReport``.

  2. ``find_conflicts`` — looks for the same logical fact recorded two
     incompatible ways (same person + same fact kind + different value,
     both confirmed). These are not bugs; they are *signals* that the
     operator needs to resolve.

  3. ``find_stale_recalls`` / ``find_orphans`` — surfaces hygiene work
     for the recall channel. Used by the CLI surface to give the
     operator a single screen of "what needs attention."

The steward speaks in Aria's voice: brief, honest, never alarmed.
A stale recall is not a crisis. It's a note that the world moved.
"""
from .health import (
    HealthCheck,
    StewardReport,
    audit_all,
    find_conflicts,
    find_orphans,
    find_stale_recalls,
)

__all__ = [
    "HealthCheck",
    "StewardReport",
    "audit_all",
    "find_conflicts",
    "find_orphans",
    "find_stale_recalls",
]
