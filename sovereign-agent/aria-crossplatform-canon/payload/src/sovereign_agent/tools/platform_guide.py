"""tools/platform_guide.py — god-tier cross-platform knowledge, retrievable.

Keys round K7. Honest architecture for an 8B local vessel: "knowledge" =
a curated, dense, retrieval-shaped canon (knowledge/crossplatform/*.md —
Linux, Windows, macOS, Mobile, the eternal traps, and the
PLATFORM_STANDARDS checklist she holds her own designs to) + this tool to
pull the relevant sections on demand. The canon also feeds gather_corpus,
so her own trained mind grows on it.

Retrieval is transparent keyword scoring over ## sections — predictable,
inspectable, no embedding dependency for a T0 read.
"""
from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel, Field

from .base import Tool, ToolResult

_CANON_FILES = {
    "linux": "linux.md",
    "windows": "windows.md",
    "macos": "macos.md",
    "mobile": "mobile.md",
    "traps": "eternal_traps.md",
    "standards": "PLATFORM_STANDARDS.md",
}
_ALIASES = {
    "mac": "macos", "osx": "macos", "darwin": "macos",
    "win": "windows", "win32": "windows",
    "ios": "mobile", "android": "mobile",
    "all": "traps", "any": "traps", "general": "traps",
    "checklist": "standards", "standard": "standards",
}


def _canon_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "knowledge" / "crossplatform"


def _split_sections(text: str) -> list[tuple[str, str]]:
    parts = re.split(r"^(## .+)$", text, flags=re.MULTILINE)
    out: list[tuple[str, str]] = []
    if parts and parts[0].strip():
        out.append(("(intro)", parts[0].strip()))
    for i in range(1, len(parts), 2):
        body = parts[i + 1] if i + 1 < len(parts) else ""
        out.append((parts[i].strip("# ").strip(), (parts[i] + body).strip()))
    return out


class PlatformGuideTool(Tool):
    """Retrieve the relevant cross-platform engineering canon section(s).

    FAILURE MODES: unknown_platform, canon_missing
    """

    name = "platform_guide"
    tier = 0
    description = (
        "Retrieve curated cross-platform engineering knowledge. platform: "
        "linux | windows | macos | mobile | traps (cross-platform pitfalls) "
        "| standards (the god-tier checklist). topic: optional keywords to "
        "select the most relevant sections (e.g. 'service daemon', 'paths "
        "encoding', 'packaging signing'). "
        "FAILURE MODES: unknown_platform, canon_missing"
    )
    failure_modes = ("unknown_platform", "canon_missing")

    class Args(BaseModel):
        platform: str = Field(..., description="linux|windows|macos|mobile|traps|standards")
        topic: str = Field("", description="Optional keywords to focus the retrieval.")

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        key = args.platform.strip().lower()
        key = _ALIASES.get(key, key)
        fname = _CANON_FILES.get(key)
        if fname is None:
            return ToolResult(
                ok=False,
                error=f"unknown_platform: {args.platform!r} — "
                      f"use one of {sorted(_CANON_FILES)}",
            )
        path = _canon_dir() / fname
        if not path.is_file():
            return ToolResult(ok=False, error=f"canon_missing: {path}")
        text = path.read_text(encoding="utf-8")

        if not args.topic.strip():
            return ToolResult(ok=True, output=text[:6000],
                              metadata={"platform": key, "sections": "all"})

        words = [w for w in re.findall(r"\w+", args.topic.lower()) if len(w) > 2]
        scored = []
        for title, body in _split_sections(text):
            low = body.lower()
            score = sum(low.count(w) for w in words)
            if score:
                scored.append((score, title, body))
        scored.sort(reverse=True)
        if not scored:
            return ToolResult(ok=True, output=text[:6000],
                              metadata={"platform": key,
                                        "sections": "all (no topic match)"})
        picked = scored[:2]
        return ToolResult(
            ok=True,
            output="\n\n".join(body for _, _, body in picked)[:6000],
            metadata={"platform": key,
                      "sections": [t for _, t, _ in picked]},
        )
