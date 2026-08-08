"""apply_queue — durable, dependency-sequenced apply queue + quarantine registry.

Cockpit-driven flow: select staged modules in the cockpit → a durable queue file
is written → close the cockpit → ``scripts/apply_queue_run.sh`` drains it through
``safe_apply.sh`` (guarded + auto-rollback). Successes leave the queue; rollbacks
route to quarantine for evaluation until fixed. Staged; applied via apply_apply_queue.sh.
"""
from __future__ import annotations

from sovereign_agent.apply_queue.store import (
    PRIORITY,
    ApplyQueueStore,
    QuarantineRecord,
    QuarantineRegistry,
    QueueItem,
)

__all__ = [
    "ApplyQueueStore",
    "QuarantineRegistry",
    "QueueItem",
    "QuarantineRecord",
    "PRIORITY",
]
