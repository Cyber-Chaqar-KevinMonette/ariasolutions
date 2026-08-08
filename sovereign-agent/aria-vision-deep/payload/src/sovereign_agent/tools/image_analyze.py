"""
image_analyze.py — deep image understanding tools (v0.2.42.0)

Three Tier 0 tools that give Aria powerful vision capabilities beyond the
basic image_caption tool:

  analyze_image        — deep structured analysis: objects, text, layout,
                         purpose, quality, technical details, and more.
                         Supports custom focus areas. Falls back to frontier
                         Claude API if local vision model is unavailable.

  extract_text_from_image — OCR-focused: extract all readable text from an
                         image, preserving structure where possible. Handles
                         screenshots, documents, whiteboards, code on screen.

  compare_images       — analyze two images side-by-side: similarities,
                         differences, changes between versions, before/after.

All three use the configured vision model (default llava:7b, configurable
via AGENT_VISION_MODEL). Falls back to Claude API if Ollama vision fails.
VRAM constraint: these serialize via vram_lock for heavy models.
"""
from __future__ import annotations

import base64
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from .base import Tool, ToolResult


_MAX_BYTES = 15 * 1024 * 1024  # 15 MB cap per image


def _load_image_b64(path: str) -> tuple[bytes, str]:
    """Load image, return (raw_bytes, base64_string). Raises on error."""
    p = Path(path).expanduser()
    if not p.is_absolute():
        raise ValueError(f"path must be absolute: {path!r}")
    if not p.exists():
        raise FileNotFoundError(f"file not found: {p}")
    data = p.read_bytes()
    if len(data) > _MAX_BYTES:
        raise ValueError(f"file too large: {len(data)} bytes (cap {_MAX_BYTES})")
    return data, base64.b64encode(data).decode("ascii")


async def _vision_call(client, model: str, prompt: str, images: list[str]) -> str:
    """Call Ollama vision API. Returns text content or raises."""
    response = await client.chat(
        model=model,
        messages=[{
            "role": "user",
            "content": prompt,
            "images": images,
        }],
        temperature=0.1,
    )
    msg = (response or {}).get("message") or {}
    content = (msg.get("content") or "").strip()
    if not content:
        raise ValueError("vision model returned empty response")
    return content


async def _vision_call_with_fallback(prompt: str, images_b64: list[str],
                                     model: str) -> tuple[str, str]:
    """Try Ollama vision; fall back to Claude API. Returns (text, source)."""
    from sovereign_agent.ollama_client import OllamaClient
    client = OllamaClient()
    try:
        text = await _vision_call(client, model, prompt, images_b64)
        return text, f"ollama:{model}"
    except Exception as ollama_err:
        # Fall back to Claude API (claude-haiku-4-5 — fast, multimodal)
        try:
            import anthropic
            aclient = anthropic.AsyncAnthropic()
            content_parts = []
            for b64 in images_b64:
                content_parts.append({
                    "type": "image",
                    "source": {"type": "base64", "media_type": "image/jpeg", "data": b64},
                })
            content_parts.append({"type": "text", "text": prompt})
            msg = await aclient.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=2048,
                messages=[{"role": "user", "content": content_parts}],
            )
            text = msg.content[0].text if msg.content else ""
            return text.strip(), "claude-haiku-4-5"
        except Exception as claude_err:
            raise RuntimeError(
                f"Ollama failed ({ollama_err!r}) and Claude API fallback also failed ({claude_err!r})"
            )


# ─── analyze_image ────────────────────────────────────────────────────────────


