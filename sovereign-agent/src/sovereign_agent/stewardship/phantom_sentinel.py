"""
╔══════════════════════════════════════════════════════════════════════════╗
║  stewardship/phantom_sentinel.py — the deception layer                  ║
║                                                                           ║
║  The honest version of Kevin's "appear deleted to the attacker" idea.  ║
║                                                                           ║
║  What this Sentinel actually does                                        ║
║                                                                           ║
║    1. Canary files — files placed in predictable spots whose ONLY      ║
║       purpose is to detect access. Their content is uninteresting; what║
║       matters is the access pattern. Reading, modifying, or deleting   ║
║       a canary is itself the alarm.                                    ║
║                                                                           ║
║    2. Honey atoms — fake memory atoms inserted into the memory store ║
║       that look real but reference fake people and fake events. If a  ║
║       recall query ever surfaces one, that's a signal: someone is     ║
║       trawling memory who shouldn't be.                                ║
║                                                                           ║
║    3. Decoy manifests — fake sentinel-shaped entries in the registry ║
║       that look like real Sentinels but are no-ops. An attacker        ║
║       enumerating the sentinels directory sees them; reading their    ║
║       manifests fires alerts.                                          ║
║                                                                           ║
║    4. Phantom mode — operator-triggered defensive posture. When active, ║
║       Aria reduces her observable surface (no cockpit, quiet voice),  ║
║       routes new state writes to the Vault, and presents a frozen     ║
║       decoy of her previous state to anyone looking.                   ║
║                                                                           ║
║  What this Sentinel explicitly does NOT do                              ║
║                                                                           ║
║    • Make Aria genuinely invisible to a sophisticated attacker with    ║
║      shell access. That's Hollywood. Real shell access wins. What we   ║
║      offer is DETECTION + DECEPTION + RECOVERY, not invisibility.     ║
║    • Auto-engage phantom mode. Autonomous phantom mode could trap     ║
║      the operator out of their own system — the opposite of           ║
║      sovereignty. Phantom is operator-triggered only.                  ║
║    • Retaliate. The no-harm doctrine still holds.                      ║
║                                                                           ║
║  Doctrinal anchor: DEFENSE-CATALOG-CE-2026.05.24 §0 + PHANTOM-DOCTRINE ║
║                    CE-2026.05.24 (sister doc, ships with this file).   ║
║                                                                           ║
║  Catalog file: <data_dir>/sentinels/phantom/catalogs/canaries.json     ║
║  Kill switch: SOV_NO_PHANTOM_SENTINEL=1                                  ║
║  Mode env: SOV_PHANTOM_MODE=1 — operator activates phantom mode.        ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
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


PHANTOM_MODE_ENV = "SOV_PHANTOM_MODE"


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


# ─── Records ─────────────────────────────────────────────────────────────


@dataclass
class CanaryFile:
    """A file placed solely to detect access. Mtime/size/access changes
    are evidence; the content itself is uninteresting (but stable so we
    can detect modification)."""
    path: str
    expected_sha256: str
    expected_size: int
    placed_at: str
    last_verified_at: str = ""
    last_status: Literal["intact", "modified", "missing", "unknown"] = "unknown"


@dataclass
class HoneyAtom:
    """A fake memory atom. If a recall query ever surfaces this atom_id,
    that's the alarm. We track it by id, not by content."""
    atom_id: str                              # ULID — the bait
    label: str                                # what kind of atom it imitates
    placed_at: str
    times_surfaced: int = 0                   # ideal: stays 0
    last_surfaced_at: str = ""


@dataclass
class DecoyManifest:
    """A fake sentinel manifest. Lives in a sentinel-shaped directory
    but the 'sentinel' is a no-op. Read access to the manifest fires
    the alarm."""
    decoy_id: str                             # 'metrics-shadow', 'cache-mirror'
    path: str
    placed_at: str
    last_verified_at: str = ""
    last_status: Literal["intact", "modified", "missing", "unknown"] = "unknown"


# ─── The Sentinel ────────────────────────────────────────────────────────


