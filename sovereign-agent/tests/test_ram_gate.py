"""Tests for ram_gate — the RAM-safety wait gate before loading a heavy
model. Kevin, 2026-07-28: "don't rush into the gpu too fast when switching
modes." All tests use injected reader/clock/sleep — no real /proc access,
no real waiting."""
from __future__ import annotations

from sovereign_agent.ram_gate import read_available_mb, wait_for_ram_safe


def _reader_returning(mem_available_kb: int | None):
    def _r():
        if mem_available_kb is None:
            return {}
        return {"MemAvailable": mem_available_kb}
    return _r


class _FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.t += seconds


def test_read_available_mb_converts_kb_to_mb():
    assert read_available_mb(_reader_returning(4096 * 1024)) == 4096


def test_read_available_mb_falls_back_to_memfree():
    def _r():
        return {"MemFree": 2048 * 1024}
    assert read_available_mb(_r) == 2048


def test_read_available_mb_missing_info_returns_none():
    assert read_available_mb(_reader_returning(None)) is None


def test_read_available_mb_never_raises_on_bad_reader():
    def _boom():
        raise RuntimeError("no /proc here")
    assert read_available_mb(_boom) is None


def test_wait_for_ram_safe_returns_immediately_when_already_safe():
    clock = _FakeClock()
    calls = []
    ok, reason = wait_for_ram_safe(
        min_available_mb=2048,
        reader=_reader_returning(4096 * 1024),
        clock=clock, sleep=clock.sleep,
        on_wait=lambda avail, elapsed: calls.append((avail, elapsed)),
    )
    assert ok is True and reason == ""
    assert calls == []          # never waited at all
    assert clock.t == 0.0       # no time elapsed


def test_wait_for_ram_safe_polls_and_calls_on_wait_until_safe():
    readings = iter([500 * 1024, 500 * 1024, 3000 * 1024])   # unsafe, unsafe, safe

    def _reader():
        return {"MemAvailable": next(readings)}

    clock = _FakeClock()
    calls = []
    ok, reason = wait_for_ram_safe(
        min_available_mb=2048, timeout_seconds=60, poll_seconds=5,
        reader=_reader, clock=clock, sleep=clock.sleep,
        on_wait=lambda avail, elapsed: calls.append(avail),
    )
    assert ok is True and reason == ""
    assert calls == [500, 500]   # called once per unsafe tick, not on the final safe check
    assert clock.t == 10.0       # two 5s polls elapsed


def test_wait_for_ram_safe_times_out_honestly():
    clock = _FakeClock()
    ok, reason = wait_for_ram_safe(
        min_available_mb=2048, timeout_seconds=10, poll_seconds=5,
        reader=_reader_returning(100 * 1024),
        clock=clock, sleep=clock.sleep,
    )
    assert ok is False
    assert "never cleared" in reason
    assert "100" in reason


def test_wait_for_ram_safe_unreadable_info_degrades_to_proceed():
    clock = _FakeClock()
    ok, reason = wait_for_ram_safe(
        min_available_mb=2048,
        reader=_reader_returning(None),
        clock=clock, sleep=clock.sleep,
    )
    assert ok is True and reason == ""


def test_wait_for_ram_safe_broken_on_wait_callback_does_not_crash_the_gate():
    readings = iter([500 * 1024, 3000 * 1024])

    def _reader():
        return {"MemAvailable": next(readings)}

    clock = _FakeClock()

    def _broken_on_wait(avail, elapsed):
        raise ValueError("UI blew up")

    ok, reason = wait_for_ram_safe(
        min_available_mb=2048, timeout_seconds=60, poll_seconds=5,
        reader=_reader, clock=clock, sleep=clock.sleep,
        on_wait=_broken_on_wait,
    )
    assert ok is True and reason == ""
