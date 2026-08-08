"""
╔══════════════════════════════════════════════════════════════════════════╗
║  stewardship/cache_sentinel.py — the cache integrity sentinel           ║
║                                                                           ║
║  Born from the bug Kevin caught on v0.2.33.0 → v0.2.34.0: `uv sync`     ║
║  saw the same version installed and skipped rebuilding the package,    ║
║  leaving a new source file (`cadence.py`) in the tree but not in the   ║
║  venv. The cockpit reported "no such command" while the file existed.  ║
║                                                                           ║
║  This sentinel's binding statements                                      ║
║                                                                           ║
║    I. I will detect when the source tree contains a module the         ║
║       installed package does not — under any cache-skip pathology.     ║
║                                                                           ║
║   II. I will detect when version strings disagree across pyproject.toml,║
║       src/sovereign_agent/__init__.py, and the installed metadata.     ║
║                                                                           ║
║  III. I will detect when uv.lock is older than pyproject.toml — a     ║
║       sign the lockfile is stale.                                       ║
║                                                                           ║
║   IV. I will detect when __pycache__ entries are newer than their      ║
║       source — a hint that source has been modified but Python may     ║
║       still be importing the old bytecode.                              ║
║                                                                           ║
║    V. I will never modify the venv automatically. I propose; the       ║
║       operator decides. Tier 1.                                        ║
║                                                                           ║
║   VI. I notify with severity matching the risk: 'info' if cosmetic,    ║
║       'warning' if dev experience is degraded, 'alert' if the          ║
║       installed package is silently lying about its capabilities.      ║
║                                                                           ║
║  How to act on a finding                                                ║
║                                                                           ║
║    Run the cockpit / CLI command the sentinel suggests in the         ║
║    finding's `remediation` field. Typically:                            ║
║                                                                           ║
║      uv sync --reinstall-package sovereign-agent                       ║
║      # or                                                                ║
║      rm -rf ~/.local/share/sovereign-agent/venv && ./install.sh        ║
╚══════════════════════════════════════════════════════════════════════════╝

Kill switch: SOV_NO_CACHE_SENTINEL=1 (honored via Sentinel.is_enabled(); master: SOV_NO_SENTINELS=1).
"""
from __future__ import annotations

import importlib
import importlib.util
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from .base import HealthStatus, Sentinel, SentinelReport
from .registry import register_sentinel


@dataclass
class CacheFinding:
    """One specific cache issue with a suggested remediation."""
    kind: str               # 'version-drift', 'source-vs-venv', 'stale-lockfile', 'pyc-stale'
    severity: str           # 'info' / 'warning' / 'alert'
    summary: str
    detail: str = ""
    remediation: str = ""


