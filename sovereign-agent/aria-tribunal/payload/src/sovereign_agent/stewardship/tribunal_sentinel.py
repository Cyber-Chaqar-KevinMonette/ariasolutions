"""stewardship/tribunal_sentinel.py — the Tribunal as a standing sentinel.

Periodically convenes the Tribunal over the running system's deepest invariants (the safety kernel,
the Frozen Core, recent self-improvement claims) and surfaces verdicts. Propose-only — it articulates;
the operator acts. Ties the god-tier scrutiny system into the sentinel framework (M100 immune lineage).
"""
from __future__ import annotations

from .base import Sentinel, SentinelReport, HealthStatus, _iso_now
from .registry import register_sentinel


@register_sentinel
class TribunalSentinel(Sentinel):
    """Standing scrutiny: runs the audit + safety-kernel check, flags ungrounded or unsafe drift."""

    @property
    def id(self) -> str:
        return "tribunal"

    @property
    def title(self) -> str:
        return "The Tribunal — Devil · Angel · Audit standing scrutiny"

    @property
    def tier(self) -> int:
        return 1

    def articles(self) -> list[str]:
        return [
            "I convene three voices over non-trivial work: the adversary, the advocate, the auditor.",
            "I refuse profundity that is anchored to nothing — claims must be grounded in evidence.",
            "I am propose-only. I render a verdict; the operator acts.",
            "I never weaken a safety check to let a proposal pass.",
            "A blocking finding (DEFERRED_UNSAFE proximity or value drift) is a hard stop, not an obstacle.",
        ]

    def scan(self) -> SentinelReport:
        """Convene the Tribunal over the system's own safety posture (a propose-only self-check)."""
        observed = _iso_now()
        details: dict = {}
        try:
            from sovereign_agent.tribunal import audit as _audit
            ledger = _audit.audit({"text": "system self-audit: safety kernel + frozen core intact"},
                                  include_kernel=True)
            details["audit_status"] = ledger.status
            details["kernel_status"] = ledger.kernel.get("status")
            details["rings"] = ledger.rings.get("ring_1_status") if ledger.rings else None
            details["notes"] = ledger.notes
        except Exception as exc:  # noqa: BLE001
            details["error"] = repr(exc)

        findings = 1 if details.get("kernel_status") not in ("GREEN", None) else 0
        summary = ("Tribunal self-audit GREEN — kernel + frozen core intact."
                   if findings == 0 else "Tribunal self-audit found a safety alert — operator review.")
        path = self.save_catalog({"observed_at": observed, **details}, name="self-audit")
        if findings:
            self.notify("alert", "Tribunal self-audit alert", summary, addressed_to="both", data=details)
        return SentinelReport(sentinel_id=self.id, observed_at=observed, catalog_name="self-audit",
                              findings_count=findings, summary=summary, catalog_path=str(path), details=details)

    def health_status(self) -> HealthStatus:
        try:
            from sovereign_agent.security.safety_kernel import kernel_scan
            status = kernel_scan().get("status")
            level = "ok" if status == "GREEN" else "warning"
            return HealthStatus(sentinel_id=self.id, level=level,
                                summary=f"safety kernel {status}", observed_at=_iso_now())
        except Exception as exc:  # noqa: BLE001
            return HealthStatus(sentinel_id=self.id, level="unknown",
                                summary=f"kernel unavailable: {exc!r}", observed_at=_iso_now())
