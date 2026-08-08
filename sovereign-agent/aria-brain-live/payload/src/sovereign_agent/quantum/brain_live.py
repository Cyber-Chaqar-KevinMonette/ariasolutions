"""quantum/brain_live.py — Bounded, stoppable "live mode" for the nested brain.

Kevin wants her brain able to run continuously — but never flooding the system. This is a SAFE
always-running substrate: a controller that runs bounded generative ticks, writes to a fixed-size
ring buffer (only the last K thoughts are kept), yields CPU between ticks, and is fully stoppable.

Hard limits (cannot be exceeded):
  - ring buffer capped at MAX_BUFFER (old thoughts drop off — never grows unbounded)
  - min sleep between ticks (CPU yield) so it can't peg the core
  - explicit start()/stop(); off by default; never auto-starts
The synchronous controller is the safe core (fully testable). A thin threaded runner is provided for
real always-on use, with the same hard limits + a stop flag.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from pathlib import Path


MAX_BUFFER = 50          # keep only the last 50 thoughts (bounded memory)
MIN_TICK_SLEEP = 0.05    # ≥50ms between ticks (CPU yield; ≤20 ticks/sec hard ceiling)


class LiveBrain:
    """Bounded, stoppable continuous-generation controller. Off by default."""

    def __init__(self, data_dir: Path, *, buffer_size: int = MAX_BUFFER,
                 tick_sleep: float = MIN_TICK_SLEEP, length: int = 60, temp: float = 0.25) -> None:
        self._data_dir = Path(data_dir)
        self._buffer: deque[str] = deque(maxlen=max(1, min(MAX_BUFFER, buffer_size)))
        self._tick_sleep = max(MIN_TICK_SLEEP, tick_sleep)   # cannot go below the floor
        self._length = max(1, min(200, length))
        self._temp = max(0.05, min(1.5, temp))
        self._ticks = 0
        self._running = False                                # NB: our own flag (controller-local)
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    # ── the bounded core (synchronous, testable) ──────────────────────────────
    def tick(self) -> str:
        """One bounded generative tick → appended to the ring buffer (oldest drops)."""
        from .brain_bench import _load_brain
        brain = _load_brain(self._data_dir)
        thought = brain.speak(length=self._length, temp=self._temp)
        with self._lock:
            self._buffer.append(thought)
            self._ticks += 1
        return thought

    def run_ticks(self, n: int) -> int:
        """Run n bounded ticks synchronously (each yields CPU). Returns ticks done."""
        n = max(1, min(1000, n))
        done = 0
        for _ in range(n):
            self.tick()
            done += 1
            time.sleep(self._tick_sleep)
        return done

    def thoughts(self) -> list[str]:
        with self._lock:
            return list(self._buffer)

    def status(self) -> dict:
        with self._lock:
            return {
                "running": self._running,
                "ticks": self._ticks,
                "buffer_size": len(self._buffer),
                "buffer_cap": self._buffer.maxlen,
                "tick_sleep_s": self._tick_sleep,
                "last_thought": self._buffer[-1] if self._buffer else None,
            }

    # ── optional threaded always-on runner (same hard limits) ─────────────────
    def start(self, max_ticks: int | None = None) -> bool:
        """Begin bounded background ticking. Off by default; explicit call only."""
        if self._running:
            return False
        self._running = True

        def _loop() -> None:
            count = 0
            while self._running:
                self.tick()
                count += 1
                if max_ticks is not None and count >= max_ticks:
                    break
                time.sleep(self._tick_sleep)
            self._running = False

        self._thread = threading.Thread(target=_loop, daemon=True, name="aria-brain-live")
        self._thread.start()
        return True

    def stop(self, timeout: float = 2.0) -> bool:
        """Stop the background runner cleanly."""
        self._running = False
        t = self._thread
        if t is not None and t.is_alive():
            t.join(timeout=timeout)
        self._thread = None
        return True
