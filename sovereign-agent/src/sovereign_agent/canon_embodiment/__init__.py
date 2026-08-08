"""canon_embodiment — the Canon-Embodiment organ: maps every mos_canon.py clause
to where (if anywhere) it's cited outside its own declaration. A clause with zero
outside citations is orphaned — declared but not (yet, traceably) lived. Staged;
applied via apply_canon_embodiment.sh."""
from __future__ import annotations

# Same preventive fix as path_scan/__init__.py: force `sovereign_agent.stewardship`
# to fully resolve before anything reaches `canon_embodiment.sentinel` (which
# stewardship/__init__.py imports to register CanonEmbodimentSentinel — a
# bidirectional coupling identical in shape to path_scan's). See path_scan's own
# comment for the full trace of why import order otherwise breaks this.
import sovereign_agent.stewardship  # noqa: F401

from sovereign_agent.canon_embodiment.mapper import (
    CanonEmbodimentReport,
    Location,
    extract_clause_ids,
    find_references,
)

__all__ = ["CanonEmbodimentReport", "Location", "extract_clause_ids", "find_references"]
