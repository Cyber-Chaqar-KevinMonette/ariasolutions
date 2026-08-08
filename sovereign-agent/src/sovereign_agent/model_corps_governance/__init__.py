"""model_corps_governance — the standing model-roster governance layer:
persisted registry (MC3), a standing sentinel (MC4, in
`stewardship/model_corps_sentinel.py`), a mechanically-scored eval + gate
(MC5), and an optional non-classical confidence tie-in (MC6). Closes
GOD_TIER_CRITERIA.md's named gaps #2 ("standing scored model benchmark")
and #3 ("small-model response-quality tuning"). Staged; applied via
apply_model_corps_governance.sh."""
from __future__ import annotations

from .gate import EvalPassResult, GateVerdict, RoleEvalResult, gate, latest_eval, run_corps_eval
from .nonclassical_confidence import score_candidates
from .registry import (
    ALLOWED_LICENSES,
    ROSTER,
    ModelCorpsEntry,
    RegistrySnapshot,
    latest_registry,
    record_registry_snapshot,
)

__all__ = [
    "ALLOWED_LICENSES", "ROSTER", "ModelCorpsEntry", "RegistrySnapshot",
    "record_registry_snapshot", "latest_registry",
    "EvalPassResult", "GateVerdict", "RoleEvalResult", "gate", "latest_eval", "run_corps_eval",
    "score_candidates",
]
