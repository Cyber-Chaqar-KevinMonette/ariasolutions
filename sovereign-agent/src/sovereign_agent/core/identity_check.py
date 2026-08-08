"""
core/identity_check.py — structural identity continuity check
v0.2.40 wholeness

Verifies that aria_values.yaml still contains all expected core
properties before allowing a values update to take effect. Pure
structural test — no LLM calls.

Future expansion path (captured in FUTURE-GOVERNANCE-ARCHITECTURE-CE-2026.05.29):
adds behavioral golden-test suite + runtime drift metrics + human review.
Those require production traffic, multiple humans, and accumulated
output history — none of which exist yet. When they do, those layers
compose on top of this one.

Kill switch: SOV_NO_IDENTITY_CHECK=1
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from sovereign_agent.core.values import AriaValues


KILL_SWITCH_ENV = "SOV_NO_IDENTITY_CHECK"


@dataclass
class ContinuityResult:
    passed: bool
    missing_properties: list[str]
    spec_version: str
    summary: str


def check_continuity(values: AriaValues) -> ContinuityResult:
    """Verify the values spec contains all expected core properties.

    Returns ContinuityResult with passed=True if all expected
    core_properties are present in identity_continuity.core_properties.
    """
    if os.environ.get(KILL_SWITCH_ENV):
        return ContinuityResult(
            passed=True, missing_properties=[],
            spec_version=values.version,
            summary="identity check disabled via SOV_NO_IDENTITY_CHECK",
        )

    passed, missing = values.structural_continuity_check()

    if passed:
        summary = (
            f"identity continuity verified — all {len(values.identity_continuity.core_properties)} "
            f"core properties present in spec {values.version}"
        )
    else:
        summary = (
            f"identity continuity FAILED — {len(missing)} core properties "
            f"missing from spec {values.version}: {missing}"
        )

    return ContinuityResult(
        passed=passed,
        missing_properties=missing,
        spec_version=values.version,
        summary=summary,
    )


__all__ = ["check_continuity", "ContinuityResult", "KILL_SWITCH_ENV"]
