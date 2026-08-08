"""tools/vision_tools.py — Screen perception tools (M45).

  vision_capture()                           T1 — screenshot + CPU OCR + memory update
  vision_scene()                             T0 — latest cached scene (no capture)
  vision_diff()                              T0 — what changed since last capture
  vision_memory(limit=5)                     T0 — last N visual scenes
  vision_deep(question=None)                 T1 — heavy VLM analysis (llava:7b)
  vision_watch(interval_seconds, duration_seconds)  T2 — periodic capture

CPU-first: EasyOCR gpu=False or tesseract subprocess. Zero VRAM for capture.
vision_deep() is the only exception: uses vram_lock + llava:7b.
"""
from __future__ import annotations

import asyncio
from typing import Optional

from pydantic import BaseModel, Field

from .base import Tool, ToolResult

# Module-level imports for testability
try:
    from sovereign_agent.vision import (
        VisualScene,
        build_scene,
        capture_screenshot,
        get_vision_memory,
        infer_context,
    )
except ImportError:
    VisualScene = None  # type: ignore[assignment]
    build_scene = None  # type: ignore[assignment]
    capture_screenshot = None  # type: ignore[assignment]
    get_vision_memory = None  # type: ignore[assignment]
    infer_context = None  # type: ignore[assignment]


# ── vision_capture ────────────────────────────────────────────────────────────


class _CaptureArgs(BaseModel):
    pass


class VisionCaptureTool(Tool[_CaptureArgs]):
    name = "vision_capture"
    tier = 1
    description = (
        "Capture the current screen state via screenshot + CPU OCR. "
        "Updates visual memory. ~200ms-2s. Returns text blocks, inferred context, scene hash. "
        "CPU-only: zero VRAM consumed. Requires grim (Wayland screenshot tool). "
        "Use before asking 'what is on screen?' or when vision context is needed."
    )
    failure_modes = ("grim_unavailable", "ocr_failed", "screenshot_write_failed")
    Args = _CaptureArgs

    async def execute(self, args: _CaptureArgs, *, trace_id: str) -> ToolResult:  # noqa: ARG002
        try:
            screenshot_path = await asyncio.to_thread(capture_screenshot)
            scene = await asyncio.to_thread(build_scene, screenshot_path)
            mem = get_vision_memory()
            await asyncio.to_thread(mem.push, scene)

            return ToolResult(ok=True, output={
                "captured_at": scene.captured_at,
                "screenshot_path": scene.screenshot_path,
                "text_block_count": len(scene.text_blocks),
                "text_preview": scene.full_text()[:300] if scene.text_blocks else "",
                "inferred_context": scene.inferred_context,
                "ocr_elapsed_ms": scene.ocr_elapsed_ms,
                "scene_hash": scene.scene_hash,
                "ocr_available": bool(scene.text_blocks) or True,
            })
        except Exception as e:  # noqa: BLE001
            return ToolResult(ok=False, error=f"vision_capture failed: {e}")


# ── vision_scene ──────────────────────────────────────────────────────────────


class _SceneArgs(BaseModel):
    pass


class VisionSceneTool(Tool[_SceneArgs]):
    name = "vision_scene"
    tier = 0
    description = (
        "Return the latest cached visual scene without taking a new screenshot. "
        "Instant. Returns None if no capture has been made this session. "
        "Use when you need what was last seen without triggering a new capture."
    )
    failure_modes = ("vision_memory_empty",)
    Args = _SceneArgs

    async def execute(self, args: _SceneArgs, *, trace_id: str) -> ToolResult:  # noqa: ARG002
        try:
            mem = get_vision_memory()
            scene = await asyncio.to_thread(mem.latest)
            if scene is None:
                return ToolResult(ok=True, output={
                    "scene": None,
                    "message": "No visual scene in memory. Call vision_capture() first.",
                })
            return ToolResult(ok=True, output={
                "scene": scene.as_dict(),
                "inferred_context": scene.inferred_context,
                "captured_at": scene.captured_at,
                "scene_hash": scene.scene_hash,
            })
        except Exception as e:  # noqa: BLE001
            return ToolResult(ok=False, error=f"vision_scene failed: {e}")


# ── vision_diff ───────────────────────────────────────────────────────────────


class _DiffArgs(BaseModel):
    pass


class VisionDiffTool(Tool[_DiffArgs]):
    name = "vision_diff"
    tier = 0
    description = (
        "Show what changed on screen since the previous capture. "
        "Returns changed=True if visual content differs (by scene hash). "
        "Useful for detecting when Kevin switches context or something changes."
    )
    failure_modes = ("insufficient_history",)
    Args = _DiffArgs

    async def execute(self, args: _DiffArgs, *, trace_id: str) -> ToolResult:  # noqa: ARG002
        try:
            mem = get_vision_memory()
            diff = await asyncio.to_thread(mem.diff_from_prev)
            return ToolResult(ok=True, output=diff)
        except Exception as e:  # noqa: BLE001
            return ToolResult(ok=False, error=f"vision_diff failed: {e}")


# ── vision_memory ─────────────────────────────────────────────────────────────


class _MemoryArgs(BaseModel):
    limit: int = Field(default=5, ge=1, le=5)


