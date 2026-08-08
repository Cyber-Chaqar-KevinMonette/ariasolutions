"""
╔══════════════════════════════════════════════════════════════════════════╗
║  path_scan/sentinel.py — PathSentinel                                    ║
║                                                                           ║
║  Wraps the pure scanner (scanner.py) in the standard Sentinel contract   ║
║  so the doctor, the cockpit panel, and the apply gate all see one        ║
║  consistent surface. Tier 1 — propose only. It names what's wrong; the   ║
║  operator (or the apply gate) decides.                                   ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from sovereign_agent.stewardship.base import (
    HealthStatus,
    Sentinel,
    SentinelReport,
)
from sovereign_agent.stewardship.registry import register_sentinel

from .scanner import ScanResult, scan_repo


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _repo_root() -> Path:
    """The live repo root — the dir holding src/sovereign_agent and the aria-* modules."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "src" / "sovereign_agent").is_dir():
            return parent
    return here.parents[4]


@register_sentinel
class PathSentinel(Sentinel):
    """Watches every staged module for false/test paths, ghosts, and zombies."""

    @property
    def id(self) -> str:
        return "path"

    @property
    def title(self) -> str:
        return "Path — the false-path / anti-ghost / anti-zombie watcher"

    @property
    def tier(self) -> int:
        return 1

    @property
    def voice_persona(self) -> str:
        return ("precise and literal — names the file and line, never guesses intent, "
                "never blocks on a comment, only on code that would actually run.")

    def articles(self) -> list[str]:
        return [
            "I. No module reaches Aria or the operator with a test path, a temp "
            "path, a machine-specific absolute path, or an unfilled placeholder "
            "path left in shipped code. A false path in running code is a block.",
            "II. I distinguish a defect in code that runs (a block) from the same "
            "string inside a comment or a test fixture (info). I never cry wolf.",
            "III. I am anti-ghost: a payload that does not mirror "
            "src/sovereign_agent/, or a tool-shipping module with no registration "
            "anchor, is structure that will silently fail to take effect.",
            "IV. I am anti-zombie: stale .bak snapshots and __pycache__ inside a "
            "payload would be copied verbatim into the live tree. I surface them.",
            "V. I propose only. I never edit and never delete. I name the file and "
            "the line; the operator and the apply gate decide.",
        ]

    # ── scan ────────────────────────────────────────────────────────────

    def _scan(self) -> ScanResult:
        return scan_repo(_repo_root())

    def scan(self) -> SentinelReport:
        result = self._scan()
        catalog = result.as_dict()
        self.save_catalog(catalog, name="paths")
        return SentinelReport(
            sentinel_id=self.id,
            observed_at=_iso_now(),
            catalog_name="paths",
            findings_count=len(result.findings),
            summary=result.summary(),
            catalog_path=str(self.catalog_path("paths")),
            details={
                "blocks": len(result.blocks),
                "warns": len(result.warns),
                "modules_scanned": result.modules_scanned,
                "files_scanned": result.files_scanned,
            },
        )

    def health_status(self) -> HealthStatus:
        result = self._scan()
        if result.blocks:
            sample = result.blocks[0]
            return HealthStatus(
                sentinel_id=self.id, level="error",
                summary=f"{len(result.blocks)} blocking false-path finding(s) across staged modules",
                detail=f"e.g. {sample.module}:{sample.path}:{sample.line} — {sample.message}",
                observed_at=_iso_now(),
            )
        if result.warns:
            return HealthStatus(
                sentinel_id=self.id, level="warning",
                summary=f"{len(result.warns)} path warning(s) to review",
                observed_at=_iso_now(),
            )
        return HealthStatus(
            sentinel_id=self.id, level="ok",
            summary=f"no false/ghost/zombie paths — {result.modules_scanned} modules clean",
            observed_at=_iso_now(),
        )

    def proposals(self, report: SentinelReport) -> list[dict]:
        result = self._scan()
        return [
            {
                "module": f.module,
                "path": f.path,
                "line": f.line,
                "severity": f.severity,
                "action": f"fix: {f.message}",
            }
            for f in result.blocks + result.warns
        ]


__all__ = ["PathSentinel"]