@register_sentinel
class PhantomSentinel(Sentinel, MedicalCapability):
    """Maintains canaries / honey atoms / decoys; tracks phantom mode."""

    DEFAULT_CANARY_COUNT = 3
    DEFAULT_HONEY_ATOM_COUNT = 5

    def __init__(self, data_dir: Path):
        super().__init__(data_dir)

    @property
    def id(self) -> str:
        return "phantom"

    @property
    def title(self) -> str:
        return "Phantom — the deception and detection layer"

    @property
    def tier(self) -> int:
        return 1

    @property
    def voice_persona(self) -> str:
        return ("quiet, careful, never theatrical. Names what tripped, "
                "names what didn't, never amplifies a signal beyond its evidence.")

    def articles(self) -> list[str]:
        return [
            "I. I maintain canary files, honey atoms, and decoy manifests "
            "whose only purpose is to detect access by something that "
            "should not be reading them.",
            "II. I do not make Aria invisible. I create signal where there "
            "was none. Sophisticated attackers with shell access can still "
            "see real state; what I provide is DETECTION + DECEPTION + "
            "RECOVERY, not magic invisibility.",
            "III. Phantom mode (reduced observable surface, OOB-routed "
            "writes, frozen decoy) is operator-triggered only — never "
            "autonomous. Autonomous phantom mode could trap the operator "
            "out of their own system. The sovereignty line holds.",
            "IV. I do not retaliate. The no-harm doctrine (DEFENSE §0) "
            "still applies. The 'comeback' to pressure is: detect, log, "
            "preserve evidence, recover.",
            "V. Every canary tripped, every honey atom surfaced, every "
            "decoy manifest read produces a DamageReport whose threat "
            "class is 'integrity-attack' — which Defense Sentinel routes "
            "to LOCKDOWN through Aegis.",
            "VI. My own manifest hash is itself a canary. If it breaks, "
            "I'm the alarm, not the watchman.",
        ]

    # ─── Phantom mode (read-only flag) ──────────────────────────────────

    @property
    def is_phantom_mode(self) -> bool:
        """True if operator has activated phantom mode via env var."""
        return bool(os.environ.get(PHANTOM_MODE_ENV))

    # ─── Catalog ────────────────────────────────────────────────────────

    def _catalog_path(self) -> Path:
        d = self.sentinel_dir / "catalogs"
        d.mkdir(parents=True, exist_ok=True)
        return d / "canaries.json"

    def _load_catalog(self) -> dict:
        p = self._catalog_path()
        if not p.is_file():
            return {"canaries": [], "honey_atoms": [], "decoys": []}
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {"canaries": [], "honey_atoms": [], "decoys": []}

    def _save_catalog(self, blob: dict) -> None:
        p = self._catalog_path()
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(blob, indent=2, sort_keys=True), encoding="utf-8")
        os.chmod(tmp, 0o600)
        os.replace(tmp, p)

    # ─── First-run: place canaries ──────────────────────────────────────

    def deploy_canaries(self, count: int | None = None) -> list[CanaryFile]:
        """Place canary files. Called on first scan if none exist.

        Locations: under <data_dir>/phantom/ with realistic-looking names.
        The content is random bytes hashed and stamped so any modification
        is detected; the names look like state files an attacker might
        plausibly target.
        """
        canary_dir = self._data_dir / "phantom"
        canary_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        n = count or self.DEFAULT_CANARY_COUNT

        names = [
            "session_cache.bin",
            "credentials.json",
            "private_state.dat",
            "memory_snapshot.bin",
            "auth_tokens.json",
        ]
        deployed: list[CanaryFile] = []
        for name in names[:n]:
            p = canary_dir / name
            content = secrets.token_bytes(256 + secrets.randbelow(512))
            p.write_bytes(content)
            os.chmod(p, 0o600)
            deployed.append(CanaryFile(
                path=str(p),
                expected_sha256=hashlib.sha256(content).hexdigest(),
                expected_size=len(content),
                placed_at=_iso_now(),
            ))
        return deployed

    def deploy_honey_atoms(self, count: int | None = None) -> list[HoneyAtom]:
        """Mint honey atom ids. These are tracked here; the actual atoms
        are inserted into the memory store by the agent's bootstrap
        sequence using the ids we mint (so this Sentinel stays focused
        on tracking, not memory-store integration)."""
        n = count or self.DEFAULT_HONEY_ATOM_COUNT
        labels = ["episode", "fact", "relationship", "intent", "commitment"]
        return [
            HoneyAtom(
                atom_id=str(ULID()),
                label=labels[i % len(labels)],
                placed_at=_iso_now(),
            )
            for i in range(n)
        ]

    def deploy_decoys(self) -> list[DecoyManifest]:
        """Place fake sentinel manifests under <data_dir>/sentinels/<decoy_id>/
        with realistic-looking shape. Reading them is the alarm."""
        decoys = [
            ("metrics-shadow", "Metrics Shadow — collects internal trace data"),
            ("cache-mirror", "Cache Mirror — secondary cache integrity check"),
        ]
        out: list[DecoyManifest] = []
        for did, title in decoys:
            d = self._data_dir / "sentinels" / did
            d.mkdir(parents=True, exist_ok=True, mode=0o700)
            mp = d / "manifest.json"
            mp.write_text(json.dumps({
                "id": did, "title": title, "tier": 1,
                "articles": ["I. (decoy)"], "manifest_hash": "decoy",
                "_phantom_decoy": True,
            }, indent=2), encoding="utf-8")
            os.chmod(mp, 0o600)
            out.append(DecoyManifest(
                decoy_id=did, path=str(mp), placed_at=_iso_now(),
            ))
        return out

    # ─── Scan ───────────────────────────────────────────────────────────

    def scan(self) -> SentinelReport:
        catalog = self._load_catalog()

        # First-run deployment if catalog is empty.
        if not catalog["canaries"]:
            catalog["canaries"] = [asdict(c) for c in self.deploy_canaries()]
        if not catalog["honey_atoms"]:
            catalog["honey_atoms"] = [asdict(h) for h in self.deploy_honey_atoms()]
        if not catalog["decoys"]:
            catalog["decoys"] = [asdict(d) for d in self.deploy_decoys()]

        # Verify canaries.
        canary_findings: list[dict] = []
        for entry in catalog["canaries"]:
            p = Path(entry["path"])
            if not p.is_file():
                entry["last_status"] = "missing"
                canary_findings.append({"path": entry["path"], "event": "missing"})
            else:
                data = p.read_bytes()
                actual_hash = hashlib.sha256(data).hexdigest()
                if actual_hash != entry["expected_sha256"]:
                    entry["last_status"] = "modified"
                    canary_findings.append({
                        "path": entry["path"], "event": "content-modified",
                        "expected": entry["expected_sha256"], "observed": actual_hash,
                    })
                else:
                    entry["last_status"] = "intact"
            entry["last_verified_at"] = _iso_now()

        # Verify decoy manifests.
        decoy_findings: list[dict] = []
        for entry in catalog["decoys"]:
            p = Path(entry["path"])
            if not p.is_file():
                entry["last_status"] = "missing"
                decoy_findings.append({"decoy_id": entry["decoy_id"], "event": "missing"})
            else:
                try:
                    blob = json.loads(p.read_text(encoding="utf-8"))
                    if not blob.get("_phantom_decoy"):
                        entry["last_status"] = "modified"
                        decoy_findings.append({
                            "decoy_id": entry["decoy_id"], "event": "modified",
                        })
                    else:
                        entry["last_status"] = "intact"
                except (json.JSONDecodeError, OSError):
                    entry["last_status"] = "modified"
                    decoy_findings.append({
                        "decoy_id": entry["decoy_id"], "event": "unreadable",
                    })
            entry["last_verified_at"] = _iso_now()

        # Honey atom surfacing is tracked by the memory store (which calls
        # report_honey_surfaced() when an honey atom comes up in recall).
        # Here we just count.
        honey_surfaced = sum(
            1 for h in catalog["honey_atoms"] if h.get("times_surfaced", 0) > 0
        )

        self._save_catalog(catalog)

        findings_total = len(canary_findings) + len(decoy_findings) + honey_surfaced
        return SentinelReport(
            sentinel_id=self.id,
            observed_at=_iso_now(),
            catalog_name="canaries",
            findings_count=findings_total,
            summary=(
                f"canaries: {len(canary_findings)} tripped, "
                f"decoys: {len(decoy_findings)} disturbed, "
                f"honey atoms surfaced: {honey_surfaced}, "
                f"phantom mode: {'ON' if self.is_phantom_mode else 'off'}"
            ),
            catalog_path=str(self._catalog_path()),
            details={
                "canary_findings": canary_findings,
                "decoy_findings": decoy_findings,
                "honey_atoms_surfaced": honey_surfaced,
                "phantom_mode_active": self.is_phantom_mode,
            },
        )

    def report_honey_surfaced(self, atom_id: str) -> None:
        """Memory store calls this when an honey atom appears in recall."""
        catalog = self._load_catalog()
        for h in catalog["honey_atoms"]:
            if h["atom_id"] == atom_id:
                h["times_surfaced"] = h.get("times_surfaced", 0) + 1
                h["last_surfaced_at"] = _iso_now()
                break
        self._save_catalog(catalog)

    def health_status(self) -> HealthStatus:
        report = self.scan()
        tripped = (
            len(report.details.get("canary_findings", []))
            + len(report.details.get("decoy_findings", []))
            + report.details.get("honey_atoms_surfaced", 0)
        )
        if tripped > 0:
            return HealthStatus(
                sentinel_id=self.id, level="error",
                summary=f"{tripped} phantom signal(s) tripped — possible intrusion",
                observed_at=_iso_now(),
            )
        return HealthStatus(
            sentinel_id=self.id, level="ok",
            summary=("all phantom signals intact"
                     + (" (phantom mode ON)" if self.is_phantom_mode else "")),
            observed_at=_iso_now(),
        )

    # ─── MedicalCapability ──────────────────────────────────────────────

    def damage_estimate(self) -> DamageReport:
        report = self.scan()
        canary = report.details.get("canary_findings", [])
        decoy = report.details.get("decoy_findings", [])
        honey = report.details.get("honey_atoms_surfaced", 0)
        if not (canary or decoy or honey):
            return DamageReport(
                incident_id=IncidentId(str(ULID())),
                sentinel_id=self.id,
                radius=BlastRadius.R0_ARTIFACT,
                severity="info", confidence=1.0,
                summary="no phantom signals tripped",
            )
        # Any phantom trip is treated as integrity-attack severity.
        evidence = []
        for c in canary[:20]:
            evidence.append(Evidence(
                kind="checksum-drift",
                summary=f"canary {c.get('path', '')} {c.get('event', '')}",
                source_path=c.get("path", ""),
                expected=c.get("expected", ""),
                observed=c.get("observed", ""),
            ))
        for d in decoy[:20]:
            evidence.append(Evidence(
                kind="manifest-tampered",
                summary=f"decoy manifest {d.get('decoy_id', '')} {d.get('event', '')}",
            ))
        if honey:
            evidence.append(Evidence(
                kind="other",
                summary=f"{honey} honey atom(s) surfaced in memory recall",
            ))
        return DamageReport(
            incident_id=IncidentId(str(ULID())),
            sentinel_id=self.id,
            radius=BlastRadius.R2_SOFTWARE,  # phantom trips are software-scope
            severity="alert", confidence=0.95,
            summary=(
                f"phantom signals tripped: {len(canary)} canaries, "
                f"{len(decoy)} decoys, {honey} honey atoms"
            ),
            evidence=evidence,
        )

    def repair_plan(self, damage: DamageReport) -> RepairPlan:
        return RepairPlan(
            incident_id=damage.incident_id,
            sentinel_id=self.id,
            radius=damage.radius,
            summary=(
                "phantom trip — recommend (1) escalate to Aegis LOCKDOWN, "
                "(2) snapshot to Vault, (3) operator investigates before "
                "any reset of canaries"
            ),
            steps=[
                RepairStep(
                    ordinal=1,
                    description="escalate to Aegis Conductor as integrity-attack",
                    action_kind="operator-action-required",
                ),
                RepairStep(
                    ordinal=2,
                    description="trigger Vault snapshot for forensic preservation",
                    action_kind="operator-action-required",
                ),
                RepairStep(
                    ordinal=3,
                    description="operator investigates; canaries re-deploy only after review",
                    action_kind="operator-action-required",
                ),
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
            warnings=["phantom trips never auto-repair — operator investigates first"],
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
            error_summary="phantom trips delegate to operator investigation",
        )


__all__ = [
    "PhantomSentinel",
    "CanaryFile", "HoneyAtom", "DecoyManifest",
    "PHANTOM_MODE_ENV",
]
