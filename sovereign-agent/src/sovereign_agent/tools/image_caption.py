"""image_caption — Tier 0. Describes the contents of an image file.

Uses your configured vision model (default ``llava:7b``, override via
``AGENT_VISION_MODEL``) to generate a natural-language caption.

Used primarily by the ``image-inventory`` planner. Operators can also invoke
it manually via the agent loop in any mode (Tier 0 — read-only, no fs writes).

The image path must be readable on disk (no network URLs). The tool sends
the image bytes to Ollama, which dispatches to the vision model.
"""
from __future__ import annotations

import base64
from pathlib import Path

from pydantic import BaseModel, Field

from ..config import SETTINGS
from ..ollama_client import OllamaClient
from .base import Tool, ToolResult


class _Args(BaseModel):
    path: str = Field(description="Absolute path to an image file (PNG, JPEG, WebP, GIF).")
    prompt: str = Field(
        default="Describe what's in this image in 30-50 words. Mention any text, labels, "
                "or apparent purpose (diagram, photo, screenshot, chart, figure, etc.).",
        description="Caption prompt. Default asks for a concise, factual description.",
    )


class ImageCaptionTool(Tool[_Args]):
    name = "image_caption"
    tier = 0
    description = (
        "Generate a natural-language caption for an image file using the vision "
        "model. Returns a string description. FAILURE MODES: file not found; "
        "file too large for vision model; vision model not pulled; ollama "
        "unreachable; image format unsupported."
    )
    failure_modes = (
        "file_not_found",
        "file_too_large",
        "vision_model_not_pulled",
        "ollama_unreachable",
        "format_unsupported",
    )
    Args = _Args

    # Reasonable cap. Ollama's vision endpoint accepts very large images,
    # but multi-MB images bloat request payloads without improving captions.
    _MAX_BYTES = 10 * 1024 * 1024  # 10 MB

    def __init__(self, client: OllamaClient | None = None) -> None:
        self._client = client or OllamaClient()

    async def execute(self, args: _Args, *, trace_id: str) -> ToolResult:  # noqa: ARG002
        path = Path(args.path).expanduser()
        if not path.is_absolute():
            return ToolResult(
                ok=False,
                error="image_caption requires an absolute path",
            )
        if not path.exists():
            return ToolResult(ok=False, error=f"file not found: {path}")
        if not path.is_file():
            return ToolResult(ok=False, error=f"not a regular file: {path}")

        try:
            size = path.stat().st_size
        except OSError as e:
            return ToolResult(ok=False, error=f"cannot stat {path}: {e}")

        if size > self._MAX_BYTES:
            return ToolResult(
                ok=False,
                error=f"file too large: {size} bytes (cap {self._MAX_BYTES})",
            )

        try:
            data = path.read_bytes()
        except OSError as e:
            return ToolResult(ok=False, error=f"cannot read {path}: {e}")

        b64 = base64.b64encode(data).decode("ascii")
        vision_model = getattr(SETTINGS, "vision_model", None) or "llava:7b"

        try:
            response = await self._client.chat(
                model=vision_model,
                messages=[{
                    "role": "user",
                    "content": args.prompt,
                    "images": [b64],
                }],
                temperature=0.2,
            )
        except Exception as e:  # noqa: BLE001
            return ToolResult(
                ok=False,
                error=f"vision model call failed: {type(e).__name__}: {e}",
            )

        # Extract caption text from Ollama response shape.
        msg = (response or {}).get("message") or {}
        caption = (msg.get("content") or "").strip()
        if not caption:
            return ToolResult(
                ok=False,
                error="vision model returned empty caption",
            )

        return ToolResult(
            ok=True,
            output=caption,
            metadata={
                "model": vision_model,
                "image_bytes": size,
                "caption_chars": len(caption),
            },
        )
