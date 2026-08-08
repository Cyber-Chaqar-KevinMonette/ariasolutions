"""vessel_health.py — Workstream I: the Vessel-Health organ.

The Plans folder's hundreds of "Flourishing Phase Space / Kernel Curvature
Tensor / Ego Potential Well"-style constructs are evocative names over
ideas Aria substantially already has. Rather than build 260 poetic
non-modules, this distills their buildable essence into ONE real, concrete
rollup — pure reads over metrics that already exist, no new storage:

  - kernel-coherence : H2's CanonEmbodimentReport (% mos_canon.py clauses
                        cited outside their own declaration).
  - sentinel health   : stewardship.registry.gather_health() (already
                        exists — this organ is mostly a *view*).
  - drift             : the SAME gather_health() call's own `conformance`
                        entry — no separate baseline-comparison check was
                        built; ConformanceSentinel already IS the drift
                        signal the plan asked for ("if present" — it is).
  - signal            : H3's EpistemicLedger — average confidence across
                        current_beliefs() + count of open Uncertainty
                        entries (a genuine, already-live proxy; there is
                        no single existing "signal/noise" aggregate
                        function to call instead).
  - flourishing trend : C's ApplyQueueStore (applied count) vs
                        QuarantineRegistry (still-quarantined count).

Deliberately NOT cached here. `gather_vessel_health()`'s kernel-coherence
component runs a full-tree clause-citation scan (~3s over ~450 files,
same order of magnitude as J's Tier-A scan_tree()) — a caller that
refreshes this on a timer (the cockpit) MUST cache that part itself and
pass `include_kernel_coherence=False` on the fast path, exactly mirroring
`aria-security-strip-wire`'s hard-won, already-proven pattern (module-
level cache + lock + background `@work(thread=True)` worker, never kicked
off eagerly on mount). This module stays a plain, uncached aggregator so
the one-shot CLI (`python -m sovereign_agent.vessel_health`) never has to
think about caching at all.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


@dataclass
class VesselHealthReport:
    generated_at: str = field(default_factory=_now)

    # kernel-coherence (H2) — None if include_kernel_coherence=False or unavailable
    kernel_coherence_ratio: float | None = None
    kernel_coherence_summary: str = "(not computed)"

    # sentinel health (gather_health)
    sentinel_ok: int = 0
    sentinel_warn: int = 0
    sentinel_error: int = 0

    # drift — the conformance sentinel's own summary, pulled from the same
    # gather_health() call rather than a second, separate check
    drift_summary: str = "(unavailable)"

    # signal (H3 epistemic ledger)
    signal_avg_confidence: float | None = None
    signal_belief_count: int = 0
    open_uncertainties: int = 0

    # flourishing trend (C apply-queue / quarantine)
    flourishing_applied: int = 0
    flourishing_quarantined: int = 0

    def overall_color(self) -> str:
        """A single worst-signal-wins color for a compact one-line view."""
        if self.sentinel_error > 0:
            return "error"
        if self.sentinel_warn > 0:
            return "warning"
        return "ok"

    def summary_line(self) -> str:
        kc = (
            f"{self.kernel_coherence_summary}"
            if self.kernel_coherence_ratio is not None
            else "kernel: (not computed)"
        )
        sig = (
            f"signal {self.signal_avg_confidence:.2f} ({self.signal_belief_count} beliefs)"
            if self.signal_avg_confidence is not None
            else "signal: (no beliefs yet)"
        )
        return (
            f"{kc} · sentinels {self.sentinel_ok}ok/{self.sentinel_warn}warn/"
            f"{self.sentinel_error}err · {sig} · {self.open_uncertainties} open Qs · "
            f"flourishing {self.flourishing_applied} applied/"
            f"{self.flourishing_quarantined} quarantined"
        )

    def as_dict(self) -> dict:
        return {
            "generated_at": self.generated_at,
            "kernel_coherence_ratio": self.kernel_coherence_ratio,
            "kernel_coherence_summary": self.kernel_coherence_summary,
            "sentinel_ok": self.sentinel_ok,
            "sentinel_warn": self.sentinel_warn,
            "sentinel_error": self.sentinel_error,
            "drift_summary": self.drift_summary,
            "signal_avg_confidence": self.signal_avg_confidence,
            "signal_belief_count": self.signal_belief_count,
            "open_uncertainties": self.open_uncertainties,
            "flourishing_applied": self.flourishing_applied,
            "flourishing_quarantined": self.flourishing_quarantined,
        }


def _gather_sentinel_health(data_dir: Path, statuses=None) -> tuple[int, int, int, str]:
    """anti-lag-d: `statuses` lets a caller that has ALREADY gathered sentinel
    health (the cockpit's background status worker does, every 5s) reuse it
    instead of triggering a second full gather — instantiating every sentinel
    and running each health_status() is the most expensive read in the
    cockpit's refresh paths and must never run twice for one snapshot."""
    if statuses is None:
        from sovereign_agent.stewardship.registry import gather_health

        statuses = gather_health(data_dir)
    n_ok = sum(1 for s in statuses if s.level == "ok")
    n_warn = sum(1 for s in statuses if s.level == "warning")
    n_err = sum(1 for s in statuses if s.level == "error")

    drift_summary = "(conformance sentinel not registered)"
    for s in statuses:
        if s.sentinel_id == "conformance":
            drift_summary = s.summary
            break
    return n_ok, n_warn, n_err, drift_summary


def _gather_signal(data_dir: Path) -> tuple[float | None, int, int]:
    from sovereign_agent.epistemic_ledger.ledger import EpistemicLedger, UncertaintyRegistry

    root = data_dir / "epistemic"
    beliefs = EpistemicLedger(root).current_beliefs()
    open_unc = UncertaintyRegistry(root).list_open()

    if not beliefs:
        return None, 0, len(open_unc)
    avg_conf = sum(b.confidence for b in beliefs) / len(beliefs)
    return avg_conf, len(beliefs), len(open_unc)


def _gather_flourishing(data_dir: Path) -> tuple[int, int]:
    from sovereign_agent.apply_queue.store import ApplyQueueStore, QuarantineRegistry

    items = ApplyQueueStore(data_dir / "apply_queue").all_items()
    applied = sum(1 for it in items if it.status == "applied")

    records = QuarantineRegistry(data_dir / "quarantine").list()
    still_quarantined = sum(1 for r in records if r.status == "quarantined")
    return applied, still_quarantined


def _gather_kernel_coherence(repo_root: Path) -> tuple[float, str]:
    from sovereign_agent.canon_embodiment.mapper import find_references

    report = find_references(repo_root)
    ratio = report.embodied_count / report.total_clauses if report.total_clauses else 0.0
    return ratio, report.summary()


def gather_vessel_health(
    *,
    repo_root: Path | None = None,
    data_dir: Path | None = None,
    include_kernel_coherence: bool = True,
    sentinel_healths=None,
) -> VesselHealthReport:
    """Pure, synchronous rollup. No caching, no background work — see the
    module docstring for why a periodic caller (the cockpit) must cache
    the kernel-coherence component itself rather than calling this with
    include_kernel_coherence=True on every refresh.

    anti-lag-d: pass `sentinel_healths` (an already-gathered list of
    HealthStatus) to reuse an existing gather instead of running a second
    full sentinel scan for the same snapshot."""
    from sovereign_agent.config import SETTINGS

    if data_dir is None:
        data_dir = SETTINGS.paths.data_dir
    if repo_root is None:
        import sovereign_agent
        repo_root = Path(sovereign_agent.__file__).parent.parent.parent

    report = VesselHealthReport()

    try:
        report.sentinel_ok, report.sentinel_warn, report.sentinel_error, report.drift_summary = (
            _gather_sentinel_health(data_dir, statuses=sentinel_healths)
        )
    except Exception as exc:  # noqa: BLE001 — a vessel-health rollup must never crash
        report.drift_summary = f"(sentinel health unavailable: {type(exc).__name__})"

    try:
        report.signal_avg_confidence, report.signal_belief_count, report.open_uncertainties = (
            _gather_signal(data_dir)
        )
    except Exception:  # noqa: BLE001
        pass

    try:
        report.flourishing_applied, report.flourishing_quarantined = _gather_flourishing(data_dir)
    except Exception:  # noqa: BLE001
        pass

    if include_kernel_coherence:
        try:
            report.kernel_coherence_ratio, report.kernel_coherence_summary = (
                _gather_kernel_coherence(repo_root)
            )
        except Exception as exc:  # noqa: BLE001
            report.kernel_coherence_summary = f"(kernel-coherence unavailable: {type(exc).__name__})"

    return report


def _main() -> int:
    """`python -m sovereign_agent.vessel_health` — one-shot, no caching
    needed (unlike the cockpit strip, this runs once and exits)."""
    report = gather_vessel_health()
    print(report.summary_line())
    print()
    print(f"kernel-coherence : {report.kernel_coherence_summary}")
    print(f"sentinels        : {report.sentinel_ok} ok / {report.sentinel_warn} warn / "
          f"{report.sentinel_error} error")
    print(f"drift            : {report.drift_summary}")
    if report.signal_avg_confidence is not None:
        print(f"signal           : avg confidence {report.signal_avg_confidence:.2f} "
              f"across {report.signal_belief_count} current beliefs")
    else:
        print("signal           : no beliefs recorded yet")
    print(f"open questions   : {report.open_uncertainties}")
    print(f"flourishing      : {report.flourishing_applied} applied / "
          f"{report.flourishing_quarantined} quarantined")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(_main())
