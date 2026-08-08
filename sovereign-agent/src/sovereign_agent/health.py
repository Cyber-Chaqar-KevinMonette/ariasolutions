"""
╔══════════════════════════════════════════════════════════════════════════╗
║  health.py — Anti-zombie & anti-ghost detection                          ║
║  v0.2.13                                                                  ║
║                                                                           ║
║  Two failure modes haunt long-running agent systems:                    ║
║                                                                           ║
║    ZOMBIES  — work that's "running" but isn't. A continuation marked    ║
║               in_progress whose driver process died. A lock file held    ║
║               by a PID that's no longer in the process table. Looks     ║
║               busy, isn't.                                               ║
║                                                                           ║
║    GHOSTS   — work that's "done" but lingers. A dream session marked    ║
║               active with no current cycle and no recent updates. A     ║
║               cycle continuation orphaned by its dream's deletion.      ║
║               Looks gone, isn't.                                         ║
║                                                                           ║
║  This module finds them. ``sov health check`` runs a read-only audit;   ║
║  ``sov health repair --dry-run`` previews fixes; ``sov health repair``  ║
║  applies them with a confirmation prompt for anything destructive.      ║
║                                                                           ║
║  Also includes the IDLE CYCLE detector — when a dream's last N cycles   ║
║  produced near-zero novelty, we flag it so the operator can decide      ║
║  whether to keep going. Idle dreams burn tokens forever otherwise.      ║
║                                                                           ║
║  All detection is conservative: prefer false positives (flagged but     ║
║  fine) over false negatives (zombie missed, lock held forever).         ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from . import edge_cases


# ─── Thresholds (tuned conservatively) ──────────────────────────────────────
# Operators can override at call time. Defaults err on "give it more time."

ZOMBIE_THRESHOLD_SECONDS = 6 * 3600       # 6 hours stalled in_progress
STALE_LOCK_THRESHOLD_SECONDS = 1 * 3600   # 1 hour past expected
GHOST_DREAM_THRESHOLD_SECONDS = 1 * 3600  # 1 hour idle on active dream
IDLE_CYCLE_WINDOW = 3                      # last N cycles checked
IDLE_ATOM_THRESHOLD = 1                    # ≤ this many = idle


# ─── Findings ───────────────────────────────────────────────────────────────


Severity = Literal["info", "warn", "error"]


@dataclass
class HealthFinding:
    """One issue surfaced by the health scan."""
    edge_case_id: str         # which EC fired (look up via edge_cases.get)
    severity: Severity
    target: str               # e.g. "cont-01J..." or "dream-01J..."
    target_kind: str          # "continuation" | "dream" | "lock" | "cycle"
    summary: str              # one-line description
    details: dict = field(default_factory=dict)


@dataclass
class HealthReport:
    """Aggregated scan result."""
    findings: list[HealthFinding] = field(default_factory=list)
    started_at: str = ""
    ended_at: str = ""

    @property
    def ok(self) -> bool:
        """No findings of severity error or critical."""
        return not any(f.severity in ("error", "critical") for f in self.findings)

    def by_severity(self, sev: Severity) -> list[HealthFinding]:
        return [f for f in self.findings if f.severity == sev]

    def summary_line(self) -> str:
        n = len(self.findings)
        if not n:
            return "no issues found"
        counts: dict[str, int] = {}
        for f in self.findings:
            counts[f.severity] = counts.get(f.severity, 0) + 1
        parts = [f"{v} {k}" for k, v in sorted(counts.items())]
        return f"{n} findings: {', '.join(parts)}"


# ─── Detectors ──────────────────────────────────────────────────────────────


def _utc_now_seconds() -> float:
    return datetime.now(timezone.utc).timestamp()


def _parse_iso_to_seconds(iso: str) -> float | None:
    """Parse our YAML-stored ISO timestamps to epoch seconds. Lenient."""
    if not iso:
        return None
    candidates = (
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S",
    )
    for fmt in candidates:
        try:
            dt = datetime.strptime(iso, fmt).replace(tzinfo=timezone.utc)
            return dt.timestamp()
        except ValueError:
            continue
    return None


def _process_alive(pid: int) -> bool:
    """Cross-platform 'is this PID alive?' check.

    Linux: kill(pid, 0) raises ProcessLookupError if dead. We swallow
    PermissionError because that means the process exists but we can't
    signal it (good enough for liveness).
    """
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False


def scan_zombies(
    cont_store, *,
    threshold_seconds: int = ZOMBIE_THRESHOLD_SECONDS,
) -> list[HealthFinding]:
    """Find continuations stalled in_progress with no live driver."""
    findings: list[HealthFinding] = []
    now = _utc_now_seconds()
    threshold = float(threshold_seconds)

    try:
        conts = cont_store.list_all()
    except Exception:  # noqa: BLE001
        return findings

    for c in conts:
        if c.status != "in_progress":
            continue

        updated_seconds = _parse_iso_to_seconds(getattr(c, "updated_at", ""))
        if updated_seconds is None:
            continue
        idle_for = now - updated_seconds
        if idle_for < threshold:
            continue

        # If a lock file exists AND its owner is alive, NOT a zombie.
        try:
            lock_alive = _has_live_lock(cont_store, c.task_id)
        except Exception:  # noqa: BLE001
            lock_alive = False
        if lock_alive:
            continue

        findings.append(HealthFinding(
            edge_case_id="EC-HEALTH-001",
            severity="warn",
            target=c.task_id,
            target_kind="continuation",
            summary=(
                f"continuation {c.task_id} stalled in_progress for "
                f"{int(idle_for / 3600)}h with no live driver"
            ),
            details={
                "task_id": c.task_id, "planner": c.planner,
                "updated_at": getattr(c, "updated_at", ""),
                "idle_seconds": int(idle_for),
            },
        ))

    return findings


def _has_live_lock(cont_store, task_id: str) -> bool:
    """Check if a task's .lock file is held by a living process.

    Uses the ContinuationStore's lock-path convention. If the store
    doesn't expose a way to compute lock paths, falls back to looking
    for a `<task_id>.lock` file next to the YAML.
    """
    lock_path: Path | None = None
    if hasattr(cont_store, "_lock_path"):
        try:
            lock_path = Path(cont_store._lock_path(task_id))
        except Exception:  # noqa: BLE001
            lock_path = None
    if lock_path is None:
        base = Path(getattr(cont_store, "root", "."))
        lock_path = base / f"{task_id}.lock"

    if not lock_path.exists():
        return False

    # Lock files often contain the PID. If readable, check liveness.
    try:
        text = lock_path.read_text(encoding="utf-8").strip()
        if text.isdigit():
            return _process_alive(int(text))
    except OSError:
        pass

    # Fallback: assume held if file exists and is recent.
    try:
        age = time.time() - lock_path.stat().st_mtime
        return age < STALE_LOCK_THRESHOLD_SECONDS
    except OSError:
        return False


def scan_stale_locks(
    cont_store, *,
    threshold_seconds: int = STALE_LOCK_THRESHOLD_SECONDS,
) -> list[HealthFinding]:
    """Find lock files held by dead processes."""
    findings: list[HealthFinding] = []
    base = Path(getattr(cont_store, "root", "."))
    if not base.exists():
        return findings

    for lock_path in sorted(base.glob("*.lock")):
        try:
            age = time.time() - lock_path.stat().st_mtime
            text = lock_path.read_text(encoding="utf-8").strip()
        except OSError:
            continue

        if age < threshold_seconds:
            continue

        is_alive = False
        if text.isdigit():
            is_alive = _process_alive(int(text))

        if is_alive:
            continue

        task_id = lock_path.stem
        findings.append(HealthFinding(
            edge_case_id="EC-CONT-002",
            severity="warn",
            target=task_id,
            target_kind="lock",
            summary=(
                f"lock {lock_path.name} ({int(age / 60)}min old) owned "
                f"by dead PID {text or '?'}"
            ),
            details={
                "lock_path": str(lock_path), "age_seconds": int(age),
                "owner_pid": text,
            },
        ))

    return findings


def scan_ghosts(
    dream_store, cont_store, *,
    threshold_seconds: int = GHOST_DREAM_THRESHOLD_SECONDS,
) -> list[HealthFinding]:
    """Find dreams that are 'active' but stalled, and orphan cycles."""
    findings: list[HealthFinding] = []
    now = _utc_now_seconds()

    # ── Ghost dreams ────────────────────────────────────────────────────
    try:
        dreams = dream_store.list_all(status="active")
    except Exception:  # noqa: BLE001
        dreams = []

    for d in dreams:
        if d.current_cycle_task_id is not None:
            # Has a current cycle; is THAT alive? If the cycle continuation
            # exists AND isn't drained, the dream is fine.
            try:
                cont = cont_store.get(d.current_cycle_task_id)
                if not cont.is_drained() and cont.status != "paused":
                    continue
            except Exception:  # noqa: BLE001
                pass

        updated_seconds = _parse_iso_to_seconds(getattr(d, "updated_at", ""))
        if updated_seconds is None:
            continue
        idle_for = now - updated_seconds
        if idle_for < threshold_seconds:
            continue

        findings.append(HealthFinding(
            edge_case_id="EC-HEALTH-002",
            severity="warn",
            target=d.dream_id,
            target_kind="dream",
            summary=(
                f"dream {d.dream_id} active but idle for "
                f"{int(idle_for / 3600)}h with no live cycle"
            ),
            details={
                "dream_id": d.dream_id, "updated_at": d.updated_at,
                "idle_seconds": int(idle_for),
                "current_cycle_task_id": d.current_cycle_task_id,
            },
        ))

    # ── Orphan cycle continuations ──────────────────────────────────────
    try:
        all_conts = cont_store.list_all()
    except Exception:  # noqa: BLE001
        return findings

    try:
        all_dreams = dream_store.list_all()
    except Exception:  # noqa: BLE001
        all_dreams = []

    known_cycle_task_ids = set()
    for d in all_dreams:
        for cycle in getattr(d, "cycles", []):
            tid = getattr(cycle, "task_id", None)
            if tid:
                known_cycle_task_ids.add(tid)

    for c in all_conts:
        if not c.task_id.startswith("cycle-"):
            continue
        if c.task_id in known_cycle_task_ids:
            continue

        findings.append(HealthFinding(
            edge_case_id="EC-HEALTH-003",
            severity="info",
            target=c.task_id,
            target_kind="cycle",
            summary=f"cycle continuation {c.task_id} not owned by any dream",
            details={"task_id": c.task_id, "planner": c.planner,
                     "status": c.status},
        ))

    return findings


def scan_idle_cycles(
    dream_store,
    *,
    window: int = IDLE_CYCLE_WINDOW,
    atom_threshold: int = IDLE_ATOM_THRESHOLD,
) -> list[HealthFinding]:
    """Detect dreams whose last N cycles produced near-zero novelty.

    The CycleEntry stores ``files_written`` per cycle. We use that as a
    proxy for novelty — a cycle that produced ≤ atom_threshold files has
    almost certainly produced ≤ atom_threshold novel atoms. Coarse but
    reliable.

    Returns findings (severity=info) for each idle dream. The dream-
    runner can also call this inline before each advance to auto-pause.
    """
    findings: list[HealthFinding] = []
    try:
        dreams = dream_store.list_all(status="active")
    except Exception:  # noqa: BLE001
        return findings

    for d in dreams:
        cycles = getattr(d, "cycles", [])
        if len(cycles) < window:
            continue
        recent = cycles[-window:]
        if not all(getattr(c, "files_written", 0) <= atom_threshold for c in recent):
            continue
        findings.append(HealthFinding(
            edge_case_id="EC-DREAM-006",
            severity="info",
            target=d.dream_id,
            target_kind="dream",
            summary=(
                f"dream {d.dream_id} idle: last {window} cycles each "
                f"produced ≤ {atom_threshold} files"
            ),
            details={
                "dream_id": d.dream_id, "window": window,
                "recent_files": [getattr(c, "files_written", 0) for c in recent],
            },
        ))

    return findings


# ─── Top-level scan ─────────────────────────────────────────────────────────


def run_full_scan(
    cont_store, dream_store,
    *,
    zombie_threshold: int = ZOMBIE_THRESHOLD_SECONDS,
    stale_lock_threshold: int = STALE_LOCK_THRESHOLD_SECONDS,
    ghost_threshold: int = GHOST_DREAM_THRESHOLD_SECONDS,
    idle_window: int = IDLE_CYCLE_WINDOW,
    idle_atom_threshold: int = IDLE_ATOM_THRESHOLD,
) -> HealthReport:
    """Run all health detectors. Read-only — no repairs."""
    started = datetime.now(timezone.utc).isoformat()
    findings: list[HealthFinding] = []

    findings.extend(scan_zombies(cont_store, threshold_seconds=zombie_threshold))
    findings.extend(scan_stale_locks(cont_store, threshold_seconds=stale_lock_threshold))
    findings.extend(scan_ghosts(
        dream_store, cont_store, threshold_seconds=ghost_threshold,
    ))
    findings.extend(scan_idle_cycles(
        dream_store, window=idle_window, atom_threshold=idle_atom_threshold,
    ))

    # Track each finding for telemetry.
    for f in findings:
        edge_cases.track(f.edge_case_id, payload={
            "target": f.target, "target_kind": f.target_kind,
            "summary": f.summary,
        })

    return HealthReport(
        findings=findings,
        started_at=started,
        ended_at=datetime.now(timezone.utc).isoformat(),
    )


# ─── Repair ─────────────────────────────────────────────────────────────────


@dataclass
class RepairAction:
    """One proposed or applied repair step."""
    finding_id: str       # which finding this action addresses
    kind: str             # "remove_lock" | "cancel_continuation" | "pause_dream"
    target: str
    description: str
    applied: bool = False
    error: str = ""


def plan_repairs(report: HealthReport) -> list[RepairAction]:
    """Map findings to proposed repair actions. PURE — does NOT touch disk."""
    actions: list[RepairAction] = []
    for f in report.findings:
        if f.edge_case_id == "EC-CONT-002":
            actions.append(RepairAction(
                finding_id=f.target,
                kind="remove_lock",
                target=f.details.get("lock_path", ""),
                description=f"remove stale lock {f.details.get('lock_path', '')}",
            ))
        elif f.edge_case_id == "EC-HEALTH-001":
            actions.append(RepairAction(
                finding_id=f.target,
                kind="reset_to_planned",
                target=f.target,
                description=(
                    f"reset zombie continuation {f.target} from "
                    f"in_progress → planned (or accept and resume)"
                ),
            ))
        elif f.edge_case_id == "EC-DREAM-006":
            actions.append(RepairAction(
                finding_id=f.target,
                kind="pause_idle_dream",
                target=f.target,
                description=f"pause idle dream {f.target}",
            ))
        elif f.edge_case_id == "EC-HEALTH-003":
            actions.append(RepairAction(
                finding_id=f.target,
                kind="cancel_orphan_cycle",
                target=f.target,
                description=(
                    f"cancel orphan cycle continuation {f.target}"
                ),
            ))
    return actions


def apply_repairs(
    actions: list[RepairAction], *,
    cont_store=None, dream_store=None,
    dry_run: bool = True,
) -> list[RepairAction]:
    """Execute repair actions. ``dry_run=True`` is the safe default.

    Returns the same list with `.applied` and `.error` populated.
    """
    for action in actions:
        if dry_run:
            action.applied = False
            continue

        try:
            if action.kind == "remove_lock":
                p = Path(action.target)
                if p.exists():
                    p.unlink()
                action.applied = True
            elif action.kind == "reset_to_planned" and cont_store is not None:
                with cont_store.lock(action.target,
                                     blocking=False) as cont:
                    cont.status = "planned"
                action.applied = True
            elif action.kind == "pause_idle_dream" and dream_store is not None:
                d = dream_store.get(action.target)
                d.status = "paused"
                d.notes = (d.notes + "\n" if d.notes else "") + \
                          "PAUSED by health auto-detect (idle cycles)"
                dream_store.save(d)
                action.applied = True
            elif action.kind == "cancel_orphan_cycle" and cont_store is not None:
                with cont_store.lock(action.target,
                                     blocking=False) as cont:
                    cont.status = "cancelled"
                action.applied = True
            else:
                action.error = "unknown action kind or missing store"
        except Exception as e:  # noqa: BLE001
            action.error = str(e)
            action.applied = False

    return actions


__all__ = [
    "GHOST_DREAM_THRESHOLD_SECONDS",
    "IDLE_ATOM_THRESHOLD",
    "IDLE_CYCLE_WINDOW",
    "STALE_LOCK_THRESHOLD_SECONDS",
    "ZOMBIE_THRESHOLD_SECONDS",
    "HealthFinding",
    "HealthReport",
    "RepairAction",
    "Severity",
    "apply_repairs",
    "plan_repairs",
    "run_full_scan",
    "scan_ghosts",
    "scan_idle_cycles",
    "scan_stale_locks",
    "scan_zombies",
]
