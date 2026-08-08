"""lag_probe.py — AL0 (anti-lag round): opt-in wall-clock probe for hot paths.

The anti-lag investigation (2026-07-11) found candidate lag sources by
reading code; this probe exists so the *ranking* is measured, not assumed.
It is the seed of the fuller `lag_ledger` (AL1) — deliberately tiny so it
can ship same-day with the quick fixes.

Usage: set ``SOV_LAG_PROBE=1`` (summaries go to /tmp/sov_lag_probe.log) or
``SOV_LAG_PROBE=/path/to/file``. Instrumented sites call ``note(site, ms)``
after timing themselves with ``time.perf_counter()``. Every ~30s the
accumulated per-site stats (count / avg / max) are appended as one summary
block and the counters reset.

Zero overhead when unset: ``ENABLED`` is a module-level constant, so every
instrumented site short-circuits on a single truthiness check.
"""
from __future__ import annotations

import os
import time

_RAW = os.environ.get("SOV_LAG_PROBE", "").strip()
ENABLED: bool = bool(_RAW)
_PATH = _RAW if "/" in _RAW else "/tmp/sov_lag_probe.log"

_FLUSH_EVERY_S = 30.0
_stats: dict[str, list[float]] = {}          # site -> [count, total_ms, max_ms]
_next_flush: list[float] = [time.monotonic() + _FLUSH_EVERY_S]


def note(site: str, dur_ms: float) -> None:
    """Record one timed call. Cheap; flushes a summary block every ~30s."""
    if not ENABLED:
        return
    st = _stats.setdefault(site, [0, 0.0, 0.0])
    st[0] += 1
    st[1] += dur_ms
    if dur_ms > st[2]:
        st[2] = dur_ms
    now = time.monotonic()
    if now >= _next_flush[0]:
        _next_flush[0] = now + _FLUSH_EVERY_S
        _flush()


def _flush() -> None:
    try:
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        lines = [f"── lag probe @ {stamp} (last {_FLUSH_EVERY_S:.0f}s) ──\n"]
        for site, (n, total, mx) in sorted(
            _stats.items(), key=lambda kv: kv[1][1], reverse=True
        ):
            avg = total / n if n else 0.0
            lines.append(
                f"  {site}: n={int(n)} avg={avg:.2f}ms max={mx:.2f}ms "
                f"total={total:.0f}ms\n"
            )
        with open(_PATH, "a", encoding="utf-8") as fh:
            fh.writelines(lines)
        _stats.clear()
    except Exception:  # noqa: BLE001 — a diagnostics probe must never crash the app
        pass


__all__ = ["ENABLED", "note"]
