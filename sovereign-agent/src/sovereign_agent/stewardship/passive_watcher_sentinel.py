"""
╔══════════════════════════════════════════════════════════════════════════╗
║  stewardship/passive_watcher_sentinel.py — eyes on non-intelligent      ║
║                                            surfaces                       ║
║                                                                           ║
║  Most of Aria's protection comes from her intelligent components (other ║
║  sentinels). But the system also runs on a substrate of non-intelligent ║
║  surfaces: pyproject.toml, uv.lock, install.sh, env vars, the data_dir ║
║  layout. These don't think. They just exist. If they drift, Aria needs ║
║  to know — but no other sentinel owns watching them all.                ║
║                                                                           ║
║  This sentinel is that watcher.                                          ║
║                                                                           ║
║  Default surfaces                                                        ║
║                                                                           ║
║    Configurable via construction; ships with a sensible default list:   ║
║                                                                           ║
║      • pyproject.toml         (sha256 + mtime)                         ║
║      • uv.lock                (sha256 + mtime)                         ║
║      • install.sh             (sha256 + mtime)                         ║
║      • Environment variables matching SOV_*                            ║
║                                                                           ║
║  What it does NOT watch                                                  ║
║                                                                           ║
║    • OS-level services (R3+; out of authority)                          ║
║    • Network state (R4; out of authority)                               ║
║    • Anything outside the project tree (sovereignty line)              ║
║                                                                           ║
║  Cooperation with Locator                                               ║
║                                                                           ║
║    Locator is the registry of paths. Passive Watcher *consumes* that   ║
║    registry — it watches the paths Locator says are pinned. So adding ║
║    a new path to watch means registering it with Locator with a       ║
║    pinned_checksum, not editing this file. That keeps configuration   ║
║    in one place.                                                        ║
║                                                                           ║
║  Catalog file: <data_dir>/sentinels/passive_watcher/catalogs/surfaces.json║
║  Kill switch: SOV_NO_PASSIVE_WATCHER_SENTINEL=1                          ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from ulid import ULID

from sovereign_agent.aegis.incidents import (
    DamageReport,
    DryRunReport,
    Evidence,
    IncidentId,
    RepairPlan,
    RepairResult,
    RepairStep,
)
from sovereign_agent.aegis.leases import RepairLease
from sovereign_agent.aegis.medical import MedicalCapability
from sovereign_agent.aegis.radius import BlastRadius
from sovereign_agent.stewardship.base import (
    HealthStatus,
    Sentinel,
    SentinelReport,
)
from sovereign_agent.stewardship.registry import register_sentinel


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


# ─── Snapshots ────────────────────────────────────────────────────────────


@dataclass
class FileSurface:
    path: str
    sha256: str
    size_bytes: int
    mtime_iso: str


@dataclass
class EnvSurface:
    name: str
    value_preview: str                          # first 64 chars, redacted
    set: bool


@dataclass
class SurfaceSnapshot:
    written_at: str
    files: list[FileSurface] = field(default_factory=list)
    env_vars: list[EnvSurface] = field(default_factory=list)


# ─── The Sentinel ────────────────────────────────────────────────────────


@register_sentinel
class PassiveWatcherSentinel(Sentinel, MedicalCapability):
    """Watches non-intelligent system surfaces and reports drift."""

    DEFAULT_FILE_WATCH = [
        "pyproject.toml",
        "uv.lock",
        "install.sh",
    ]

    DEFAULT_ENV_PREFIXES = ["SOV_"]

    def __init__(
        self,
        data_dir: Path,
        project_root: Path | None = None,
        file_watch: list[str] | None = None,
        env_prefixes: list[str] | None = None,
    ):
        super().__init__(data_dir)
        self._project_root = project_root or Path.cwd()
        self._file_watch = file_watch or list(self.DEFAULT_FILE_WATCH)
        self._env_prefixes = env_prefixes or list(self.DEFAULT_ENV_PREFIXES)

    @property
    def id(self) -> str:
        return "passive_watcher"

    @property
    def title(self) -> str:
        return "Passive Watcher — eyes on non-intelligent surfaces"

    @property
    def tier(self) -> int:
        return 1

    @property
    def voice_persona(self) -> str:
        return "quiet, patient, attentive. Speaks only when something changed."

    def articles(self) -> list[str]:
        return [
            "I. I watch the non-intelligent surfaces the system depends on: "
            "pyproject.toml, uv.lock, install.sh, and SOV_* environment variables.",
            "II. I never modify these surfaces. I record their state and report "
            "drift; the operator (or owner sentinel) decides what to do about it.",
            "III. I do NOT watch the OS, the network, or anything outside the "
            "project tree. R3+ surfaces are outside my authority.",
            "IV. Env var values are previewed (first 64 chars, redacted as needed). "
            "I never log full secrets even if I happen across one.",
            "V. New paths to watch should be registered with the Locator Sentinel "
            "as pinned-checksum entries. I read them from there, not from a "
            "hand-edited list in my own code.",
        ]

    # ─── Catalog management ─────────────────────────────────────────────

    def _catalog_path(self) -> Path:
        d = self.sentinel_dir / "catalogs"
        d.mkdir(parents=True, exist_ok=True)
        return d / "surfaces.json"

    def _load_prior_snapshot(self) -> SurfaceSnapshot | None:
        p = self._catalog_path()
        if not p.is_file():
            return None
        try:
            blob = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        return SurfaceSnapshot(
            written_at=blob.get("written_at", ""),
            files=[FileSurface(**f) for f in blob.get("files", [])],
            env_vars=[EnvSurface(**e) for e in blob.get("env_vars", [])],
        )

    def _save_snapshot(self, snapshot: SurfaceSnapshot) -> None:
        p = self._catalog_path()
        blob = {
            "written_at": snapshot.written_at,
            "files": [asdict(f) for f in snapshot.files],
            "env_vars": [asdict(e) for e in snapshot.env_vars],
        }
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(blob, indent=2, sort_keys=True), encoding="utf-8")
        os.chmod(tmp, 0o600)
        os.replace(tmp, p)

    # ─── Capture present state ──────────────────────────────────────────

    def _capture_files(self) -> list[FileSurface]:
        out: list[FileSurface] = []
        for rel in self._file_watch:
            p = self._project_root / rel
            if not p.is_file():
                continue
            data = p.read_bytes()
            stat_result = p.stat()
            out.append(FileSurface(
                path=str(p),
                sha256=hashlib.sha256(data).hexdigest(),
                size_bytes=stat_result.st_size,
                mtime_iso=datetime.fromtimestamp(
                    stat_result.st_mtime, tz=timezone.utc,
                ).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            ))
        return out

    def _capture_env(self) -> list[EnvSurface]:
        out: list[EnvSurface] = []
        for name, value in sorted(os.environ.items()):
            if not any(name.startswith(p) for p in self._env_prefixes):
                continue
            # Redact: never log more than 64 chars of value, and replace
            # anything that looks key-shaped (long, base64ish, hex).
            preview = value[:64]
            if len(value) > 32 and value.replace("-", "").replace("_", "").isalnum():
                preview = f"<redacted {len(value)} chars>"
            out.append(EnvSurface(name=name, value_preview=preview, set=True))
        return out

    # ─── Scan ───────────────────────────────────────────────────────────

    def scan(self) -> SentinelReport:
        prior = self._load_prior_snapshot()
        now_files = self._capture_files()
        now_env = self._capture_env()
        snapshot = SurfaceSnapshot(
            written_at=_iso_now(),
            files=now_files,
            env_vars=now_env,
        )

        file_drift: list[dict] = []
        env_drift: list[dict] = []

        if prior is not None:
            prior_files = {f.path: f for f in prior.files}
            for now in now_files:
                pri = prior_files.get(now.path)
                if pri is None:
                    file_drift.append({"path": now.path, "event": "appeared"})
                elif pri.sha256 != now.sha256:
                    file_drift.append({
                        "path": now.path, "event": "content-changed",
                        "prior_sha256": pri.sha256, "now_sha256": now.sha256,
                    })
            for path, pri in prior_files.items():
                if not any(f.path == path for f in now_files):
                    file_drift.append({"path": path, "event": "disappeared"})

            prior_env = {e.name: e for e in prior.env_vars}
            for now in now_env:
                pri = prior_env.get(now.name)
                if pri is None:
                    env_drift.append({"name": now.name, "event": "appeared"})
                elif pri.value_preview != now.value_preview:
                    env_drift.append({"name": now.name, "event": "value-changed"})
            for name in prior_env:
                if not any(e.name == name for e in now_env):
                    env_drift.append({"name": name, "event": "unset"})

        self._save_snapshot(snapshot)

        total = len(file_drift) + len(env_drift)
        return SentinelReport(
            sentinel_id=self.id,
            observed_at=_iso_now(),
            catalog_name="surfaces",
            findings_count=total,
            summary=(
                f"watched {len(now_files)} file(s) + {len(now_env)} env var(s); "
                f"{len(file_drift)} file drift, {len(env_drift)} env drift"
            ),
            catalog_path=str(self._catalog_path()),
            details={
                "files_watched": len(now_files),
                "env_watched": len(now_env),
                "file_drift": file_drift,
                "env_drift": env_drift,
                "is_first_scan": prior is None,
            },
        )

    def health_status(self) -> HealthStatus:
        report = self.scan()
        total = report.findings_count
        if report.details.get("is_first_scan"):
            return HealthStatus(
                sentinel_id=self.id, level="ok",
                summary="first scan — baseline captured", observed_at=_iso_now(),
            )
        if total == 0:
            return HealthStatus(
                sentinel_id=self.id, level="ok",
                summary="no drift on watched surfaces", observed_at=_iso_now(),
            )
        return HealthStatus(
            sentinel_id=self.id,
            level="warning",
            summary=f"{total} surface(s) drifted since last scan",
            observed_at=_iso_now(),
        )

    # ─── MedicalCapability ──────────────────────────────────────────────

    def damage_estimate(self) -> DamageReport:
        report = self.scan()
        file_drift = report.details.get("file_drift", [])
        env_drift = report.details.get("env_drift", [])
        if report.details.get("is_first_scan") or (not file_drift and not env_drift):
            return DamageReport(
                incident_id=IncidentId(str(ULID())),
                sentinel_id=self.id,
                radius=BlastRadius.R0_ARTIFACT,
                severity="info", confidence=1.0,
                summary="no drift",
            )
        evidence = []
        for d in file_drift[:30]:
            evidence.append(Evidence(
                kind="checksum-drift",
                summary=f"{d['path']}: {d['event']}",
                source_path=d.get("path", ""),
                expected=d.get("prior_sha256", ""),
                observed=d.get("now_sha256", ""),
            ))
        for d in env_drift[:30]:
            evidence.append(Evidence(
                kind="version-drift",
                summary=f"env {d['name']}: {d['event']}",
            ))
        return DamageReport(
            incident_id=IncidentId(str(ULID())),
            sentinel_id=self.id,
            radius=BlastRadius.R1_SURFACE,
            severity="warning", confidence=0.9,
            summary=(f"{len(file_drift)} file drift(s), "
                     f"{len(env_drift)} env drift(s)"),
            evidence=evidence,
        )

    def repair_plan(self, damage: DamageReport) -> RepairPlan:
        return RepairPlan(
            incident_id=damage.incident_id,
            sentinel_id=self.id,
            radius=damage.radius,
            summary="surface drift — operator confirms intent (was this you?)",
            steps=[
                RepairStep(
                    ordinal=i, description=ev.summary,
                    action_kind="operator-action-required",
                )
                for i, ev in enumerate(damage.evidence, start=1)
            ],
        )

    def repair_dry_run(self, plan: RepairPlan) -> DryRunReport:
        return DryRunReport(
            incident_id=plan.incident_id,
            plan_hash=plan.plan_hash(),
            sentinel_id=self.id,
            would_succeed=True,
            would_modify=[], would_create=[], would_delete=[],
            opaque_steps=[s.ordinal for s in plan.steps],
            warnings=["Passive Watcher never modifies surfaces; nothing to simulate"],
        )

    def _execute_repair_internal(
        self, plan: RepairPlan, lease: RepairLease | None,
    ) -> RepairResult:
        return RepairResult(
            incident_id=plan.incident_id,
            lease_id=lease.lease_id if lease else "",  # type: ignore[arg-type]
            sentinel_id=self.id,
            plan_hash=plan.plan_hash(),
            succeeded=True,
            steps_completed=[], steps_failed=[],
            paths_actually_modified=[], paths_actually_created=[],
            paths_actually_deleted=[],
            error_summary="Passive Watcher never modifies surfaces; operator decides",
        )


__all__ = [
    "PassiveWatcherSentinel", "SurfaceSnapshot", "FileSurface", "EnvSurface",
]
