"""VRAM accounting tests. Architecture §12, ported math from mos_vram.

These verify the tool-gating logic (``can_run_heavy_tool``) and the file
lock (``vram_lock``). The ``read_vram`` function itself depends on
external tools (pynvml or nvidia-smi); we don't mock those — we just
ensure it returns a plausible snapshot in the estimate fallback case.
"""
from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from sovereign_agent.vram import (
    HEAVY_TOOL_VRAM_MB,
    SAFETY_FLOOR_MB,
    VRAMSnapshot,
    can_run_heavy_tool,
    read_vram,
    vram_lock,
)


def test_read_vram_returns_plausible_snapshot():
    snap = read_vram()
    assert isinstance(snap, VRAMSnapshot)
    assert snap.total_mb > 0
    assert snap.used_mb >= 0
    assert snap.free_mb >= 0
    assert snap.source in {"nvml", "nvidia-smi", "estimate"}


def test_can_run_unknown_tool_always_passes():
    """A tool we haven't classified as heavy is approved by default."""
    ok, reason = can_run_heavy_tool("read_file")
    assert ok is True
    assert "not in heavy list" in reason


def test_heavy_tool_gating_respects_free_vram(monkeypatch):
    """If free VRAM is below tool's cost + safety floor, gate refuses."""
    fake_snap = VRAMSnapshot(total_mb=8192, used_mb=7000, free_mb=500, source="estimate")
    monkeypatch.setattr("sovereign_agent.vram.read_vram", lambda: fake_snap)

    ok, reason = can_run_heavy_tool("transcribe_video")  # needs 4096 + safety
    assert ok is False
    assert "insufficient" in reason.lower()


def test_heavy_tool_gating_passes_with_headroom(monkeypatch):
    """If free VRAM is sufficient, gate approves."""
    fake_snap = VRAMSnapshot(total_mb=8192, used_mb=2000, free_mb=6000, source="estimate")
    monkeypatch.setattr("sovereign_agent.vram.read_vram", lambda: fake_snap)

    ok, reason = can_run_heavy_tool("ocr_image")  # needs 1024 + safety
    assert ok is True


def test_heavy_tool_costs_are_realistic():
    """Sanity-check the cost table: nothing exceeds 8 GB GPU's headroom."""
    for tool_name, cost in HEAVY_TOOL_VRAM_MB.items():
        assert 0 < cost <= 8192, f"{tool_name}: {cost} MB is out of range"


def test_vram_lock_serializes_access():
    """Two callers must not hold the lock simultaneously."""
    held: list[str] = []
    barrier_released = []

    def hold_briefly(label: str, sleep: float):
        with vram_lock(f"test-tool-{label}", timeout_seconds=5):
            held.append(f"{label}-acquired")
            time.sleep(sleep)
            held.append(f"{label}-released")
        barrier_released.append(label)

    with ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(hold_briefly, "A", 0.3)
        time.sleep(0.05)  # ensure A grabs first
        f2 = executor.submit(hold_briefly, "B", 0.1)
        f1.result(timeout=5)
        f2.result(timeout=5)

    # The acquire/release pairs must be properly nested — no interleaving
    assert held == [
        "A-acquired", "A-released",
        "B-acquired", "B-released",
    ]


def test_vram_lock_timeout_raises():
    """If the lock can't be acquired within timeout, raise TimeoutError."""
    def hold_long():
        with vram_lock("blocker", timeout_seconds=10):
            time.sleep(2)

    with ThreadPoolExecutor(max_workers=1) as executor:
        f = executor.submit(hold_long)
        time.sleep(0.1)  # let blocker acquire

        with pytest.raises(TimeoutError):
            with vram_lock("waiter", timeout_seconds=0.5):
                pass

        f.result(timeout=5)


def test_safety_floor_is_positive():
    """The safety floor protects the OS / compositor from OOM. Don't ever zero it."""
    assert SAFETY_FLOOR_MB > 0
