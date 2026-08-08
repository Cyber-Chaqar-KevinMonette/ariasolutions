"""contracts — rate-limits as a structural gate, not a guideline.

The heart of "legitimate by construction". Two rules, both enforced:

  1. You may not poll a source faster than the rate it permits. A
     `RateContract` whose `poll_interval_s` is below a source's declared
     `allowed_min_interval_s` raises `ContractViolation` at construction —
     an unpollable-too-fast bot cannot even be built.
  2. You may not fire deliveries faster than the contract's ceiling. The
     `RateGate` tracks a sliding one-minute window and refuses a send that
     would exceed `max_sends_per_minute`.

Pure + deterministic: every method takes `now` (epoch seconds) so it is
fully testable without wall-clock sleeps.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field


class ContractViolation(ValueError):
    """Raised when a configuration would violate an allowed rate."""


@dataclass(frozen=True)
class RateContract:
    """The enforced rate ceiling for one running bot.

    poll_interval_s        — seconds between polls of any one source.
    max_sends_per_minute   — hard cap on deliveries per rolling minute.
    """
    poll_interval_s: float = 60.0
    max_sends_per_minute: int = 5

    def __post_init__(self) -> None:
        if self.poll_interval_s <= 0:
            raise ContractViolation("poll_interval_s must be > 0")
        if self.max_sends_per_minute <= 0:
            raise ContractViolation("max_sends_per_minute must be > 0")

    def validate_for_source(self, allowed_min_interval_s: float) -> None:
        """Refuse a contract that would poll faster than a source permits."""
        if self.poll_interval_s < allowed_min_interval_s:
            raise ContractViolation(
                f"contract polls every {self.poll_interval_s}s but the source "
                f"permits no faster than every {allowed_min_interval_s}s — "
                f"raise poll_interval_s to respect the source's allowed rate")


@dataclass
class RateGate:
    """Stateful gate that enforces a `RateContract` over real time.

    Inject `now` on every call; nothing sleeps or reads the clock itself.
    """
    contract: RateContract
    _last_poll: dict[str, float] = field(default_factory=dict)
    _sends: deque[float] = field(default_factory=deque)

    # ── polling ──
    def poll_due(self, source_name: str, now: float) -> bool:
        last = self._last_poll.get(source_name)
        if last is None:
            return True
        return (now - last) >= self.contract.poll_interval_s

    def record_poll(self, source_name: str, now: float) -> None:
        self._last_poll[source_name] = now

    def seconds_until_poll(self, source_name: str, now: float) -> float:
        last = self._last_poll.get(source_name)
        if last is None:
            return 0.0
        remaining = self.contract.poll_interval_s - (now - last)
        return max(0.0, remaining)

    # ── sending ──
    def _prune(self, now: float) -> None:
        cutoff = now - 60.0
        while self._sends and self._sends[0] <= cutoff:
            self._sends.popleft()

    def send_allowed(self, now: float) -> bool:
        self._prune(now)
        return len(self._sends) < self.contract.max_sends_per_minute

    def remaining_sends(self, now: float) -> int:
        self._prune(now)
        return max(0, self.contract.max_sends_per_minute - len(self._sends))

    def record_send(self, now: float) -> None:
        self._prune(now)
        self._sends.append(now)
