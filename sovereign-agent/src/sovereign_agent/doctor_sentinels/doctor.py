"""
╔══════════════════════════════════════════════════════════════════════════╗
║  doctor/doctor.py — sov doctor                                            ║
║  v0.2.39.1 — HOTFIX                                                       ║
║                                                                           ║
║  v0.2.39.1 fixes a real bug Kevin found within an hour of using Aria   ║
║  for real work: the env-var-based VIRTUAL_ENV detection in v0.2.38     ║
║  was invisible when the doctor was launched through `uv run`, because  ║
║  UV strips/overrides VIRTUAL_ENV before the child process starts.      ║
║                                                                           ║
║  The fix: a filesystem-level detector (_scan_legacy_venv_dirs) that    ║
║  finds ghost venv directories on disk without depending on env vars.   ║
║  Works regardless of launcher (UV, python3, cron, anything). The      ║
║  env-var detector stays in place — it's still useful when launched    ║
║  directly — but no longer the only line of defense.                    ║
║                                                                           ║
║  Self-healing for Aria's own surface. R0 (her own data_dir, venv,        ║
║  build artifacts) autonomously cleanable. R2+ (operator's shell, system  ║
║  state) report-only — surfaced for Kevin to act on, never touched.      ║
║                                                                           ║
║  Three operations                                                        ║
║                                                                           ║
║    scan()   — read-only inventory of detected issues                    ║
║    heal()   — autonomous fix for R0-class issues only                  ║
║    report() — structured Markdown for offline review                    ║
║                                                                           ║
║  Detections implemented                                                ║
║                                                                           ║
║    R0:                                                                   ║
║      • stale .tmp files in data_dir (age > 1 day)                      ║
║      • __pycache__ dirs mismatched to current Python version            ║
║      • orphaned .pyc files (no matching .py)                           ║
║                                                                           ║
║    R2:                                                                   ║
║      • VIRTUAL_ENV env var pointing at a path that doesn't exist OR    ║
║        differs from the project's .venv (env-var-based — visible       ║
║        only when launched WITHOUT uv)                                   ║
║      • Ghost venv DIRECTORIES on disk in legacy locations (new in     ║
║        v0.2.39.1 — works regardless of launcher)                       ║
║                                                                           ║
║  Kill switch: SOV_NO_DOCTOR=1                                            ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import os
import shutil
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional


KILL_SWITCH_ENV = "SOV_NO_DOCTOR"

# Detection issue kinds.
IssueKind = Literal[
    "stale-tmp",
    "pycache-version-mismatch",
    "orphaned-pyc",
    "ghost-virtualenv-envvar",
    "missing-virtualenv-path",
    "legacy-venv-directory",        # NEW in v0.2.39.1
]

Scope = Literal["R0", "R1", "R2", "R3"]
Severity = Literal["info", "warning", "alert"]

# Legacy venv locations to check on disk. These are paths where Aria's older
# install procedures placed a venv before the project standardized on
# `.venv` in the repo root. Add to this list as more legacy locations are
# discovered. None of these paths get *touched* by the doctor; they get
# REPORTED with the suggested fix.
LEGACY_VENV_LOCATIONS = [
    "~/.local/share/sovereign-agent/venv",
    "~/.local/share/aria/venv",
    "~/.cache/sovereign-agent/venv",
]


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _looks_like_venv(p: Path) -> bool:
    """Quick heuristic: does this directory look like a Python venv?
    Has bin/activate (POSIX) or Scripts/activate.bat (Windows).
    """
    if not p.is_dir():
        return False
    return (p / "bin" / "activate").is_file() or (p / "Scripts" / "activate.bat").is_file()


# ─── Issue record ────────────────────────────────────────────────────────


@dataclass
class DoctorIssue:
    kind: IssueKind
    scope: Scope
    severity: Severity
    summary: str
    path: str = ""
    suggested_fix: str = ""
    auto_healable: bool = False     # True only for R0
    detected_at: str = field(default_factory=_iso_now)


@dataclass
class HealAction:
    kind: str                       # 'deleted', 'cleaned', 'skipped'
    issue_kind: IssueKind
    path: str
    succeeded: bool
    error: str = ""


# ─── Doctor ──────────────────────────────────────────────────────────────


class SovDoctor:
    """Inspects Aria's surface; heals R0; reports the rest."""

    def __init__(
        self,
        data_dir: Path,
        project_venv: Optional[Path] = None,
        repo_root: Optional[Path] = None,
        stale_tmp_age_days: int = 1,
        legacy_venv_locations: Optional[list[str]] = None,
    ):
        self._data_dir = Path(data_dir).expanduser()
        self._project_venv = Path(project_venv).expanduser() if project_venv else None
        self._repo_root = Path(repo_root).expanduser() if repo_root else None
        self._stale_tmp_age_seconds = stale_tmp_age_days * 86400
        self._legacy_venv_locations = legacy_venv_locations or LEGACY_VENV_LOCATIONS

    @property
    def is_disabled(self) -> bool:
        return bool(os.environ.get(KILL_SWITCH_ENV))

    # ─── scan() ─────────────────────────────────────────────────────────

    def scan(self) -> list[DoctorIssue]:
        if self.is_disabled:
            return []
        issues: list[DoctorIssue] = []
        issues.extend(self._scan_stale_tmp())
        issues.extend(self._scan_pycache_mismatch())
        issues.extend(self._scan_orphaned_pyc())
        issues.extend(self._scan_virtualenv_envvar())
        issues.extend(self._scan_legacy_venv_dirs())   # NEW in v0.2.39.1
        return issues

    def _scan_stale_tmp(self) -> list[DoctorIssue]:
        out: list[DoctorIssue] = []
        if not self._data_dir.is_dir():
            return out
        now = time.time()
        for tmp in self._data_dir.rglob("*.tmp"):
            try:
                age = now - tmp.stat().st_mtime
            except OSError:
                continue
            if age > self._stale_tmp_age_seconds:
                out.append(DoctorIssue(
                    kind="stale-tmp",
                    scope="R0",
                    severity="info",
                    summary=f".tmp file stale for {age/86400:.1f} days",
                    path=str(tmp),
                    suggested_fix=f"delete {tmp}",
                    auto_healable=True,
                ))
        return out

    def _scan_pycache_mismatch(self) -> list[DoctorIssue]:
        out: list[DoctorIssue] = []
        if not self._repo_root or not self._repo_root.is_dir():
            return out
        current_tag = f"cpython-{sys.version_info.major}{sys.version_info.minor}"
        for pyc in self._repo_root.rglob("__pycache__/*.pyc"):
            name = pyc.name
            if ".cpython-" in name:
                tag = name.split(".cpython-", 1)[1].rsplit(".pyc", 1)[0]
                tag_full = f"cpython-{tag}"
                if tag_full != current_tag:
                    out.append(DoctorIssue(
                        kind="pycache-version-mismatch",
                        scope="R0",
                        severity="info",
                        summary=f".pyc from {tag_full}, current is {current_tag}",
                        path=str(pyc),
                        suggested_fix=f"delete stale .pyc",
                        auto_healable=True,
                    ))
        return out

    def _scan_orphaned_pyc(self) -> list[DoctorIssue]:
        out: list[DoctorIssue] = []
        if not self._repo_root or not self._repo_root.is_dir():
            return out
        for pyc in self._repo_root.rglob("__pycache__/*.pyc"):
            stem = pyc.name.split(".", 1)[0]
            source = pyc.parent.parent / f"{stem}.py"
            if not source.is_file():
                out.append(DoctorIssue(
                    kind="orphaned-pyc",
                    scope="R0",
                    severity="info",
                    summary=f"{pyc.name} has no source .py",
                    path=str(pyc),
                    suggested_fix=f"delete orphaned .pyc",
                    auto_healable=True,
                ))
        return out

    def _scan_virtualenv_envvar(self) -> list[DoctorIssue]:
        """Env-var-based VIRTUAL_ENV detection. NOTE: when the doctor is
        launched via `uv run`, UV strips/overrides VIRTUAL_ENV so this
        detector is blind. The filesystem detector below covers that gap.
        """
        out: list[DoctorIssue] = []
        venv_env = os.environ.get("VIRTUAL_ENV", "")
        if not venv_env:
            return out
        venv_path = Path(venv_env).expanduser()
        if not venv_path.is_dir():
            out.append(DoctorIssue(
                kind="missing-virtualenv-path",
                scope="R2",
                severity="warning",
                summary=(
                    f"VIRTUAL_ENV points at {venv_env}, "
                    f"which does not exist"
                ),
                path=venv_env,
                suggested_fix=(
                    "run `unset VIRTUAL_ENV` in your shell, "
                    "or update your shell config to remove the stale export"
                ),
                auto_healable=False,
            ))
            return out
        if self._project_venv:
            try:
                same = venv_path.resolve() == self._project_venv.resolve()
            except OSError:
                same = False
            if not same:
                out.append(DoctorIssue(
                    kind="ghost-virtualenv-envvar",
                    scope="R2",
                    severity="warning",
                    summary=(
                        f"VIRTUAL_ENV={venv_env} differs from project venv "
                        f"{self._project_venv}"
                    ),
                    path=venv_env,
                    suggested_fix=(
                        "run `unset VIRTUAL_ENV && source .venv/bin/activate`, "
                        "or open a fresh shell to clear the legacy export"
                    ),
                    auto_healable=False,
                ))
        return out

    def _scan_legacy_venv_dirs(self) -> list[DoctorIssue]:
        """NEW in v0.2.39.1 — filesystem-level ghost venv detection.

        Walks the configured list of legacy venv locations. If any of them
        exist on disk AND are not the same as the project's canonical
        .venv, reports them. Works regardless of how the doctor was
        launched (UV, python3, cron, anything) because it doesn't read
        env vars.
        """
        out: list[DoctorIssue] = []
        canonical = self._project_venv.resolve() if self._project_venv else None
        for legacy in self._legacy_venv_locations:
            p = Path(legacy).expanduser()
            try:
                p_resolved = p.resolve()
            except OSError:
                continue
            if not _looks_like_venv(p):
                continue
            if canonical and p_resolved == canonical:
                # Operator pointed legacy location at the canonical venv —
                # not a ghost, that's intentional.
                continue
            # Get a friendly size hint.
            try:
                size_mb = sum(
                    f.stat().st_size for f in p.rglob("*") if f.is_file()
                ) / (1024 * 1024)
                size_hint = f" (~{size_mb:.0f} MB)"
            except (OSError, ValueError):
                size_hint = ""
            out.append(DoctorIssue(
                kind="legacy-venv-directory",
                scope="R2",
                severity="warning",
                summary=(
                    f"legacy venv directory found at {legacy}{size_hint} — "
                    f"not the project's canonical venv"
                    + (f" ({canonical})" if canonical else "")
                ),
                path=str(p),
                suggested_fix=(
                    f"if no longer needed, remove with: rm -rf {p} "
                    f"(NEVER auto-removed — Aria stays out of your filesystem "
                    f"above her own data_dir)"
                ),
                auto_healable=False,
            ))
        return out

    # ─── heal() ─────────────────────────────────────────────────────────

    def heal(self) -> list[HealAction]:
        """Autonomously fix R0 issues only. Returns the actions taken."""
        if self.is_disabled:
            return []
        actions: list[HealAction] = []
        for issue in self.scan():
            if not issue.auto_healable or issue.scope != "R0":
                continue
            try:
                p = Path(issue.path)
                if p.is_file():
                    p.unlink()
                    actions.append(HealAction(
                        kind="deleted", issue_kind=issue.kind,
                        path=issue.path, succeeded=True,
                    ))
                elif p.is_dir():
                    shutil.rmtree(p)
                    actions.append(HealAction(
                        kind="cleaned", issue_kind=issue.kind,
                        path=issue.path, succeeded=True,
                    ))
                else:
                    actions.append(HealAction(
                        kind="skipped", issue_kind=issue.kind,
                        path=issue.path, succeeded=True,
                        error="path no longer exists",
                    ))
            except Exception as e:
                actions.append(HealAction(
                    kind="skipped", issue_kind=issue.kind,
                    path=issue.path, succeeded=False,
                    error=f"{type(e).__name__}: {e}",
                ))
        return actions

    # ─── report() ───────────────────────────────────────────────────────

    def report(self) -> str:
        """Render a Markdown report of all detected issues, grouped by scope."""
        issues = self.scan()
        if not issues:
            return (
                f"# sov doctor report — {_iso_now()}\n\n"
                "No issues detected.\n"
            )

        lines = [
            f"# sov doctor report — {_iso_now()}\n",
            f"**Total issues detected:** {len(issues)}\n",
        ]

        by_scope: dict[Scope, list[DoctorIssue]] = {}
        for issue in issues:
            by_scope.setdefault(issue.scope, []).append(issue)

        scope_labels = {
            "R0": "R0 — Aria's own surface (autonomously healable)",
            "R1": "R1 — operator-visible repo artifacts (build-time only)",
            "R2": "R2 — operator's shell/filesystem (REPORT ONLY)",
            "R3": "R3 — system-wide (REPORT ONLY)",
        }
        for scope in ("R0", "R1", "R2", "R3"):
            scope_issues = by_scope.get(scope, [])
            if not scope_issues:
                continue
            lines.append(f"\n## {scope_labels[scope]}\n")
            for issue in scope_issues:
                lines.append(f"- **{issue.kind}** — {issue.summary}")
                if issue.path:
                    lines.append(f"  - path: `{issue.path}`")
                if issue.suggested_fix:
                    lines.append(f"  - suggested fix: {issue.suggested_fix}")
        return "\n".join(lines) + "\n"


__all__ = [
    "SovDoctor", "DoctorIssue", "HealAction",
    "IssueKind", "Scope", "Severity",
    "KILL_SWITCH_ENV", "LEGACY_VENV_LOCATIONS",
]
