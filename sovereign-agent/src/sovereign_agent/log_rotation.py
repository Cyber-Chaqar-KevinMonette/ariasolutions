"""
log_rotation.py — size-based rotation for append-only logs.
v0.2.22.0

Rotation policy:
  When a log file exceeds `max_bytes`, rename it to `<name>.1`, then
  `.1` → `.2`, etc., keeping `max_backups` rotated copies. The current
  log is truncated to a fresh empty file.

This is not a sophisticated retention system. It's enough to prevent
unbounded growth on long-running operator machines. For analytics
across years, a future archival pipeline (compressed monthly bundles)
can be built on top — that's v0.2.24.0+ work.

Invariants:
  • Rotation is atomic per individual rename operation; if the process
    crashes mid-rotation, the worst case is a numbered file out of
    order — never data loss.
  • A failed rotation does NOT block the calling write. The calling
    writer logs the failure and proceeds with the original append.
  • Rotation triggers are checked BEFORE a write begins, so the size
    threshold may be exceeded slightly by one write. Operators have
    not been observed to write 1GB log lines, so this is fine.
"""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


# Defaults — tunable per-log if needed
DEFAULT_MAX_BYTES = 10 * 1024 * 1024     # 10 MB
DEFAULT_MAX_BACKUPS = 5                   # keep 5 rotated copies


def maybe_rotate(
    log_path: Path,
    *,
    max_bytes: int = DEFAULT_MAX_BYTES,
    max_backups: int = DEFAULT_MAX_BACKUPS,
) -> bool:
    """Rotate log_path if it exceeds max_bytes. Returns True if rotation
    occurred, False otherwise. Errors are logged and swallowed.

    Side effects:
      <log_path>     → <log_path>.1
      <log_path>.1   → <log_path>.2
      ...
      <log_path>.N-1 → <log_path>.N
      Oldest copy (above max_backups) is deleted.
      A fresh empty <log_path> is left for subsequent appends.
    """
    try:
        log_path = Path(log_path)
        if not log_path.exists():
            return False
        if log_path.stat().st_size < max_bytes:
            return False

        # Shift existing backups down
        for i in range(max_backups, 0, -1):
            src = log_path.with_suffix(log_path.suffix + f".{i}")
            dst = log_path.with_suffix(log_path.suffix + f".{i+1}")
            if i == max_backups and src.exists():
                src.unlink()
                continue
            if src.exists():
                src.rename(dst)

        # Move the current log to .1
        rotated = log_path.with_suffix(log_path.suffix + ".1")
        log_path.rename(rotated)

        # Re-create the original as empty (next append uses it)
        log_path.touch()
        return True
    except OSError as exc:
        logger.warning("rotation failed for %s: %r", log_path, exc)
        return False


__all__ = ["maybe_rotate", "DEFAULT_MAX_BYTES", "DEFAULT_MAX_BACKUPS"]
