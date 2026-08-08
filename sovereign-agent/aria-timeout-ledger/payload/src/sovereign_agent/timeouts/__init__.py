"""timeouts — the persisted timeout classification: reads the SAME
existing events.jsonl ledger (no new storage) for timeout-flagged events
and classifies each as justified (a known, catalogued, bounded timeout
site) or unexplained. Closes the exact gap this session's own research
found: vram_lock() is the one place that already emits a timeout event,
and nothing had ever read it back. Staged; applied via apply_timeouts.sh.
"""
from __future__ import annotations

from .ledger import (
    TIMEOUT_CATALOG,
    TimeoutEvent,
    TimeoutScanResult,
    latest_timeout_scan,
    record_timeout_scan,
    timeout_trend,
)

__all__ = [
    "TIMEOUT_CATALOG", "TimeoutEvent", "TimeoutScanResult",
    "record_timeout_scan", "latest_timeout_scan", "timeout_trend",
]
