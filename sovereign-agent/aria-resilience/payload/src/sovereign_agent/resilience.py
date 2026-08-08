"""
resilience.py — Circuit breaker + exponential backoff (M34).

Protects against cascading failures when Ollama stalls or a tool enters
a failure loop. Three components:

  CircuitBreaker — per-name breaker with CLOSED/OPEN/HALF_OPEN states.
    CLOSED  → normal operation, calls pass through
    OPEN    → failing, calls rejected immediately (saves iterations)
    HALF_OPEN → one probe call allowed to test recovery

  BreakerRegistry — session-scoped dict of named circuit breakers.
    get_breaker(name) → CircuitBreaker (creates if absent)
    all_statuses()    → list[dict] for resilience_status() tool

  exponential_backoff(attempt, base, cap, jitter) → float seconds to wait.

Usage in loop.py:
  Before tool.execute(): check tool breaker → if OPEN, skip execution
  In ollama_client.py:   retry with backoff on connection failure
"""
from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class CircuitState(StrEnum):
    CLOSED = "closed"       # normal — calls pass through
    OPEN = "open"           # failing — calls rejected immediately
    HALF_OPEN = "half_open" # one probe call to test recovery


@dataclass
class CircuitBreaker:
    """Per-resource circuit breaker."""
    name: str
    failure_threshold: int = 3
    recovery_window: float = 60.0     # seconds to wait before HALF_OPEN
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    last_failure_at: float = 0.0
    last_success_at: float = 0.0

    def call_allowed(self) -> bool:
        if self.state == CircuitState.CLOSED:
            return True
        if self.state == CircuitState.HALF_OPEN:
            return True  # one probe through
        # OPEN: check if recovery window has elapsed
        if time.monotonic() - self.last_failure_at >= self.recovery_window:
            self.state = CircuitState.HALF_OPEN
            return True
        return False

    def record_success(self) -> None:
        self.last_success_at = time.monotonic()
        self.failure_count = 0
        self.state = CircuitState.CLOSED

    def record_failure(self) -> None:
        self.failure_count += 1
        self.last_failure_at = time.monotonic()
        if self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN

    def status(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "last_failure_at": self.last_failure_at or None,
            "last_success_at": self.last_success_at or None,
            "recovery_window": self.recovery_window,
        }


class BreakerRegistry:
    """Session-scoped registry of named circuit breakers."""

    def __init__(self) -> None:
        self._breakers: dict[str, CircuitBreaker] = {}

    def get_breaker(self, name: str,
                    failure_threshold: int = 3,
                    recovery_window: float = 60.0) -> CircuitBreaker:
        if name not in self._breakers:
            self._breakers[name] = CircuitBreaker(
                name=name,
                failure_threshold=failure_threshold,
                recovery_window=recovery_window,
            )
        return self._breakers[name]

    def all_statuses(self) -> list[dict[str, Any]]:
        return [b.status() for b in self._breakers.values()]


def exponential_backoff(attempt: int,
                        base: float = 1.0,
                        cap: float = 60.0,
                        jitter: bool = True) -> float:
    """Return seconds to wait before `attempt` (0-indexed).

    Uses truncated binary exponential backoff:
      wait = min(cap, base * 2^attempt)

    With jitter: wait = random.uniform(0, wait)  (full-jitter)
    """
    wait = min(cap, base * math.pow(2, attempt))
    if jitter:
        wait = random.uniform(0.0, wait)
    return wait


__all__ = ["CircuitBreaker", "CircuitState", "BreakerRegistry", "exponential_backoff"]
