"""quality — the persisted quality ledger + standing sentinel. (Quality round · Q1)

`src/sovereign_agent/qa/` already scores test reports and hardening
checklists — pure functions, deterministic, but the score was NEVER
PERSISTED (recomputed fresh each call, never stored, never trended). This
package is the same fix `proving_ground/` already applied to benchmarks:
write the score down.

`quality/ledger.py` — `record_quality_pass()` runs `qa.hardening.
harden_module()` per target, scores it via `qa.quality_score.
score_hardening_report()`, appends an fsync'd NDJSON record. `latest_
quality()` / `quality_trend()` read it back — the "honest kind" of trend,
from stored scores only, mirroring `proving_ground.runner.trend()`.

Staged; applied via apply_quality.sh.
"""
from __future__ import annotations

from .ledger import (
    QualityPassResult, latest_quality, quality_trend, record_quality_pass,
)

__all__ = [
    "QualityPassResult", "latest_quality", "quality_trend",
    "record_quality_pass",
]
