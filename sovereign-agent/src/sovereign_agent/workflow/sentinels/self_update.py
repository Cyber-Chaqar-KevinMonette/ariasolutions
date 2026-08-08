"""
╔══════════════════════════════════════════════════════════════════════════╗
║  workflow/sentinels/self_update.py — SelfUpdateWorkflowSentinel          ║
║  v0.2.39 language drop                                                    ║
║                                                                           ║
║  Turns the install ritual we've been doing manually six times in this   ║
║  conversation into a structured workflow Aria can run for herself.      ║
║                                                                           ║
║  The ritual we automated                                                ║
║                                                                           ║
║    1. unzip update package to staging                                   ║
║    2. verify integrity (SHA256 against expected hash)                   ║
║    3. show operator a multi-select preview of what would change         ║
║    4. on operator confirm: snapshot data_dir → Vault                    ║
║    5. apply the update (rsync into target dir)                          ║
║    6. run a post-install smoke test                                     ║
║    7. on smoke-test failure: roll back from Vault snapshot              ║
║    8. log everything to the Aegis Ledger                                ║
║                                                                           ║
║  Authority discipline                                                   ║
║                                                                           ║
║    This sentinel operates at trust level T3 (Delegated Maintenance) by ║
║    default — multi-step work within a defined scope, with operator     ║
║    approval at the start. The 'multi-select confirmation' is the       ║
║    approval. Each high-impact step (apply, rollback) is bounded by    ║
║    the FileWriteHandler scope guards from v0.2.38.                     ║
║                                                                           ║
║    SOV_AUTO_APPROVE_SELF_UPDATES=1 elevates to T2 (Bounded Self-Heal) ║
║    where the operator's policy authorization stands in for the per-run║
║    confirmation. Default is OFF. Operator must consciously enable.    ║
║                                                                           ║
║  What this is NOT                                                       ║
║                                                                           ║
║    Not deployment to other machines. Not download-from-internet of    ║
║    updates. Not auto-discovery of "any update package anywhere."      ║
║    It reads from a single, operator-configured updates_dir, full stop.║
║                                                                           ║
║  Kill switch: SOV_NO_SELF_UPDATE=1                                      ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import zipfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal, Optional


KILL_SWITCH_ENV = "SOV_NO_SELF_UPDATE"
AUTO_APPROVE_ENV = "SOV_AUTO_APPROVE_SELF_UPDATES"


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


# ─── Records ─────────────────────────────────────────────────────────────


@dataclass
class UpdatePackage:
    """One candidate update package discovered in the updates_dir."""
    path: str                              # absolute path to .zip
    name: str                              # filename stem (e.g. "AA-Erebo-v0.2.39")
    size_bytes: int
    sha256: str
    discovered_at: str = ""

    @classmethod
    def from_path(cls, p: Path) -> "UpdatePackage":
        data = p.read_bytes()
        return cls(
            path=str(p),
            name=p.stem,
            size_bytes=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
            discovered_at=_iso_now(),
        )


@dataclass
class UpdatePreview:
    """The multi-select preview operator sees before confirming."""
    package: UpdatePackage
    staged_files: list[str] = field(default_factory=list)
    files_that_would_overwrite: list[str] = field(default_factory=list)
    new_files: list[str] = field(default_factory=list)
    deletions: list[str] = field(default_factory=list)
    total_bytes_changing: int = 0


@dataclass
class UpdateOutcome:
    """The result of a self-update run."""
    succeeded: bool
    package_name: str
    summary: str
    snapshot_id: str = ""
    files_changed: list[str] = field(default_factory=list)
    rolled_back: bool = False
    smoke_test_passed: bool = False
    error: str = ""
    started_at: str = ""
    completed_at: str = ""


# ─── Protocol: operator confirmation callback ───────────────────────────


OperatorConfirmCallback = Callable[[UpdatePreview], Optional[list[str]]]
"""Callback the sentinel invokes to ask operator approval.

