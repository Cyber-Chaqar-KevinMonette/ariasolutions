"""
╔══════════════════════════════════════════════════════════════════════════╗
║  workflow/handlers/file_write.py — file I/O tool handlers                 ║
║  v0.2.38 muscle drop                                                       ║
║                                                                           ║
║  Two handlers for the agentic loop: 'file_write' and 'file_read'.        ║
║                                                                           ║
║  Scope discipline                                                         ║
║                                                                           ║
║    Both handlers refuse to operate outside an explicitly-declared       ║
║    "allowed roots" list. The allowed roots are project-bound; AriaLoop  ║
║    constructs FileHandler(allowed_roots=[project.repo_path, data_dir]). ║
║    Writes outside those roots return scope-rejection without touching   ║
║    the filesystem.                                                       ║
║                                                                           ║
║    Why: file_write is the most dangerous handler in the muscle drop —  ║
║    arbitrary file write outside the project boundary is exactly the    ║
║    R3+ surface the LOVE doctrine §4 forbids. Bounding it here makes    ║
║    the boundary structural, not aspirational.                          ║
║                                                                           ║
║  Action input shapes                                                    ║
║                                                                           ║
║    file_write:                                                          ║
║      {                                                                   ║
║        "path": "src/some_file.py",                                      ║
║        "content": "...",                                                ║
║        "mode": "0644",                  # optional                      ║
║        "create_parents": true,          # optional, default true       ║
║        "atomic": true                   # optional, default true       ║
║      }                                                                   ║
║                                                                           ║
║    file_read:                                                           ║
║      {                                                                   ║
║        "path": "src/some_file.py",                                      ║
║        "max_bytes": 65536              # optional, default 64KB        ║
║      }                                                                   ║
║                                                                           ║
║  Kill switches: SOV_NO_FILE_WRITE_HANDLER=1, SOV_NO_FILE_READ_HANDLER=1 ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sovereign_agent.persistence.projects import Task
from sovereign_agent.workflow.agentic_loop import StepOutcome


KILL_SWITCH_WRITE = "SOV_NO_FILE_WRITE_HANDLER"
KILL_SWITCH_READ = "SOV_NO_FILE_READ_HANDLER"

DEFAULT_READ_CAP = 64 * 1024     # 64 KB


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _is_within(path: Path, root: Path) -> bool:
    """True if path is the same as or under root, after resolving symlinks.
    Defense against ../../etc/passwd-style escapes."""
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (ValueError, OSError):
        return False


# ─── FileWriteHandler ────────────────────────────────────────────────────


class FileWriteHandler:
    """Writes files within the allowed roots. Refuses anything outside."""

    def __init__(self, allowed_roots: list[Path]):
        if not allowed_roots:
            raise ValueError("FileWriteHandler requires at least one allowed_root")
        self._allowed_roots = [Path(r).resolve() for r in allowed_roots]

    @property
    def is_disabled(self) -> bool:
        return bool(os.environ.get(KILL_SWITCH_WRITE))

    @property
    def allowed_roots(self) -> list[Path]:
        return list(self._allowed_roots)

    def __call__(self, task: Task) -> StepOutcome:
        started_at = _iso_now()

        if self.is_disabled:
            return StepOutcome(
                succeeded=False,
                summary="file_write handler disabled via SOV_NO_FILE_WRITE_HANDLER",
                error="handler-disabled",
                started_at=started_at,
                completed_at=_iso_now(),
            )

        try:
            blob = json.loads(task.description)
            action_input = blob.get("action_input", {})
        except (json.JSONDecodeError, AttributeError):
            return StepOutcome(
                succeeded=False,
                summary="malformed task description",
                error="malformed-description",
                started_at=started_at,
                completed_at=_iso_now(),
            )

        path_str = action_input.get("path")
        content = action_input.get("content")
        if not path_str or not isinstance(path_str, str):
            return StepOutcome(
                succeeded=False, summary="action_input.path required",
                error="invalid-path",
                started_at=started_at, completed_at=_iso_now(),
            )
        if content is None or not isinstance(content, str):
            return StepOutcome(
                succeeded=False, summary="action_input.content (string) required",
                error="invalid-content",
                started_at=started_at, completed_at=_iso_now(),
            )

        target = Path(path_str).expanduser()
        # Resolve relative paths against the first allowed_root.
        if not target.is_absolute():
            target = self._allowed_roots[0] / target

        # Scope check.
        if not any(_is_within(target, root) for root in self._allowed_roots):
            return StepOutcome(
                succeeded=False,
                summary=f"path {target} not within any allowed root",
                error="scope-rejection",
                extra={
                    "attempted_path": str(target),
                    "allowed_roots": [str(r) for r in self._allowed_roots],
                },
                started_at=started_at, completed_at=_iso_now(),
            )

        create_parents = action_input.get("create_parents", True)
        atomic = action_input.get("atomic", True)
        mode_str = action_input.get("mode", "0644")
        try:
            mode = int(mode_str, 8) if isinstance(mode_str, str) else int(mode_str)
        except (ValueError, TypeError):
            mode = 0o644

        try:
            if create_parents:
                target.parent.mkdir(parents=True, exist_ok=True)
            if atomic:
                tmp = target.with_suffix(target.suffix + ".tmp")
                tmp.write_text(content, encoding="utf-8")
                os.chmod(tmp, mode)
                os.replace(tmp, target)
            else:
                target.write_text(content, encoding="utf-8")
                os.chmod(target, mode)
        except Exception as e:
            return StepOutcome(
                succeeded=False,
                summary=f"file write failed: {type(e).__name__}",
                error=str(e),
                extra={"target": str(target)},
                started_at=started_at, completed_at=_iso_now(),
            )

        return StepOutcome(
            succeeded=True,
            summary=f"wrote {len(content)} bytes to {target}",
            artifacts=[str(target)],
            extra={
                "target": str(target),
                "bytes": len(content),
                "atomic": atomic,
                "mode": oct(mode),
            },
            started_at=started_at, completed_at=_iso_now(),
        )


# ─── FileReadHandler ─────────────────────────────────────────────────────


class FileReadHandler:
    """Reads files within the allowed roots. Capped to max_bytes."""

    def __init__(self, allowed_roots: list[Path]):
        if not allowed_roots:
            raise ValueError("FileReadHandler requires at least one allowed_root")
        self._allowed_roots = [Path(r).resolve() for r in allowed_roots]

    @property
    def is_disabled(self) -> bool:
        return bool(os.environ.get(KILL_SWITCH_READ))

    def __call__(self, task: Task) -> StepOutcome:
        started_at = _iso_now()

        if self.is_disabled:
            return StepOutcome(
                succeeded=False,
                summary="file_read handler disabled via SOV_NO_FILE_READ_HANDLER",
                error="handler-disabled",
                started_at=started_at, completed_at=_iso_now(),
            )

        try:
            blob = json.loads(task.description)
            action_input = blob.get("action_input", {})
        except (json.JSONDecodeError, AttributeError):
            return StepOutcome(
                succeeded=False, summary="malformed task description",
                error="malformed-description",
                started_at=started_at, completed_at=_iso_now(),
            )

        path_str = action_input.get("path")
        if not path_str or not isinstance(path_str, str):
            return StepOutcome(
                succeeded=False, summary="action_input.path required",
                error="invalid-path",
                started_at=started_at, completed_at=_iso_now(),
            )

        target = Path(path_str).expanduser()
        if not target.is_absolute():
            target = self._allowed_roots[0] / target

        if not any(_is_within(target, root) for root in self._allowed_roots):
            return StepOutcome(
                succeeded=False,
                summary=f"path {target} not within any allowed root",
                error="scope-rejection",
                started_at=started_at, completed_at=_iso_now(),
            )

        if not target.is_file():
            return StepOutcome(
                succeeded=False,
                summary=f"file not found: {target}",
                error="not-found",
                started_at=started_at, completed_at=_iso_now(),
            )

        max_bytes = int(action_input.get("max_bytes", DEFAULT_READ_CAP))
        try:
            content = target.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            return StepOutcome(
                succeeded=False,
                summary=f"file read failed: {type(e).__name__}",
                error=str(e),
                started_at=started_at, completed_at=_iso_now(),
            )

        truncated = len(content) > max_bytes
        if truncated:
            content = content[:max_bytes]

        return StepOutcome(
            succeeded=True,
            summary=f"read {len(content)} bytes from {target}"
                    + (" (truncated)" if truncated else ""),
            extra={
                "target": str(target),
                "bytes_read": len(content),
                "truncated": truncated,
                "content": content,
            },
            started_at=started_at, completed_at=_iso_now(),
        )


__all__ = [
    "FileWriteHandler", "FileReadHandler",
    "KILL_SWITCH_WRITE", "KILL_SWITCH_READ",
    "DEFAULT_READ_CAP",
]
