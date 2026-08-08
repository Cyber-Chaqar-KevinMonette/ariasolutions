"""wellbeing — the persisted composite value/care/flourishing score +
standing sentinel. (Wellbeing round · W1)

Three real subsystems already exist and were never connected to anything
standing: `stewardship.msims` (a rich impact-vector engine — `is_zombie()`,
`is_7g()` — reachable only via one manual CLI path), `stewardship.
calibration.honor_score()` (same disconnection), and `tools.
companion_tools`'s `value_report()` tool (computed fresh every call, never
persisted). This package composes all three into ONE persisted pass — the
same fix `quality/` and `grounding/` already applied to their own domains:
write the score down, standing.

`wellbeing/ledger.py` — `record_wellbeing_pass()` runs `companion_tools.
_build_value_report()` for the love/care signal, folds in an
`ImpactVector`'s `is_7g()`/`is_zombie()` when supplied, and
`foresight.project()` for the flourishing verdict — appends an fsync'd
NDJSON record. `latest_wellbeing()` / `wellbeing_trend()` read it back —
the honest kind, from stored passes only, mirroring `quality.ledger`/
`grounding.ledger`'s exact discipline.

Staged; applied via apply_wellbeing_ledger.sh.
"""
from __future__ import annotations

from .gate import WellbeingGateVerdict, gate  # wellbeing-gate-d
from .ledger import (
    WellbeingPassResult, latest_wellbeing, record_wellbeing_pass,
    wellbeing_trend,
)

__all__ = [
    "WellbeingPassResult", "latest_wellbeing", "wellbeing_trend",
    "record_wellbeing_pass", "WellbeingGateVerdict", "gate",  # wellbeing-gate-d
]