@register_sentinel
class CacheSentinel(Sentinel):
    """Watches build/import caches for the silent-staleness bug class."""

    @property
    def id(self) -> str:
        return "cache"

    @property
    def title(self) -> str:
        return "Cache integrity sentinel"

    @property
    def tier(self) -> int:
        return 1

    def articles(self) -> list[str]:
        return [
            "I detect modules in source that are not in the installed package.",
            "I detect version disagreement across pyproject, __init__, and installed metadata.",
            "I detect uv.lock older than pyproject.toml.",
            "I detect __pycache__ entries newer than the source files they shadow.",
            "I never modify the venv automatically — I propose; the operator decides.",
            "I notify with severity matching the actual operator-experience risk.",
        ]

    # ── Scanning ─────────────────────────────────────────────────────────

    def scan(self) -> SentinelReport:
        findings: list[CacheFinding] = []
        findings.extend(self._check_source_vs_installed())
        findings.extend(self._check_version_drift())
        findings.extend(self._check_lockfile_age())
        findings.extend(self._check_stale_pyc())

        # Catalog dump
        catalog = {
            "scanned_at": self._iso_now(),
            "findings": [
                {"kind": f.kind, "severity": f.severity, "summary": f.summary,
                 "detail": f.detail, "remediation": f.remediation}
                for f in findings
            ],
            "counts": {
                "alert":   sum(1 for f in findings if f.severity == "alert"),
                "warning": sum(1 for f in findings if f.severity == "warning"),
                "info":    sum(1 for f in findings if f.severity == "info"),
            },
        }
        catalog_path = self.save_catalog(catalog, name="default")

        # Emit notifications for alert-level findings (auto-surface to operator)
        for f in findings:
            if f.severity == "alert":
                self.notify(
                    severity="alert",
                    title=f.summary,
                    message=f.detail + ("\n\nSuggested fix:\n  " + f.remediation if f.remediation else ""),
                    addressed_to="both",
                    data={"kind": f.kind},
                )

        return SentinelReport(
            sentinel_id=self.id,
            observed_at=self._iso_now(),
            catalog_name="default",
            findings_count=len(findings),
            summary=(
                f"{catalog['counts']['alert']} alert, "
                f"{catalog['counts']['warning']} warning, "
                f"{catalog['counts']['info']} info"
            ),
            catalog_path=str(catalog_path),
            details={"counts": catalog["counts"]},
        )

    def health_status(self) -> HealthStatus:
        catalog = self.load_catalog("default")
        if catalog is None:
            return HealthStatus(
                sentinel_id=self.id, level="unknown",
                summary="never scanned (run `sov sentinels scan cache`)",
            )
        counts = catalog.get("counts", {})
        if counts.get("alert", 0) > 0:
            return HealthStatus(
                sentinel_id=self.id, level="error",
                summary=f"{counts['alert']} cache alert(s) — module(s) or version(s) drifted",
                detail="Run `sov sentinels show cache` for details.",
            )
        if counts.get("warning", 0) > 0:
            return HealthStatus(
                sentinel_id=self.id, level="warning",
                summary=f"{counts['warning']} cache warning(s)",
                detail="Run `sov sentinels show cache` for details.",
            )
        return HealthStatus(
            sentinel_id=self.id, level="ok",
            summary="cache integrity clean",
            detail=f"last scan {catalog.get('scanned_at', '?')}",
        )

    def proposals(self, report: SentinelReport) -> list[dict]:
        catalog = self.load_catalog("default")
        if catalog is None:
            return []
        return [
            {"kind": f["kind"], "summary": f["summary"], "remediation": f["remediation"]}
            for f in catalog.get("findings", [])
            if f.get("remediation")
        ]

    # ── Individual check methods ─────────────────────────────────────────

    def _check_source_vs_installed(self) -> list[CacheFinding]:
        """The bug Kevin caught: source has cadence.py, venv doesn't.

        Walks src/sovereign_agent/*.py and verifies every module is
        importable through the installed package. Any source file that
        importlib can't find via the package is a 'source-vs-venv' alert.
        """
        findings: list[CacheFinding] = []
        try:
            import sovereign_agent
            installed_path = Path(sovereign_agent.__file__).parent
        except ImportError:
            return findings

        src_path = self._find_source_path()
        if src_path is None:
            return findings

        src_modules = set()
        for py in src_path.rglob("*.py"):
            if py.name == "__init__.py":
                continue
            if "__pycache__" in py.parts:
                continue
            rel = py.relative_to(src_path)
            module_name = "sovereign_agent." + ".".join(rel.with_suffix("").parts)
            src_modules.add(module_name)

        missing: list[str] = []
        for mod_name in sorted(src_modules):
            try:
                spec = importlib.util.find_spec(mod_name)
                if spec is None:
                    missing.append(mod_name)
            except (ImportError, ValueError):
                missing.append(mod_name)

        if missing:
            findings.append(CacheFinding(
                kind="source-vs-venv",
                severity="alert",
                summary=f"{len(missing)} source module(s) not importable from installed package",
                detail=(
                    "These modules exist in source but cannot be imported through the\n"
                    "installed `sovereign_agent` package. Strong signal that the venv\n"
                    "is stale (e.g., `uv sync` skipped a rebuild).\n\n"
                    "Missing: " + ", ".join(missing[:8]) +
                    (f" (+{len(missing) - 8} more)" if len(missing) > 8 else "")
                ),
                remediation=(
                    "uv sync --reinstall-package sovereign-agent\n"
                    "  # or if that doesn't work:\n"
                    "  rm -rf ~/.local/share/sovereign-agent/venv\n"
                    "  cd ~/AA-Erebo/sovereign-agent && ./install.sh"
                ),
            ))
        return findings

    def _check_version_drift(self) -> list[CacheFinding]:
        """Version in pyproject.toml, __init__.py, and pkg metadata must agree."""
        findings: list[CacheFinding] = []
        py_ver = self._version_from_pyproject()
        init_ver = self._version_from_init()
        meta_ver = self._version_from_metadata()
        versions = {"pyproject.toml": py_ver, "__init__.py": init_ver, "installed metadata": meta_ver}
        unique_versions = {v for v in versions.values() if v}
        if len(unique_versions) > 1:
            detail_lines = [f"  {k}: {v or '<missing>'}" for k, v in versions.items()]
            findings.append(CacheFinding(
                kind="version-drift",
                severity="alert",
                summary="version disagreement across source and installed package",
                detail="Three places must agree on version:\n" + "\n".join(detail_lines),
                remediation=(
                    "Bump or align versions in pyproject.toml and src/sovereign_agent/__init__.py,\n"
                    "  then: uv sync --reinstall-package sovereign-agent"
                ),
            ))
        return findings

    def _check_lockfile_age(self) -> list[CacheFinding]:
        """uv.lock older than pyproject.toml → lockfile may be stale."""
        findings: list[CacheFinding] = []
        src_path = self._find_source_path()
        if src_path is None:
            return findings
        root = src_path.parent.parent
        py_toml = root / "pyproject.toml"
        lock = root / "uv.lock"
        if not (py_toml.is_file() and lock.is_file()):
            return findings
        if py_toml.stat().st_mtime > lock.stat().st_mtime + 1:  # 1s slack
            findings.append(CacheFinding(
                kind="stale-lockfile",
                severity="warning",
                summary="uv.lock is older than pyproject.toml",
                detail="A dependency or version was changed without regenerating the lockfile.",
                remediation="uv lock   # regenerates uv.lock from pyproject.toml",
            ))
        return findings

    def _check_stale_pyc(self) -> list[CacheFinding]:
        """__pycache__ entries newer than source → low risk; flag as info."""
        findings: list[CacheFinding] = []
        src_path = self._find_source_path()
        if src_path is None:
            return findings
        stale_count = 0
        for py in src_path.rglob("*.py"):
            if "__pycache__" in py.parts:
                continue
            cache_dir = py.parent / "__pycache__"
            if not cache_dir.is_dir():
                continue
            for pyc in cache_dir.glob(f"{py.stem}.*.pyc"):
                try:
                    if pyc.stat().st_mtime < py.stat().st_mtime - 1:
                        stale_count += 1
                except OSError:
                    continue
        if stale_count > 0:
            findings.append(CacheFinding(
                kind="pyc-stale",
                severity="info",
                summary=f"{stale_count} stale .pyc entries (older than their .py)",
                detail=(
                    "Python should auto-invalidate these on import; this is mostly\n"
                    "cosmetic. If you see import errors, clear the cache:"
                ),
                remediation=(
                    "find ~/AA-Erebo/sovereign-agent -name '__pycache__' "
                    "-type d -exec rm -rf {} +"
                ),
            ))
        return findings

    # ── Helpers ──────────────────────────────────────────────────────────

    def _find_source_path(self) -> Path | None:
        """Locate the src/sovereign_agent/ directory."""
        # Walk up from this file
        here = Path(__file__).resolve()
        for parent in here.parents:
            candidate = parent / "src" / "sovereign_agent"
            if candidate.is_dir() and (candidate / "__init__.py").is_file():
                return candidate
        return None

    def _version_from_pyproject(self) -> str:
        src_path = self._find_source_path()
        if src_path is None:
            return ""
        py_toml = src_path.parent.parent / "pyproject.toml"
        if not py_toml.is_file():
            return ""
        try:
            text = py_toml.read_text(encoding="utf-8")
        except OSError:
            return ""
        m = re.search(r'^\s*version\s*=\s*"([^"]+)"', text, re.MULTILINE)
        return m.group(1) if m else ""

    def _version_from_init(self) -> str:
        try:
            from sovereign_agent import __version__
            return __version__
        except ImportError:
            return ""

    def _version_from_metadata(self) -> str:
        try:
            from importlib.metadata import version
            return version("sovereign-agent")
        except Exception:
            return ""

    @staticmethod
    def _iso_now() -> str:
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


__all__ = ["CacheSentinel", "CacheFinding"]
