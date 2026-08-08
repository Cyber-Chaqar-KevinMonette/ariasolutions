"""integrity — the composite anti-misleading signal: one persisted score
folding together text-honesty (grounding.gate), outcome-honesty
(calibration.presumed_zombie_penalty), proposal-honesty (spectrum.lenses.
witness), and refusal-honesty (peig_sentinel Identity score). None of
these four cross-referenced each other before this package existed.
Staged; applied via apply_integrity.sh."""
from __future__ import annotations

from .gate import IntegrityGateVerdict, gate  # integrity-gate-d
from .ledger import (
    IntegrityPassResult,
    IntegritySignal,
    calibration_sensitivity,
    integrity_trend,
    latest_integrity,
    record_integrity_pass,
)

__all__ = [
    "IntegritySignal", "IntegrityPassResult", "record_integrity_pass",
    "latest_integrity", "integrity_trend", "calibration_sensitivity",
    "IntegrityGateVerdict", "gate",  # integrity-gate-d
]
