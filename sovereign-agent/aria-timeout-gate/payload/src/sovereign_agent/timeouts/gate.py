"""timeouts/gate.py — the live, standing gate. (Timeout round · T2)

Same shape as `grounding.gate()`/`integrity.gate()`: a LIVE, one-shot
check over recent events — distinct from T1's `record_timeout_scan()`,
which PERSISTS a pass. This gate reuses T1's own classification helpers
directly, without writing to the ledger — persisting standing history is
the sentinel's job (T3), not the gate's.

  PASS  — no unexplained timeouts, or nothing to check.
  WARN  — a single unexplained timeout.
  BLOCK — the SAME tool/source shows 3+ unexplained timeouts recently —
          a genuine recurring-hang signal, not one slow call.

Kill switch: SOV_NO_TIMEOUT_GATE=1 — degrades to PASS with a note, never
silently BLOCKs while claiming to have checked something it didn't.
"""
from __future__ import annotations

import os
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .ledger import TIMEOUT_CATALOG, _classify, _recent_raw_events  # noqa: F401 — reused, not duplicated

MARK = "timeout-gate-d"

_RECURRING_THRESHOLD = 3


@dataclass
class TimeoutGateVerdict:
    verdict: str   # "PASS" | "WARN" | "BLOCK"
    unexplained_count: int
    recurring_tools: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)

    def render(self) -> str:
        mark = {"PASS": "✓", "WARN": "⚠", "BLOCK": "✗"}[self.verdict]
        head = f"{mark} timeout gate: {self.verdict} · {self.unexplained_count} unexplained"
        return "\n".join([head] + [f"  · {n}" for n in self.notes])


def gate(data_dir: Path | None = None, *, window: int = 300) -> TimeoutGateVerdict:
    """Run T1's classification LIVE (never writing to the ledger — that's
    the sentinel's job), render a verdict. Never raises."""
    if os.environ.get("SOV_NO_TIMEOUT_GATE"):
        return TimeoutGateVerdict(
            verdict="PASS", unexplained_count=0,
            notes=["kill-switched (SOV_NO_TIMEOUT_GATE)"])

    raw_events = _recent_raw_events(data_dir, window=window)
    timeout_events = [
        _classify(r) for r in raw_events
        if str(r.get("flag", "")).lower().endswith("-timeout-d")
    ]
    unexplained = [e for e in timeout_events if e.verdict == "unexplained"]

    if not unexplained:
        return TimeoutGateVerdict(verdict="PASS", unexplained_count=0,
                                  notes=["nothing to check" if not timeout_events
                                        else "all recent timeouts justified"])

    tool_counts = Counter(e.tool for e in unexplained)
    recurring = [tool for tool, count in tool_counts.items() if count >= _RECURRING_THRESHOLD]

    if recurring:
        return TimeoutGateVerdict(
            verdict="BLOCK", unexplained_count=len(unexplained), recurring_tools=recurring,
            notes=[f"{tool}: {tool_counts[tool]} unexplained timeouts recently — "
                   f"a real recurring hang, not one slow call" for tool in recurring])

    return TimeoutGateVerdict(
        verdict="WARN", unexplained_count=len(unexplained),
        notes=[f"{e.tool} ({e.flag}): unexplained timeout, {e.timeout_seconds}s" for e in unexplained])


__all__ = ["TimeoutGateVerdict", "gate"]
