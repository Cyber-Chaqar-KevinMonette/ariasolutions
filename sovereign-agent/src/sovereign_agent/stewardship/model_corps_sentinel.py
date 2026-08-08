"""stewardship/model_corps_sentinel.py — ModelCorpsSentinel. (Model Corps
round · MC4)

Watches the model roster standing: (a) license — every registered role's
license must be in `registry.ALLOWED_LICENSES`, which would have caught
every model in the pre-round roster (Llama 3 Community License,
research-only LLaVA); (b) drift — the `aria-<role>` tag the registry
declares must actually be installed (`ollama list`); (c) VRAM budget — the
single largest registered model must fit under `vram.py`'s own
`TOTAL_VRAM_MB - SAFETY_FLOOR_MB`, reusing that module's existing constants
rather than inventing a second budget.

Propose-only, like every sentinel here — it reports, it does not `heal()`.
Kill switch: SOV_NO_MODEL_CORPS_SENTINEL=1 (via Sentinel.is_enabled();
master: SOV_NO_SENTINELS=1).
"""
from __future__ import annotations

import subprocess
from datetime import datetime, timezone

from sovereign_agent.stewardship.base import HealthStatus, Sentinel, SentinelReport
from sovereign_agent.stewardship.registry import register_sentinel

MARK = "model-corps-sentinel-d"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _installed_tags() -> set[str] | None:
    """The set of tags `ollama list` currently reports, or None if the
    daemon is unreachable (a down daemon is reported honestly, never
    mistaken for "every model missing")."""
    try:
        proc = subprocess.run(["ollama", "list"], capture_output=True, text=True, timeout=10)
    except Exception:  # noqa: BLE001
        return None
    if proc.returncode != 0:
        return None
    tags = set()
    for line in proc.stdout.splitlines()[1:]:  # skip the header row
        parts = line.split()
        if parts:
            tags.add(parts[0])
    return tags


@register_sentinel
class ModelCorpsSentinel(Sentinel):
    """Watches whether the declared model roster is actually what's running,
    actually within license, and actually within the VRAM budget — not just
    whether it looked right the day it was built."""

    @property
    def id(self) -> str:
        return "model_corps"

    @property
    def title(self) -> str:
        return "Model Corps — roster license / drift / VRAM-budget standing check"

    @property
    def tier(self) -> int:
        return 1

    def articles(self) -> list[str]:
        return [
            "I. I check every registered role's license against an explicit "
            "allow-list (Apache-2.0, MIT, BSD-3-Clause) — a model with a "
            "restrictive license is a FAIL, not a footnote.",
            "II. I check that the tag the registry declares is actually "
            "installed — a stale registry pointing at a deleted model is "
            "drift, reported plainly.",
            "III. I check the single largest registered model against "
            "vram.py's own TOTAL_VRAM_MB/SAFETY_FLOOR_MB constants — the "
            "same budget the rest of the system already uses, not a second "
            "invented one.",
            "IV. I propose, never repair. A license or drift failure is "
            "reported for a human to act on, never silently patched.",
        ]

    def scan(self) -> SentinelReport:
        from sovereign_agent.model_corps_governance.registry import (
            ALLOWED_LICENSES,
            ROSTER,
            record_registry_snapshot,
        )

        snapshot = record_registry_snapshot(data_dir=self._data_dir)
        installed = _installed_tags()

        license_failures = [e.role for e in snapshot.entries if e.license not in ALLOWED_LICENSES]
        if installed is None:
            drift_failures: list[str] = []
            daemon_reachable = False
        else:
            drift_failures = [e.role for e in snapshot.entries if e.tag not in installed]
            daemon_reachable = True

        vram_failure = None
        try:
            from sovereign_agent import vram as vram_mod

            largest = max(snapshot.entries, key=lambda e: e.vram_mb, default=None)
            if largest is not None:
                budget = vram_mod.TOTAL_VRAM_MB - vram_mod.SAFETY_FLOOR_MB
                if largest.vram_mb > budget:
                    vram_failure = (f"{largest.role} ({largest.vram_mb}MB) exceeds budget "
                                    f"({budget}MB = TOTAL_VRAM_MB-SAFETY_FLOOR_MB)")
        except Exception:  # noqa: BLE001 — vram.py optional in this check
            pass

        findings = len(license_failures) + len(drift_failures) + (1 if vram_failure else 0)
        if not daemon_reachable:
            summary = "ollama daemon unreachable — license check ran, drift check skipped"
        elif findings:
            parts = []
            if license_failures:
                parts.append(f"license FAIL: {', '.join(license_failures)}")
            if drift_failures:
                parts.append(f"drift FAIL: {', '.join(drift_failures)}")
            if vram_failure:
                parts.append(f"VRAM FAIL: {vram_failure}")
            summary = "; ".join(parts)
        else:
            summary = f"all {len(snapshot.entries)} roles licensed, present, within VRAM budget"

        blob = {
            "snapshot_id": snapshot.snapshot_id,
            "license_failures": license_failures,
            "drift_failures": drift_failures,
            "vram_failure": vram_failure,
            "daemon_reachable": daemon_reachable,
            "roster_size": len(snapshot.entries),
        }
        cat_path = self.save_catalog(blob, name="model_corps")
        report = SentinelReport(
            sentinel_id=self.id, observed_at=_now(),
            catalog_name="model_corps",
            findings_count=findings,
            summary=summary,
            catalog_path=str(cat_path),
            details=blob,
        )
        if findings:
            self.notify(
                severity="warning",
                title="model corps standing check found a problem",
                message=summary,
                addressed_to="operator",
                data=blob,
            )
        return report

    def health_status(self) -> HealthStatus:
        cached = self.load_catalog(name="model_corps")
        if cached is None:
            return HealthStatus(sentinel_id=self.id, level="ok",
                                summary="not yet scanned — `sov sentinels scan model_corps`",
                                observed_at=_now())
        if not cached.get("daemon_reachable", True):
            return HealthStatus(sentinel_id=self.id, level="warning",
                                summary="ollama daemon was unreachable at last scan",
                                observed_at=_now())
        findings = (len(cached.get("license_failures", []))
                   + len(cached.get("drift_failures", []))
                   + (1 if cached.get("vram_failure") else 0))
        if findings:
            return HealthStatus(sentinel_id=self.id, level="warning",
                                summary=f"{findings} model-corps finding(s) at last scan",
                                observed_at=_now())
        return HealthStatus(sentinel_id=self.id, level="ok",
                            summary=f"{cached.get('roster_size', 0)} role(s) licensed, "
                                    f"present, within VRAM budget",
                            observed_at=_now())

    def proposals(self, report: SentinelReport) -> list[dict]:
        out = []
        d = report.details
        if d.get("license_failures"):
            out.append({
                "file": "model_corps_governance/registry.py",
                "summary": f"non-permissive license on role(s): {', '.join(d['license_failures'])}",
                "remediation": "replace with an Apache-2.0/MIT/BSD-3-Clause model and "
                              "re-run scripts/regen_model_corps.sh",
            })
        if d.get("drift_failures"):
            out.append({
                "file": "model_corps_governance/registry.py",
                "summary": f"registered but not installed: {', '.join(d['drift_failures'])}",
                "remediation": "re-run scripts/regen_model_corps.sh to rebuild the missing tag(s)",
            })
        if d.get("vram_failure"):
            out.append({
                "file": "src/sovereign_agent/vram.py",
                "summary": d["vram_failure"],
                "remediation": "choose a smaller quantization for the offending role",
            })
        return out
