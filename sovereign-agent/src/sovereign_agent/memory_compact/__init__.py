"""memory_compact — bounded growth with dignity. (FABLE II · M2)

Audit every append-only store; compact the compactable ones to verbatim
cold storage with a pointer index; propose-first via the sentinel;
execute only via the operator's `sov compact`. Staged; applied via
apply_memory_compact.sh.
"""
from __future__ import annotations

from .compact import (
    CompactError, CompactPlan, CompactResult, compaction_enabled,
    iter_cold_records, load_index, preview, run,
)
from .stores import REGISTRY, StoreSpec, audit_all, audit_journal, audit_store

__all__ = [
    "REGISTRY", "StoreSpec", "audit_all", "audit_journal", "audit_store",
    "CompactError", "CompactPlan", "CompactResult", "compaction_enabled",
    "iter_cold_records", "load_index", "preview", "run",
]