class VisionMemoryTool(Tool[_MemoryArgs]):
    name = "vision_memory"
    tier = 0
    description = (
        "Return the last N visual scenes from rolling memory (max 5). "
        "Shows the visual history of this session. "
        "Useful for understanding how Kevin's screen has evolved."
    )
    failure_modes = ("vision_memory_empty",)
    Args = _MemoryArgs

    async def execute(self, args: _MemoryArgs, *, trace_id: str) -> ToolResult:  # noqa: ARG002
        try:
            mem = get_vision_memory()
            scenes = await asyncio.to_thread(mem.last_n, args.limit)
            return ToolResult(ok=True, output={
                "scenes": [
                    {
                        "captured_at": s.captured_at,
                        "inferred_context": s.inferred_context,
                        "scene_hash": s.scene_hash,
                        "text_block_count": len(s.text_blocks),
                        "text_preview": s.full_text()[:100],
                    }
                    for s in scenes
                ],
                "count": len(scenes),
            })
        except Exception as e:  # noqa: BLE001
            return ToolResult(ok=False, error=f"vision_memory failed: {e}")


# ── vision_deep ───────────────────────────────────────────────────────────────


class _DeepArgs(BaseModel):
    question: Optional[str] = Field(
        default=None,
        max_length=500,
        description="What to ask about the screen. Omit for general analysis.",
    )
    image_path: Optional[str] = Field(
        default=None,
        description="Path to image to analyze. Uses latest capture if omitted.",
    )


class VisionDeepTool(Tool[_DeepArgs]):
    name = "vision_deep"
    tier = 1
    description = (
        "Deep semantic vision analysis using llava:7b via vram_lock. "
        "Expensive (~5-15s, uses vram_lock to prevent VRAM conflicts). "
        "Use sparingly. CPU OCR via vision_capture() is preferred for routine use. "
        "vision_deep() is for complex questions that require semantic understanding."
    )
    failure_modes = ("vram_lock_timeout", "vision_model_unavailable", "no_image_available")
    Args = _DeepArgs

    async def execute(self, args: _DeepArgs, *, trace_id: str) -> ToolResult:
        try:
            # Resolve image path
            img_path: Optional[str] = args.image_path
            if not img_path:
                mem = get_vision_memory()
                scene = await asyncio.to_thread(mem.latest)
                if scene is None:
                    # Take a fresh screenshot
                    shot = await asyncio.to_thread(capture_screenshot)
                    if shot:
                        img_path = str(shot)
                else:
                    img_path = scene.screenshot_path

            if not img_path:
                return ToolResult(ok=False, error="No image available. Run vision_capture() first.")

            from sovereign_agent.config import SETTINGS
            from sovereign_agent.vram import vram_lock
            from sovereign_agent.ollama_client import OllamaClient, CallKind

            prompt = args.question or (
                "Describe what is on this screen. What is the user working on? "
                "What tools or applications are visible?"
            )

            def _call_vision() -> str:
                client = OllamaClient(host=SETTINGS.ollama_host)
                with vram_lock("vision_deep"):
                    import base64 as _b64
                    from pathlib import Path as _Path
                    img_bytes = _Path(img_path).read_bytes()
                    img_b64 = _b64.b64encode(img_bytes).decode()
                    # Direct Ollama vision call
                    import httpx
                    resp = httpx.post(
                        f"{SETTINGS.ollama_host}/api/generate",
                        json={
                            "model": SETTINGS.vision_model,
                            "prompt": prompt,
                            "images": [img_b64],
                            "stream": False,
                        },
                        timeout=60.0,
                    )
                    resp.raise_for_status()
                    return resp.json().get("response", "")

            analysis = await asyncio.to_thread(_call_vision)
            return ToolResult(ok=True, output={
                "analysis": analysis,
                "image_path": img_path,
                "question": prompt,
                "model": SETTINGS.vision_model,
            })
        except Exception as e:  # noqa: BLE001
            return ToolResult(ok=False, error=f"vision_deep failed: {e}")


# ── vision_watch ─────────────────────────────────────────────────────────────


class _WatchArgs(BaseModel):
    interval_seconds: int = Field(
        default=10,
        ge=5,
        le=60,
        description="How often to capture (seconds).",
    )
    duration_seconds: int = Field(
        default=60,
        ge=10,
        le=300,
        description="Total watch duration (seconds). Max 5 minutes.",
    )


class VisionWatchTool(Tool[_WatchArgs]):
    name = "vision_watch"
    tier = 2
    description = (
        "Periodically capture screen for N seconds at given interval. "
        "T2 — Kevin must confirm (can run for up to 5 minutes). "
        "Fills visual memory with a sequence of scenes. "
        "Use when monitoring for changes over time."
    )
    failure_modes = ("grim_unavailable", "duration_exceeded", "interrupted")
    Args = _WatchArgs

    async def execute(self, args: _WatchArgs, *, trace_id: str) -> ToolResult:
        try:
            mem = get_vision_memory()
            captures = 0
            import time as _time
            start = _time.monotonic()

            while _time.monotonic() - start < args.duration_seconds:
                screenshot_path = await asyncio.to_thread(capture_screenshot)
                scene = await asyncio.to_thread(build_scene, screenshot_path)
                await asyncio.to_thread(mem.push, scene)
                captures += 1
                remaining = args.duration_seconds - (_time.monotonic() - start)
                if remaining > args.interval_seconds:
                    await asyncio.sleep(args.interval_seconds)
                else:
                    break

            latest = await asyncio.to_thread(mem.latest)
            return ToolResult(ok=True, output={
                "captures": captures,
                "duration_seconds": round(_time.monotonic() - start, 1),
                "final_context": latest.inferred_context if latest else "unknown",
                "message": f"Captured {captures} scenes over {args.duration_seconds}s.",
            })
        except Exception as e:  # noqa: BLE001
            return ToolResult(ok=False, error=f"vision_watch failed: {e}")


__all__ = [
    "VisionCaptureTool",
    "VisionSceneTool",
    "VisionDiffTool",
    "VisionMemoryTool",
    "VisionDeepTool",
    "VisionWatchTool",
]
