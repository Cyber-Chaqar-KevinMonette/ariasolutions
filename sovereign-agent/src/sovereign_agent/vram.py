"""VRAM accounting. Ported from mos_vram.py — the math, not the ceremony.

On an 8 GB Pascal card (GTX 1070):
  Ollama 8B weights:    ~5,200 MB (qwen3:8b q4_K_M)
  KV-cache 16k:           ~550 MB (peak during generation)
  OS / compositor:        ~800 MB
  CUDA driver:            ~200 MB
  Safety floor:           ~200 MB
  Headroom for tools:    ~1,242 MB

Heavy tools that contend with the orchestrator for VRAM:
  faster-whisper transcription: ~4,096 MB
  EasyOCR vision pipeline:      ~2,048 MB

These MUST NOT run concurrently with the orchestrator. The Mode Controller
checks ``can_run_heavy_tool`` before scheduling them, and ``vram_lock``
serializes access via a file lock so two tools can't fire at once.
"""
from __future__ import annotations

import contextlib
import os
import shutil
import subprocess
import time
from dataclasses import dataclass

from .config import SETTINGS
from .events import emit_event

# Hardware budget defaults (override via env: AGENT_VRAM_TOTAL_MB, etc.)
TOTAL_VRAM_MB = int(os.environ.get("AGENT_VRAM_TOTAL_MB", "8192"))
SAFETY_FLOOR_MB = int(os.environ.get("AGENT_VRAM_SAFETY_MB", "200"))
ORCHESTRATOR_VRAM_MB = int(os.environ.get("AGENT_VRAM_ORCHESTRATOR_MB", "5750"))

# Known heavy tool costs
HEAVY_TOOL_VRAM_MB: dict[str, int] = {
    "transcribe_video": 4096,
    "ocr_pdf":          2048,
    "ocr_image":        1024,
}


@dataclass(frozen=True)
class VRAMSnapshot:
    total_mb: int
    used_mb: int
    free_mb: int
    source: str           # "nvml" | "nvidia-smi" | "estimate"


def read_vram() -> VRAMSnapshot:
    """Best-effort VRAM read. Falls back gracefully when nvidia tools are absent."""
    # Try pynvml first (fast)
    try:
        import pynvml

        pynvml.nvmlInit()
        h = pynvml.nvmlDeviceGetHandleByIndex(0)
        info = pynvml.nvmlDeviceGetMemoryInfo(h)
        return VRAMSnapshot(
            total_mb=info.total // (1024 * 1024),
            used_mb=info.used // (1024 * 1024),
            free_mb=info.free // (1024 * 1024),
            source="nvml",
        )
    except Exception:  # noqa: BLE001 — nvml is best-effort
        pass

    # Fall back to nvidia-smi
    if shutil.which("nvidia-smi"):
        try:
            out = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=memory.total,memory.used,memory.free",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=5,
                check=True,
            )
            total, used, free = (int(x.strip()) for x in out.stdout.split(",")[:3])
            return VRAMSnapshot(total_mb=total, used_mb=used, free_mb=free, source="nvidia-smi")
        except Exception:  # noqa: BLE001
            pass

    # Last resort: assume orchestrator is loaded, headroom = whatever's left
    return VRAMSnapshot(
        total_mb=TOTAL_VRAM_MB,
        used_mb=ORCHESTRATOR_VRAM_MB,
        free_mb=TOTAL_VRAM_MB - ORCHESTRATOR_VRAM_MB - SAFETY_FLOOR_MB,
        source="estimate",
    )


def can_run_heavy_tool(tool_name: str) -> tuple[bool, str]:
    """Should the Mode Controller fire this heavy tool right now?

    Returns (ok, reason). False means defer until VRAM frees up.
    """
    cost = HEAVY_TOOL_VRAM_MB.get(tool_name)
    if cost is None:
        return True, "tool not in heavy list"

    snap = read_vram()
    needed = cost + SAFETY_FLOOR_MB
    if snap.free_mb < needed:
        return False, (
            f"insufficient VRAM: need {needed} MB, have {snap.free_mb} MB free "
            f"(source={snap.source})"
        )
    return True, f"ok: {snap.free_mb} MB free, need {needed} MB"


@contextlib.contextmanager
def vram_lock(tool_name: str, *, timeout_seconds: float = 60.0):
    """Serialize heavy-tool access via a file lock.

    Two heavy tools must never run concurrently — both would OOM. The
    orchestrator implicitly always has the lock; this only gates non-model
    GPU work (whisper, OCR).
    """
    import fcntl

    SETTINGS.paths.config_dir.mkdir(parents=True, exist_ok=True)
    lock_path = SETTINGS.paths.config_dir / "vram.lock"
    lock_path.touch(exist_ok=True)

    start = time.monotonic()
    f = lock_path.open("r+")
    try:
        while True:
            try:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() - start > timeout_seconds:
                    emit_event(
                        "vram-lock-timeout-d",
                        plane="control",
                        trace_id="vram",
                        payload={"tool": tool_name, "timeout_seconds": timeout_seconds},
                    )
                    raise TimeoutError(
                        f"vram_lock: another tool held the lock for >{timeout_seconds}s"
                    ) from None
                time.sleep(0.5)
        # Stamp who holds it for debug
        f.seek(0)
        f.truncate()
        f.write(f"{tool_name} {os.getpid()} {time.time()}\n")
        f.flush()
        yield
    finally:
        try:
            fcntl.flock(f, fcntl.LOCK_UN)
        except Exception:  # noqa: BLE001
            pass
        f.close()
