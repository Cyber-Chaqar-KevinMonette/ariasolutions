"""breaker — a circuit breaker so we back off failure instead of hammering it.

Classic three-state breaker (resilience4j / Hystrix lineage):

  • CLOSED     — calls flow; failures are counted.
  • OPEN       — after `fail_threshold` consecutive failures, calls are
                 refused for `cooldown_s` (protects a down source/target and
                 our own retry budget).
  • HALF_OPEN  — after the cooldown, ONE probe is allowed; success closes the
                 circuit, failure re-opens it.

Pure + deterministic: every method takes `now` (epoch seconds), so it is
fully testable without wall-clock sleeps. One breaker per source (for fetch)
and one per project (for delivery).
"""
from __future__ import annotations

from dataclasses import dataclass

CLOSED = "closed"
OPEN = "open"
HALF_OPEN = "half_open"


@dataclass
class CircuitBreaker:
    fail_threshold: int = 3
    cooldown_s: float = 60.0
    _failures: int = 0
    _state: str = CLOSED
    _opened_at: float = 0.0
    _probing: bool = False

    @property
    def state(self) -> str:
        return self._state

    def allow(self, now: float) -> bool:
        """May a call proceed right now? Transitions OPEN→HALF_OPEN when the
        cooldown elapses and hands out exactly one probe."""
        if self._state == OPEN:
            if now - self._opened_at >= self.cooldown_s:
                self._state = HALF_OPEN
                self._probing = False
            else:
                return False
        if self._state == HALF_OPEN:
            if self._probing:
                return False          # a probe is already in flight
            self._probing = True
            return True
        return True                    # CLOSED

    def record_success(self, now: float = 0.0) -> None:
        self._failures = 0
        self._state = CLOSED
        self._probing = False

    def record_failure(self, now: float) -> None:
        if self._state == HALF_OPEN:
            self._state = OPEN          # probe failed → re-open
            self._opened_at = now
            self._probing = False
            return
        self._failures += 1
        if self._failures >= self.fail_threshold:
            self._state = OPEN
            self._opened_at = now
