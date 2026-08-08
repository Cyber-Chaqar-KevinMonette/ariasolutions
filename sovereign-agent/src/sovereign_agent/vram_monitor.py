"""
╔══════════════════════════════════════════════════════════════════════════╗
║  vram_monitor.py — Per-step VRAM sampling (v0.2.11)                      ║
║                                                                          ║
║  Non-invasive. Spawns nvidia-smi (or falls back to None on systems       ║
║  without GPU). Returns MB integers or None.                              ║
║                                                                          ║
║  Used by the continuation runner to record vram_before / vram_peak /     ║
║  vram_after on every model-invoking step — same pattern as elapsed_      ║
║  seconds in v0.2.7. Operator can see VRAM cost per step in CLI output    ║
║  and post-hoc via `sov continuations show <task>`.                       ║
║                                                                          ║
║  Sampling strategy:                                                      ║
║    - 'before' : single sample just before the step starts                ║
║    - 'peak'   : best-effort during execution via background thread       ║
║                 sampling at 0.5s intervals (not exact, but good enough   ║
║                 for "did this step blow up VRAM" signal)                 ║
║    - 'after'  : single sample after the step releases                    ║
║                                                                          ║
║  Why not pyNVML? Because (a) it's an extra dep, (b) nvidia-smi is        ║
║  always present where pyNVML works, (c) the sampling cost is dominated   ║
║  by the model call anyway. Subprocess is fine here.                      ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import shutil
import subprocess
import threading
import time
from dataclasses import dataclass


# Cache the nvidia-smi availability check — calling shutil.which on every
# step is wasted work.
_HAS_NVIDIA_SMI: bool | None = None


def has_gpu() -> bool:
    """Return True if nvidia-smi is on PATH AND returns successfully."""
    global _HAS_NVIDIA_SMI
    if _HAS_NVIDIA_SMI is not None:
        return _HAS_NVIDIA_SMI
    if shutil.which("nvidia-smi") is None:
        _HAS_NVIDIA_SMI = False
        return False
    try:
        proc = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=2,
        )
        _HAS_NVIDIA_SMI = (proc.returncode == 0)
    except Exception:  # noqa: BLE001
        _HAS_NVIDIA_SMI = False
    return _HAS_NVIDIA_SMI


def sample_vram_used_mb(timeout: float = 1.0) -> int | None:
    """One-shot sample of total VRAM used (integer MB).

    Returns None if no GPU or sampling failed. Designed to be cheap (~50ms)
    and never raise — VRAM monitoring should never break the runner.

    Note: this returns total used across ALL processes. For per-process
    isolation we'd need to query by pid, but for our use case (single
    Ollama instance) total-used is the meaningful signal.
    """
    if not has_gpu():
        return None
    try:
        proc = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=timeout,
        )
        if proc.returncode != 0:
            return None
        # nvidia-smi may report multiple GPUs (one per line); take the max.
        # On a single-GPU system this is equivalent to taking the only line.
        values: list[int] = []
        for line in proc.stdout.strip().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                values.append(int(line))
            except ValueError:
                continue
        return max(values) if values else None
    except Exception:  # noqa: BLE001
        return None


@dataclass
class VRAMTrace:
    """VRAM snapshot before/peak/after a single step.

    All fields in MB. None = sample unavailable (no GPU, sample failed).

    delta_mb: peak - before. Positive = the step caused VRAM growth (e.g.
              loaded a new model). Negative is unusual (would mean another
              process freed memory during your step).
    """

    before_mb: int | None = None
    peak_mb: int | None = None
    after_mb: int | None = None

    @property
    def delta_mb(self) -> int | None:
        if self.before_mb is None or self.peak_mb is None:
            return None
        return self.peak_mb - self.before_mb

    def to_dict(self) -> dict:
        return {
            "before_mb": self.before_mb,
            "peak_mb": self.peak_mb,
            "after_mb": self.after_mb,
            "delta_mb": self.delta_mb,
        }

    def display_short(self) -> str:
        """Compact display for CLI output, e.g. '6029→6802MB Δ+773'.

        Returns empty string if no data (so it doesn't clutter no-GPU output).
        """
        if self.before_mb is None or self.peak_mb is None:
            return ""
        delta = self.delta_mb or 0
        sign = "+" if delta >= 0 else ""
        return f"vram={self.before_mb}→{self.peak_mb}MB Δ{sign}{delta}"


class VRAMSampler:
    """Background-thread sampler for peak VRAM during a step.

    Usage:
        sampler = VRAMSampler()
        sampler.start()                    # captures 'before', begins polling
        try:
            ... do work ...
        finally:
            trace = sampler.stop()         # captures 'after', returns VRAMTrace

    On systems without a GPU, the sampler does nothing and returns
    VRAMTrace(None, None, None). Designed to be safe to wrap around any
    code without changing its behavior.
    """

    def __init__(self, poll_interval_seconds: float = 0.5):
        self.poll_interval = poll_interval_seconds
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._before: int | None = None
        self._peak: int | None = None
        self._lock = threading.Lock()

    def _poll_loop(self) -> None:
        while not self._stop_event.is_set():
            sample = sample_vram_used_mb(timeout=0.5)
            if sample is not None:
                with self._lock:
                    if self._peak is None or sample > self._peak:
                        self._peak = sample
            # Wait for either the interval or stop signal.
            self._stop_event.wait(self.poll_interval)

    def start(self) -> None:
        """Capture 'before' sample and start the polling thread."""
        if not has_gpu():
            # Stay inert — no thread, no overhead.
            return
        self._before = sample_vram_used_mb()
        with self._lock:
            self._peak = self._before  # peak starts at before
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()

    def stop(self) -> VRAMTrace:
        """Stop polling, capture 'after' sample, return the full trace."""
        if self._thread is not None:
            self._stop_event.set()
            self._thread.join(timeout=2.0)
        after = sample_vram_used_mb()
        with self._lock:
            return VRAMTrace(
                before_mb=self._before,
                peak_mb=self._peak,
                after_mb=after,
            )
