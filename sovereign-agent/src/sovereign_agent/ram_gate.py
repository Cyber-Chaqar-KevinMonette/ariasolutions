"""ram_gate — wait for system RAM to be safe before loading a heavy model.

movie-focus-d (Kevin, 2026-07-28): "The system have to wait for the system
ram to be safe before the vision model is loaded also. So don't rush into
the gpu too fast when switching modes." Directly motivated by two real
crashes tonight: `enable_sequential_cpu_offload()` keeps a whole ~10GB
model resident in system RAM by design, and this 15GB-RAM machine has a
separate, real memory leak (`aria-duty.service`'s Playwright scraper) that
can eat most of it before a movie generation even starts.

No RAM-safety gate existed anywhere in this repo before this — `vram.py`'s
`vram_lock()` is a pure mutex (never measures free RAM/VRAM, just
serializes access) and RAM was only ever read for reporting
(`cockpit/sysmon.py`, `model_ladder.probe_hardware()`), never gated on.

Mirrors two existing shapes rather than inventing a new one:
  - `self_practice.py`'s `_interruptible_rest()` — injectable clock/sleep,
    small poll slices, a defensive iteration cap so a stalled clock can
    never loop forever.
  - `model_ladder.py`'s probe-before-trust idiom — measure for real, don't
    assume.

Default threshold (2GB) is reasoned, not guessed: real crashes tonight
happened when available RAM dropped to a few hundred MB or less; this
machine's swap (19GB) absorbs the rest of a big model's footprint, so 2GB
of genuine headroom before a load starts is a conservative floor.
"""
from __future__ import annotations

import time as _time
from typing import Callable, Optional

__all__ = ["read_available_mb", "wait_for_ram_safe", "DEFAULT_MIN_AVAILABLE_MB"]

DEFAULT_MIN_AVAILABLE_MB = 2048


def _default_meminfo_reader() -> dict[str, int]:
    """Read /proc/meminfo -> {key: value_in_kB}. Same parsing as
    cockpit/sysmon.py's SystemMonitor._read_meminfo, kept independent here
    (no SystemMonitor instance required) so this module has zero cockpit
    dependency and can be called from tools/CLI code too."""
    info: dict[str, int] = {}
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                key, _, rest = line.partition(":")
                val = rest.strip().split()
                if val:
                    info[key] = int(val[0])
    except (OSError, ValueError):
        pass
    return info


def read_available_mb(reader: Optional[Callable[[], dict[str, int]]] = None) -> Optional[int]:
    """Real available RAM in MB, or None if it couldn't be read (e.g. not
    Linux, or /proc unavailable) — never raises."""
    reader = reader or _default_meminfo_reader
    try:
        info = reader()
    except Exception:  # noqa: BLE001
        return None
    if not info:
        return None
    kb = info.get("MemAvailable", info.get("MemFree"))
    if kb is None:
        return None
    return kb // 1024


def wait_for_ram_safe(
    *,
    min_available_mb: int = DEFAULT_MIN_AVAILABLE_MB,
    timeout_seconds: float = 300.0,
    poll_seconds: float = 5.0,
    on_wait: Optional[Callable[[Optional[int], float], None]] = None,
    reader: Optional[Callable[[], dict[str, int]]] = None,
    clock: Optional[Callable[[], float]] = None,
    sleep: Optional[Callable[[float], None]] = None,
) -> tuple[bool, str]:
    """Poll until MemAvailable >= min_available_mb, or give up after
    timeout_seconds. Never raises — returns (True, "") once safe (including
    immediately, with no wait, if already safe) or (False, reason) on
    timeout. `on_wait(available_mb, elapsed_seconds)` fires once per poll
    tick while NOT yet safe — the caller's hook for a "please wait, RAM is
    still settling" UI message.

    Unreadable RAM info (reader returns None) degrades to "proceed" rather
    than blocking forever on information that will never arrive — same
    "dormant, not broken" discipline as the rest of this repo.
    """
    clock = clock or _time.monotonic
    sleep = sleep or _time.sleep
    poll_seconds = max(0.1, poll_seconds)
    start = clock()

    # Defensive cap: even if the clock doesn't advance, this loop still ends.
    max_iters = int(timeout_seconds / poll_seconds) + 2
    for _ in range(max_iters):
        available = read_available_mb(reader)
        elapsed = clock() - start
        if available is None or available >= min_available_mb:
            return True, ""
        if on_wait is not None:
            try:
                on_wait(available, elapsed)
            except Exception:  # noqa: BLE001 — a broken UI callback must never break the gate
                pass
        if elapsed >= timeout_seconds:
            return False, (
                f"RAM never cleared to {min_available_mb}MB within "
                f"{timeout_seconds:.0f}s (last seen: {available}MB available)"
            )
        sleep(min(poll_seconds, max(0.0, timeout_seconds - elapsed)))

    available = read_available_mb(reader)
    if available is None or available >= min_available_mb:
        return True, ""
    return False, f"RAM never cleared to {min_available_mb}MB (timeout)"