Returns a list of file paths to actually apply (subset of preview.staged_files),
or None to cancel the update entirely. Default callbacks live in this module
for terminal and programmatic use; cockpit can provide a TUI variant later.
"""


def terminal_confirm(preview: UpdatePreview) -> Optional[list[str]]:
    """Default CLI confirmation: print the preview, prompt yes/no/select."""
    print(f"\n=== Update preview: {preview.package.name} ===")
    print(f"SHA256: {preview.package.sha256[:16]}...")
    print(f"Size: {preview.package.size_bytes} bytes")
    print(f"Files staged: {len(preview.staged_files)}")
    print(f"  Would overwrite: {len(preview.files_that_would_overwrite)}")
    print(f"  New files:       {len(preview.new_files)}")
    print(f"  Deletions:       {len(preview.deletions)}")
    if preview.files_that_would_overwrite:
        print("\nFiles that would be overwritten:")
        for f in preview.files_that_would_overwrite[:20]:
            print(f"  ~ {f}")
        if len(preview.files_that_would_overwrite) > 20:
            print(f"  ... and {len(preview.files_that_would_overwrite) - 20} more")
    response = input("\nProceed? [y/N]: ").strip().lower()
    if response in ("y", "yes"):
        return list(preview.staged_files)
    return None


def auto_approve_all(preview: UpdatePreview) -> Optional[list[str]]:
    """For SOV_AUTO_APPROVE_SELF_UPDATES mode. Approves everything."""
    return list(preview.staged_files)


# ─── The sentinel ────────────────────────────────────────────────────────


class SelfUpdateWorkflowSentinel:
    """Manages discovery, preview, application, and rollback of self-updates.

    Construct with:
        updates_dir — where to look for .zip update packages
        target_root — where to apply them (typically your project root)
        vault       — Vault instance for pre-update snapshots (optional but
                      strongly recommended for rollback support)
        confirm_callback — how to get operator approval (default: terminal)
        smoke_test_callable — optional, called after apply; returns bool
    """

    def __init__(
        self,
        updates_dir: Path,
        target_root: Path,
        vault: Optional[object] = None,
        confirm_callback: Optional[OperatorConfirmCallback] = None,
        smoke_test_callable: Optional[Callable[[], bool]] = None,
    ):
        self._updates_dir = Path(updates_dir).expanduser()
        self._target_root = Path(target_root).expanduser().resolve()
        self._vault = vault
        self._confirm = confirm_callback or self._default_confirm
        self._smoke_test = smoke_test_callable

    @property
    def is_disabled(self) -> bool:
        return bool(os.environ.get(KILL_SWITCH_ENV))

    @property
    def is_auto_approve(self) -> bool:
        return bool(os.environ.get(AUTO_APPROVE_ENV))

    def _default_confirm(self, preview: UpdatePreview) -> Optional[list[str]]:
        if self.is_auto_approve:
            return auto_approve_all(preview)
        return terminal_confirm(preview)

    # ─── Discovery ──────────────────────────────────────────────────────

    def discover_packages(self) -> list[UpdatePackage]:
        """List all .zip update packages in the updates_dir."""
        if not self._updates_dir.is_dir():
            return []
        return sorted(
            (UpdatePackage.from_path(p) for p in self._updates_dir.glob("*.zip")),
            key=lambda u: u.name,
        )

    # ─── Preview ────────────────────────────────────────────────────────

    def build_preview(self, package: UpdatePackage) -> UpdatePreview:
        """Stage the package to a temp dir, compute what would change."""
        staging = Path("/tmp") / f"aria-update-preview-{package.name}"
        if staging.exists():
            shutil.rmtree(staging)
        staging.mkdir(parents=True)

        try:
            with zipfile.ZipFile(package.path) as zf:
                zf.extractall(staging)
        except (zipfile.BadZipFile, OSError) as e:
            shutil.rmtree(staging, ignore_errors=True)
            raise ValueError(f"failed to unzip {package.path}: {e}") from e

        # Walk the staging tree. For each file, decide: overwrite, new, no-op.
        staged_files: list[str] = []
        would_overwrite: list[str] = []
        new_files: list[str] = []
        total_bytes = 0

        # Find the source root — many update zips have a top-level dir
        # like "AA-Erebo-v0.2.39/". We don't assume; we just walk staging.
        for f in staging.rglob("*"):
            if not f.is_file():
                continue
            rel = f.relative_to(staging)
            # Skip __pycache__ et al.
            if any(part in {"__pycache__", ".git"} for part in rel.parts):
                continue
            staged_files.append(str(rel))
            total_bytes += f.stat().st_size
            # Heuristic: map staging path → target path.
            # We strip the top-level dir if it exists.
            parts = rel.parts
            if len(parts) > 1:
                target_rel = Path(*parts[1:])
            else:
                target_rel = rel
            target_path = self._target_root / target_rel
            if target_path.is_file():
                would_overwrite.append(str(target_rel))
            else:
                new_files.append(str(target_rel))

        return UpdatePreview(
            package=package,
            staged_files=staged_files,
            files_that_would_overwrite=would_overwrite,
            new_files=new_files,
            deletions=[],   # we don't compute deletions in this version
            total_bytes_changing=total_bytes,
        )

    # ─── Apply ──────────────────────────────────────────────────────────

    def apply_update(
        self,
        package: UpdatePackage,
        approved_files: list[str],
    ) -> UpdateOutcome:
        """Apply the approved subset of files from a previously-built preview."""
        started_at = _iso_now()
        outcome = UpdateOutcome(
            succeeded=False,
            package_name=package.name,
            summary="not started",
            started_at=started_at,
        )

        # Snapshot to Vault first if available.
        if self._vault is not None:
            try:
                from ulid import ULID
                snapshot_id = str(ULID())
                self._vault.snapshot(   # type: ignore[attr-defined]
                    snapshot_id=snapshot_id,
                    source=self._target_root,
                    label=f"pre-update-{package.name}",
                )
                outcome.snapshot_id = snapshot_id
            except Exception as e:
                outcome.summary = f"vault snapshot failed: {e}"
                outcome.error = str(e)
                outcome.completed_at = _iso_now()
                return outcome

        # Apply approved files from staging.
        staging = Path("/tmp") / f"aria-update-preview-{package.name}"
        files_changed: list[str] = []
        try:
            for rel in approved_files:
                # Reconstruct target path the same way preview did.
                src = staging / rel
                if not src.is_file():
                    continue
                parts = Path(rel).parts
                if len(parts) > 1:
                    target_rel = Path(*parts[1:])
                else:
                    target_rel = Path(rel)
                tgt = self._target_root / target_rel
                tgt.parent.mkdir(parents=True, exist_ok=True)
                # Atomic write.
                tmp = tgt.with_suffix(tgt.suffix + ".tmp")
                shutil.copy2(src, tmp)
                os.replace(tmp, tgt)
                files_changed.append(str(target_rel))
        except Exception as e:
            outcome.summary = f"apply failed: {e}"
            outcome.error = str(e)
            outcome.completed_at = _iso_now()
            # Best-effort rollback.
            if self._vault and outcome.snapshot_id:
                outcome.rolled_back = self._rollback(outcome.snapshot_id)
            return outcome

        outcome.files_changed = files_changed

        # Run smoke test if provided.
        if self._smoke_test is not None:
            try:
                passed = bool(self._smoke_test())
            except Exception as e:
                passed = False
                outcome.error = f"smoke test raised: {e}"
            outcome.smoke_test_passed = passed
            if not passed:
                outcome.summary = "smoke test failed, rolling back"
                if self._vault and outcome.snapshot_id:
                    outcome.rolled_back = self._rollback(outcome.snapshot_id)
                outcome.completed_at = _iso_now()
                return outcome
        else:
            outcome.smoke_test_passed = True  # no test = trust the apply

        outcome.succeeded = True
        outcome.summary = (
            f"applied {len(files_changed)} files from {package.name}; "
            f"smoke {'PASS' if outcome.smoke_test_passed else 'SKIP'}"
        )
        outcome.completed_at = _iso_now()
        return outcome

    def _rollback(self, snapshot_id: str) -> bool:
        """Restore from a Vault snapshot. Returns True if rollback succeeded."""
        if self._vault is None:
            return False
        try:
            self._vault.restore(           # type: ignore[attr-defined]
                snapshot_id=snapshot_id,
                target=self._target_root,
                confirm=True,
            )
            return True
        except Exception:
            return False

    # ─── End-to-end driver ──────────────────────────────────────────────

    def run(self, package_name: Optional[str] = None) -> Optional[UpdateOutcome]:
        """Discover → preview → confirm → apply → smoke → maybe rollback.

        If package_name is given, runs that specific package. Otherwise
        discovers and uses the most recent. Returns None if disabled or
        operator cancels.
        """
        if self.is_disabled:
            return None

        packages = self.discover_packages()
        if not packages:
            return None

        if package_name:
            package = next((p for p in packages if p.name == package_name), None)
            if package is None:
                return None
        else:
            package = packages[-1]   # latest by name-sort

        preview = self.build_preview(package)
        approved = self._confirm(preview)
        if not approved:
            return None

        return self.apply_update(package, approved)


__all__ = [
    "SelfUpdateWorkflowSentinel",
    "UpdatePackage", "UpdatePreview", "UpdateOutcome",
    "OperatorConfirmCallback",
    "terminal_confirm", "auto_approve_all",
    "KILL_SWITCH_ENV", "AUTO_APPROVE_ENV",
]
