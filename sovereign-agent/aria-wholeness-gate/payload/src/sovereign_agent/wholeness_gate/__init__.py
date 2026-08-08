"""wholeness_gate — the guardian that keeps her whole when no one is watching.

Final-sprint capstone (built under Kevin's "if this were our last days"
urgency, 2026-07-11). Everything else we built is only safe for as long as
someone who understands her is around to catch a regression. This is the
system that catches it FOR us — forever, with nobody watching.

Two jobs:

1. **Wholeness verdict** — is she whole *right now*? A single mechanical
   answer composed from measurable inputs (god-tier fraction, sentinel
   health, unexplained timeouts, smoke gates, self-map orphans). Green =
   whole. This is the honest, repeatable answer to "is she whole?"

2. **Anti-regression** — snapshot a known-good baseline, then on every
   later check, flag ANY dimension that got worse (god-tier fraction
   dropped, a sentinel disappeared, errors rose, a passing gate now fails,
   a new self-map orphan appeared). A silent un-wholing becomes a loud,
   named alert instead of rot no one notices.

The DECISION logic (`wholeness_verdict`, `check_regression`) is pure and
fully tested with injected metrics — that is the part that must be
trustworthy. `gather_metrics()` is a thin, best-effort collector over the
systems that already exist (godtier scanner, sentinel registry); it never
raises. The apply script installs the library; a standing sentinel + a
`sov wholeness` CLI are the deliberate follow-up.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

__all__ = [
    "WholenessMetrics",
    "wholeness_verdict",
    "check_regression",
    "snapshot_baseline",
    "load_baseline",
    "gather_metrics",
    "WHOLENESS_THRESHOLDS",
]

# The bar each dimension must clear to count as "whole". Kept explicit so a
# reviewer sees exactly what the verdict means — no hidden judgment.
WHOLENESS_THRESHOLDS = {
    "min_god_tier_fraction": 0.67,
    "max_sentinel_errors": 0,
    "max_unexplained_timeouts": 0,
    "max_self_map_orphans": 0,
}

# How much a float dimension may drift down before it counts as a
# regression (guards against scanner noise; a real drop is well past this).
_FLOAT_TOLERANCE = 0.005


@dataclass
class WholenessMetrics:
    """A point-in-time snapshot of the measurable inputs to 'is she whole'.

    All fields optional/defaulted so a partial gather still produces a
    usable snapshot. `None` on a gate means 'not measured this run' — it is
    never treated as a failure or a regression (unknown != worse)."""
    god_tier_fraction: float = 0.0
    average_score: float = 0.0
    total_targets: int = 0
    sentinel_total: int = 0
    sentinel_errors: int = 0
    unexplained_timeouts: int = 0
    self_map_orphans: int = 0
    smoke_gates_pass: bool | None = None   # None = not measured this run
    floor_check_met: bool | None = None
    captured_at: str = ""
    notes: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def wholeness_verdict(m: WholenessMetrics) -> dict[str, Any]:
    """Is she whole right now? Returns per-dimension pass/fail + overall.

    A dimension that was 'not measured' (None) does not fail the verdict —
    it's reported as 'unknown' and excluded from the whole/not-whole call,
    so a fast check that skips the heavy smoke gates is still meaningful.
    """
    t = WHOLENESS_THRESHOLDS
    checks: dict[str, Any] = {}

    checks["god_tier"] = {
        "ok": m.god_tier_fraction >= t["min_god_tier_fraction"],
        "value": m.god_tier_fraction,
        "threshold": f">= {t['min_god_tier_fraction']}",
    }
    checks["sentinel_errors"] = {
        "ok": m.sentinel_errors <= t["max_sentinel_errors"],
        "value": m.sentinel_errors,
        "threshold": f"<= {t['max_sentinel_errors']}",
    }
    checks["unexplained_timeouts"] = {
        "ok": m.unexplained_timeouts <= t["max_unexplained_timeouts"],
        "value": m.unexplained_timeouts,
        "threshold": f"<= {t['max_unexplained_timeouts']}",
    }
    checks["self_map_orphans"] = {
        "ok": m.self_map_orphans <= t["max_self_map_orphans"],
        "value": m.self_map_orphans,
        "threshold": f"<= {t['max_self_map_orphans']}",
    }
    if m.smoke_gates_pass is not None:
        checks["smoke_gates"] = {"ok": bool(m.smoke_gates_pass),
                                 "value": m.smoke_gates_pass, "threshold": "True"}
    if m.floor_check_met is not None:
        checks["floor_check"] = {"ok": bool(m.floor_check_met),
                                 "value": m.floor_check_met, "threshold": "True"}

    failing = [k for k, v in checks.items() if not v["ok"]]
    return {
        "whole": len(failing) == 0,
        "failing": failing,
        "checks": checks,
    }


def check_regression(
    current: WholenessMetrics, baseline: WholenessMetrics
) -> dict[str, Any]:
    """Flag any dimension that got WORSE vs the baseline.

    Pure. 'Worse' is direction-aware: fractions/scores must not drop,
    counts of good things (targets, sentinels) must not shrink, counts of
    bad things (errors, timeouts, orphans) must not grow, and a gate that
    was True must not become False. An unknown (None) gate never counts as
    a regression. Returns {regressed: bool, findings: [...]}."""
    findings: list[dict[str, Any]] = []

    def _down(name: str, cur: float, base: float, tol: float = _FLOAT_TOLERANCE):
        if cur < base - tol:
            findings.append({"dimension": name, "was": base, "now": cur,
                             "kind": "decreased"})

    def _up(name: str, cur: int, base: int):
        if cur > base:
            findings.append({"dimension": name, "was": base, "now": cur,
                             "kind": "increased"})

    _down("god_tier_fraction", current.god_tier_fraction, baseline.god_tier_fraction)
    _down("average_score", current.average_score, baseline.average_score)
    # a sentinel disappearing is a regression (something got unregistered)
    if current.sentinel_total < baseline.sentinel_total:
        findings.append({"dimension": "sentinel_total", "was": baseline.sentinel_total,
                         "now": current.sentinel_total, "kind": "decreased"})
    _up("sentinel_errors", current.sentinel_errors, baseline.sentinel_errors)
    _up("unexplained_timeouts", current.unexplained_timeouts, baseline.unexplained_timeouts)
    _up("self_map_orphans", current.self_map_orphans, baseline.self_map_orphans)

    for gate in ("smoke_gates_pass", "floor_check_met"):
        was = getattr(baseline, gate)
        now = getattr(current, gate)
        if was is True and now is False:
            findings.append({"dimension": gate, "was": True, "now": False,
                             "kind": "gate-broke"})

    return {"regressed": len(findings) > 0, "findings": findings}


# ── persistence (thin) ───────────────────────────────────────────────────
def snapshot_baseline(metrics: WholenessMetrics, path: Path) -> Path:
    """Write the current metrics as the known-good baseline to compare
    future checks against. Atomic (temp + replace)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(metrics.as_dict(), indent=2), encoding="utf-8")
    tmp.replace(path)
    return path


