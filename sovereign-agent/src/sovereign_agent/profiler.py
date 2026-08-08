"""
sovereign_agent.profiler — measure hot paths before optimising them.

Philosophy borrowed from low-level optimisation work (FFmpeg/David's
SIMD culture): *don't guess where time goes; measure it*. For a
SQLite-backed local agent, the hottest paths are typically:

    * Atom inserts (write-amplification across triggers + FTS5)
    * FTS5 queries (recall.search, task.search)
    * vec0 similarity search (when sqlite-vec is loaded)
    * Idempotency lookups (json_extract scan over atoms)

We do NOT need handwritten SIMD here — the bottleneck is SQLite, not
arithmetic. But we DO need to know which paths are hot, and we need a
cheap way to measure them. This module is that.

Usage:

    from sovereign_agent.profiler import timed, ProfilerScope

    with ProfilerScope("recall.search") as scope:
        results = rc.search(query)
    # scope.duration_ms is now populated
    # scope also writes a sample to the profile log if enabled

The profile log is JSONL at ``<data>/profile/<YYYY-MM-DD>.jsonl``,
rotated daily, append-only. Reading it gives a histogram of hot paths.
"""
from __future__ import annotations

import json
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from .config import SETTINGS


# Toggle: cheap default (in-memory only). The CLI can flip --profile to
# enable disk-write samples for one command.
_DISK_SAMPLES_ENABLED = False


@dataclass
class ProfileSample:
    label: str
    duration_ms: float
    started_at: str
    extras: dict = field(default_factory=dict)


@dataclass
class ProfilerScope:
    """Time a block. Writes a sample on __exit__ if disk samples enabled."""
    label: str
    extras: dict = field(default_factory=dict)
    duration_ms: float = 0.0
    started_at: str = ""
    _t0: float = 0.0

    def __enter__(self) -> "ProfilerScope":
        self.started_at = datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%S.%fZ"
        )
        self._t0 = time.perf_counter()
        return self

    def __exit__(self, *args) -> None:
        self.duration_ms = (time.perf_counter() - self._t0) * 1000.0
        if _DISK_SAMPLES_ENABLED:
            _append_sample(ProfileSample(
                label=self.label, duration_ms=self.duration_ms,
                started_at=self.started_at, extras=self.extras,
            ))


@contextmanager
def timed(label: str, **extras) -> Iterator[ProfilerScope]:
    """Convenience context manager: ``with timed("op"): ...``."""
    scope = ProfilerScope(label=label, extras=dict(extras))
    scope.__enter__()
    try:
        yield scope
    finally:
        scope.__exit__()


def enable_disk_samples(on: bool = True) -> None:
    """Turn disk-sample writing on/off process-wide.

    Off by default — measurement is in-memory only. Turn on for one
    command (e.g., during a slow report investigation), then turn off.
    """
    global _DISK_SAMPLES_ENABLED
    _DISK_SAMPLES_ENABLED = on


def _profile_path() -> Path:
    d = SETTINGS.paths.data_dir / "profile"
    try:
        d.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return d / f"{today}.jsonl"


def _append_sample(sample: ProfileSample) -> None:
    """Append one sample to today's JSONL log.

    Guards against runaway disk usage with two limits:
      * MAX_DAILY_BYTES — hard cap; once exceeded, samples are silently
        dropped for the rest of the day. The rotation lands on the next
        UTC date roll-over.
      * Existing-file write only — never grows beyond the cap.
    """
    MAX_DAILY_BYTES = 50 * 1024 * 1024   # 50MB / day
    try:
        path = _profile_path()
        if path.exists():
            try:
                if path.stat().st_size >= MAX_DAILY_BYTES:
                    return
            except OSError:
                pass
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({
                "label": sample.label,
                "duration_ms": round(sample.duration_ms, 3),
                "started_at": sample.started_at,
                "extras": sample.extras,
            }) + "\n")
    except OSError:
        pass


def read_samples(*, days: int = 1) -> list[ProfileSample]:
    """Read recent samples for analysis."""
    out: list[ProfileSample] = []
    now = datetime.now(timezone.utc)
    for delta in range(days):
        day = (now - _delta(delta)).strftime("%Y-%m-%d")
        p = SETTINGS.paths.data_dir / "profile" / f"{day}.jsonl"
        if not p.is_file():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                d = json.loads(line)
                out.append(ProfileSample(
                    label=d["label"], duration_ms=d["duration_ms"],
                    started_at=d["started_at"], extras=d.get("extras") or {},
                ))
            except (ValueError, KeyError):
                continue
    return out


def _delta(days: int):
    from datetime import timedelta
    return timedelta(days=days)


def summarize(samples: list[ProfileSample]) -> dict:
    """Roll up samples by label: count, sum_ms, mean_ms, p95_ms.

    p95 is approximate (sorted nth-percentile, no interpolation).
    """
    by_label: dict[str, list[float]] = {}
    for s in samples:
        by_label.setdefault(s.label, []).append(s.duration_ms)
    out = {}
    for label, ms in by_label.items():
        ms_sorted = sorted(ms)
        n = len(ms_sorted)
        p95 = ms_sorted[min(n - 1, int(0.95 * n))] if n else 0.0
        out[label] = {
            "count": n,
            "sum_ms": round(sum(ms_sorted), 3),
            "mean_ms": round(sum(ms_sorted) / n, 3) if n else 0.0,
            "p95_ms": round(p95, 3),
            "max_ms": round(max(ms_sorted), 3) if ms_sorted else 0.0,
        }
    return dict(sorted(out.items(), key=lambda kv: -kv[1]["sum_ms"]))


__all__ = [
    "ProfileSample", "ProfilerScope", "timed",
    "enable_disk_samples", "read_samples", "summarize",
]
