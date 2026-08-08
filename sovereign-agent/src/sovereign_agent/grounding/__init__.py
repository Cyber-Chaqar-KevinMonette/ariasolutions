"""grounding — the persisted composite epistemic score + standing sentinel.
(Grounding round · G1)

Three real subsystems already exist and never cross-reference each other:
`tribunal.grounding.analyze()` (a lexical evidence/hedge/mystical-fog
classifier, one-shot, pre-apply-only), `epistemic_ledger` (belief
confidence, never read anywhere else), and `curiosity.py`'s wonder loop
(self-reported confidence, never checked against the text's own texture).
This package composes all three into ONE persisted pass — the same fix
`quality/` already applied to `qa/`: write the score down, standing.

`grounding/ledger.py` — `record_grounding_pass()` scores each given text
via `tribunal.grounding.analyze()`, folds in `epistemic_ledger.
EpistemicLedger.current_beliefs()`'s average confidence, `eval_tools`'s
hypothesis-confirm-rate, and whether the qa-uncertainty join currently
holds, appends an fsync'd NDJSON record. `latest_grounding()` /
`grounding_trend()` read it back — the honest kind, from stored passes
only, mirroring `quality.ledger`'s exact discipline.

Staged; applied via apply_grounding_ledger.sh.
"""
from __future__ import annotations

from .gate import GroundingGateVerdict, gate  # grounding-gate-d
from .ledger import (
    GroundingPassResult, latest_grounding, grounding_trend,
    record_grounding_pass,
)

__all__ = [
    "GroundingPassResult", "latest_grounding", "grounding_trend",
    "record_grounding_pass", "GroundingGateVerdict", "gate",  # grounding-gate-d
]