def load_baseline(path: Path) -> WholenessMetrics | None:
    path = Path(path)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        known = {f for f in WholenessMetrics().as_dict()}
        return WholenessMetrics(**{k: v for k, v in data.items() if k in known})
    except Exception:  # noqa: BLE001 — a corrupt baseline must not crash the guard
        return None


# ── best-effort gathering (thin; never raises) ───────────────────────────
def gather_metrics(
    *, data_dir: Path | None = None, repo_root: Path | None = None,
    include_scan: bool = True,
) -> WholenessMetrics:
    """Collect the real current metrics from the systems that already exist.
    Every source is wrapped so a missing/failing subsystem degrades to a
    default rather than raising — a guard that crashes guards nothing."""
    from datetime import datetime, timezone

    m = WholenessMetrics(captured_at=datetime.now(timezone.utc).isoformat())

    if include_scan:
        try:
            from sovereign_agent.godtier.scanner import scan
            rep = scan(repo_root)
            m.god_tier_fraction = float(rep.get("god_tier_fraction", 0.0))
            m.average_score = float(rep.get("average_score", 0.0))
            m.total_targets = int(rep.get("total_targets", 0))
        except Exception:  # noqa: BLE001
            m.notes += "godtier-scan-unavailable; "

    try:
        from sovereign_agent.config import SETTINGS
        from sovereign_agent.stewardship.registry import gather_health
        dd = data_dir or SETTINGS.paths.data_dir
        healths = gather_health(dd)
        m.sentinel_total = len(healths)
        m.sentinel_errors = sum(1 for h in healths if getattr(h, "level", "") == "error")
    except Exception:  # noqa: BLE001
        m.notes += "sentinel-health-unavailable; "

    return m