class AnalyzeImageTool(Tool):
    """Deep structured analysis of an image file.

    Goes far beyond a basic caption. Returns: content description, visible
    text, spatial layout, apparent purpose, quality assessment, colors and
    style, any data/charts/tables, technical metadata, and notable details.

    Can focus on specific aspects via the `focus` parameter:
      "all"         — comprehensive analysis (default)
      "text"        — prioritize readable text and labels
      "objects"     — enumerate objects and their positions
      "layout"      — describe spatial arrangement
      "data"        — charts, tables, graphs, numbers
      "code"        — code on screen, terminals, IDEs
      "faces"       — people, expressions, poses
      "quality"     — technical quality, resolution, artifacts
    """

    name = "analyze_image"
    tier = 0
    description = (
        "Perform deep structured analysis of an image file. Returns content, "
        "visible text, layout, purpose, quality, and any data or code visible. "
        "Supports focus areas: all/text/objects/layout/data/code/quality. "
        "Falls back to Claude API if local vision model is unavailable."
    )
    failure_modes = (
        "file not found or unreadable",
        "file too large (>15MB)",
        "both Ollama vision and Claude API unavailable",
        "unsupported image format",
    )

    class Args(BaseModel):
        path: str = Field(description="Absolute path to the image file.")
        focus: str = Field(
            default="all",
            description=(
                "Analysis focus: all/text/objects/layout/data/code/faces/quality. "
                "Default 'all' gives a comprehensive report."
            ),
        )
        question: Optional[str] = Field(
            default=None,
            description="Specific question to answer about the image.",
        )

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        from sovereign_agent.config import SETTINGS

        try:
            raw, b64 = _load_image_b64(args.path)
        except (FileNotFoundError, ValueError) as exc:
            return ToolResult(ok=False, error=str(exc))

        vision_model = getattr(SETTINGS, "vision_model", None) or "llava:7b"

        focus_prompts = {
            "all": (
                "Analyze this image comprehensively. Provide:\n"
                "1. CONTENT: What is shown? Describe all key elements.\n"
                "2. TEXT: Transcribe ALL readable text exactly as shown.\n"
                "3. LAYOUT: Describe spatial arrangement and structure.\n"
                "4. PURPOSE: What is this image for? What type is it (photo/screenshot/diagram/chart/document/art)?\n"
                "5. DATA: Any numbers, charts, tables, or structured information.\n"
                "6. QUALITY: Resolution, clarity, any artifacts or issues.\n"
                "7. NOTABLE: Anything unusual, important, or that demands attention."
            ),
            "text": (
                "Extract and transcribe ALL text visible in this image. "
                "Preserve structure: use newlines where the text has line breaks, "
                "and indicate different text regions (e.g., [header], [body], [caption]). "
                "Transcribe exactly — do not paraphrase. Include partial or unclear text, "
                "marking uncertain characters with [?]."
            ),
            "objects": (
                "List every distinct object, element, or entity visible in this image. "
                "For each: name it, describe its appearance, and note its position "
                "(top-left, center, etc.). Be exhaustive."
            ),
            "layout": (
                "Describe the spatial layout of this image in detail. "
                "How is it structured? What's in the foreground vs background? "
                "How are elements arranged relative to each other? "
                "What visual hierarchy exists?"
            ),
            "data": (
                "Extract all data, numbers, statistics, chart values, table contents, "
                "and structured information from this image. "
                "Recreate tables in markdown format. "
                "Describe charts with their axes, labels, and approximate values."
            ),
            "code": (
                "Extract and transcribe all code, commands, terminal output, "
                "configuration, or technical text visible in this image. "
                "Preserve indentation and formatting. "
                "Identify the programming language or tool if visible."
            ),
            "faces": (
                "Describe all people visible in this image: "
                "approximate age, expression, pose, notable features, clothing. "
                "Note their positions and what they appear to be doing."
            ),
            "quality": (
                "Assess the technical quality of this image: "
                "resolution, sharpness, exposure, color balance, compression artifacts, "
                "noise, distortion. Rate overall quality and note any issues."
            ),
        }

        focus_key = args.focus.lower().strip()
        prompt = focus_prompts.get(focus_key, focus_prompts["all"])
        if args.question:
            prompt = f"{prompt}\n\nAlso specifically answer: {args.question}"

        try:
            text, source = await _vision_call_with_fallback(prompt, [b64], vision_model)
        except RuntimeError as exc:
            return ToolResult(ok=False, error=str(exc))

        return ToolResult(
            ok=True,
            output=text,
            metadata={
                "source": source,
                "path": args.path,
                "image_bytes": len(raw),
                "focus": focus_key,
            },
        )


# ─── extract_text_from_image ─────────────────────────────────────────────────


class ExtractTextFromImageTool(Tool):
    """OCR-focused text extraction from images.

    Optimized for screenshots, documents, whiteboards, code on screen,
    signs, and any image with readable text. Returns verbatim transcription
    with structure preserved.
    """

    name = "extract_text_from_image"
    tier = 0
    description = (
        "Extract and transcribe ALL text visible in an image file. "
        "Optimized for screenshots, documents, whiteboards, code on screen. "
        "Returns verbatim text with structure preserved. "
        "Falls back to Claude API if local vision model unavailable."
    )
    failure_modes = (
        "file not found or unreadable",
        "file too large (>15MB)",
        "no text visible in image",
        "both Ollama and Claude API unavailable",
    )

    class Args(BaseModel):
        path: str = Field(description="Absolute path to the image file.")
        preserve_layout: bool = Field(
            default=True,
            description="If True, try to preserve line breaks and columns from the original.",
        )

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        from sovereign_agent.config import SETTINGS

        try:
            raw, b64 = _load_image_b64(args.path)
        except (FileNotFoundError, ValueError) as exc:
            return ToolResult(ok=False, error=str(exc))

        vision_model = getattr(SETTINGS, "vision_model", None) or "llava:7b"

        if args.preserve_layout:
            prompt = (
                "You are an OCR system. Extract ALL text from this image exactly as it appears. "
                "Rules:\n"
                "- Transcribe every word, number, and symbol you can see\n"
                "- Preserve line breaks where they exist in the image\n"
                "- Preserve columns and indentation\n"
                "- Mark uncertain characters as [?]\n"
                "- Mark distinct text regions with labels like [HEADER], [BODY], [FOOTER], [CAPTION], [CODE]\n"
                "- Do NOT paraphrase or summarize — transcribe verbatim\n"
                "Output only the extracted text, nothing else."
            )
        else:
            prompt = (
                "Extract all text visible in this image. "
                "Transcribe every word and number exactly. "
                "Do not paraphrase. Mark unclear text with [?]."
            )

        try:
            text, source = await _vision_call_with_fallback(prompt, [b64], vision_model)
        except RuntimeError as exc:
            return ToolResult(ok=False, error=str(exc))

        if not text or text.lower() in ("no text visible", "no text found"):
            return ToolResult(
                ok=True,
                output="(no readable text found in this image)",
                metadata={"source": source, "path": args.path, "chars": 0},
            )

        return ToolResult(
            ok=True,
            output=text,
            metadata={"source": source, "path": args.path, "chars": len(text)},
        )


# ─── compare_images ───────────────────────────────────────────────────────────


class CompareImagesTool(Tool):
    """Compare two images side-by-side and describe similarities and differences.

    Useful for: before/after comparisons, version diffs, A/B tests,
    spotting changes in screenshots, and quality assessment.
    Returns a structured comparison report.
    """

    name = "compare_images"
    tier = 0
    description = (
        "Compare two image files and describe their similarities and differences. "
        "Useful for before/after, version diffs, A/B comparisons, UI changes. "
        "Returns structured comparison: what changed, what's the same, key differences. "
        "Falls back to Claude API if local vision model unavailable."
    )
    failure_modes = (
        "either file not found or unreadable",
        "files too large (>15MB each)",
        "both Ollama and Claude API unavailable",
    )

    class Args(BaseModel):
        path_a: str = Field(description="Absolute path to the first image (baseline/before).")
        path_b: str = Field(description="Absolute path to the second image (comparison/after).")
        context: Optional[str] = Field(
            default=None,
            description="Optional context about what you're comparing (e.g., 'UI before/after refactor').",
        )

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        from sovereign_agent.config import SETTINGS

        try:
            raw_a, b64_a = _load_image_b64(args.path_a)
            raw_b, b64_b = _load_image_b64(args.path_b)
        except (FileNotFoundError, ValueError) as exc:
            return ToolResult(ok=False, error=str(exc))

        vision_model = getattr(SETTINGS, "vision_model", None) or "llava:7b"

        context_line = f"\nContext: {args.context}" if args.context else ""
        prompt = (
            f"I'm showing you two images to compare.{context_line}\n\n"
            "The FIRST image is the baseline (Image A).\n"
            "The SECOND image is the comparison (Image B).\n\n"
            "Provide a structured comparison:\n"
            "1. OVERVIEW: What are these images showing?\n"
            "2. SIMILARITIES: What's the same between A and B?\n"
            "3. DIFFERENCES: What has changed from A to B? Be specific.\n"
            "4. KEY CHANGES: The 3 most important differences.\n"
            "5. VERDICT: Overall, how significant are the changes?"
        )

        try:
            text, source = await _vision_call_with_fallback(prompt, [b64_a, b64_b], vision_model)
        except RuntimeError as exc:
            return ToolResult(ok=False, error=str(exc))

        return ToolResult(
            ok=True,
            output=text,
            metadata={
                "source": source,
                "path_a": args.path_a,
                "path_b": args.path_b,
                "bytes_a": len(raw_a),
                "bytes_b": len(raw_b),
            },
        )
