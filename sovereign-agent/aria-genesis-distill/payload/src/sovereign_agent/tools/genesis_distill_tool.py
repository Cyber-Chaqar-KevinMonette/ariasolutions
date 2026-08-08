"""tools/genesis_distill_tool.py — Continuable Genesis-Seeds distillation engine.

The Genesis-Seeds corpus (~1,557 files) holds the buildable lego blocks for the
Non-Classical Layer: formulas, derivatives, falsifiability protocols, the node
model, the bridge topology. This tool makes distilling them repeatable and
Aria-owned: inventory a sub-area, or read a specific text file's content so the
model can synthesize it into the distilled/ record and into atoms.

Honest frame (Kevin's): the corpus is quantum-INSPIRED multi-agent architecture —
a numpy/QuTiP design language, not physics, not a consciousness claim.

Tier 1: read-only over the corpus; the only write is an optional inventory file
under Genesis-Seeds/distilled/. Binary files (pdf/docx/png/ipynb) are listed but
not parsed here — they are flagged for a deeper pass.

FAILURE MODES: not_found, read_error, write_error
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from .base import Tool, ToolResult

# Text extensions we can distill directly; everything else is listed-only.
_TEXT_EXTS = frozenset({".md", ".txt", ".py", ".json", ".tex", ".csv", ".yaml", ".yml", ".gd", ".cff"})
_BINARY_EXTS = frozenset({".pdf", ".docx", ".png", ".jpg", ".jpeg", ".zip", ".ipynb"})
_MAX_READ_BYTES = 200_000


def _genesis_root() -> Path:
    """Resolve the Genesis-Seeds corpus root (env override, else sibling of repo)."""
    env = os.environ.get("GENESIS_SEEDS_DIR")
    if env:
        return Path(env).expanduser()
    # Default: ~/AA-Erebo/Genesis-Seeds (sibling of the sovereign-agent repo)
    return Path.home() / "AA-Erebo" / "Genesis-Seeds"


def _purpose_hint(path: Path) -> str:
    """Cheap one-line purpose hint from a text file's first non-empty lines."""
    if path.suffix.lower() not in _TEXT_EXTS:
        return ""
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as f:
            for _ in range(8):
                line = f.readline()
                if not line:
                    break
                s = line.strip().lstrip("#/*-\" ").strip()
                if len(s) > 12:
                    return s[:120]
    except Exception:
        return ""
    return ""


class GenesisDistillTool(Tool):
    """Inventory or read the Genesis-Seeds corpus for distillation.

    Args:
      area: relative sub-path under Genesis-Seeds (default "" = whole tree).
      mode: "inventory" (list files + purpose hints, text vs binary) or
            "read" (return the text content of `area` when it is a single file).
      write_inventory: if True (inventory mode), also write the listing to
            Genesis-Seeds/distilled/inventory_<area>.md.

    FAILURE MODES: not_found, read_error, write_error
    """

    name = "genesis_distill"
    tier = 1
    description = (
        "Distill the Genesis-Seeds research corpus. mode='inventory' lists files "
        "in an area with purpose hints (text vs binary); mode='read' returns a single "
        "text file's content for synthesis. area is a path relative to Genesis-Seeds. "
        "Binary files (pdf/docx/ipynb) are flagged for a deeper pass, not parsed. "
        "FAILURE MODES: not_found, read_error, write_error"
    )
    failure_modes = ("not_found", "read_error", "write_error")

    class Args(BaseModel):
        area: str = Field(default="", description="Path relative to Genesis-Seeds (file or dir).")
        mode: str = Field(default="inventory", description="inventory | read")
        write_inventory: bool = Field(default=False, description="Write inventory to distilled/.")

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        root = _genesis_root()
        if not root.exists():
            return ToolResult(ok=False, error=f"not_found: Genesis-Seeds root {root} does not exist")

        # Resolve target safely inside the corpus (no path escape).
        target = (root / args.area).resolve()
        try:
            target.relative_to(root.resolve())
        except ValueError:
            return ToolResult(ok=False, error=f"not_found: {args.area!r} escapes the corpus root")
        if not target.exists():
            return ToolResult(ok=False, error=f"not_found: {args.area!r} not under {root}")

        if args.mode == "read":
            if not target.is_file():
                return ToolResult(ok=False, error=f"read_error: {args.area!r} is not a file")
            if target.suffix.lower() not in _TEXT_EXTS:
                return ToolResult(
                    ok=False,
                    error=f"read_error: {target.suffix} is binary — flag for deeper pass, not readable here",
                )
            try:
                data = target.read_text(encoding="utf-8", errors="ignore")[:_MAX_READ_BYTES]
            except Exception as exc:
                return ToolResult(ok=False, error=f"read_error: {exc!r}")
            return ToolResult(
                ok=True,
                output={"path": str(target.relative_to(root)), "bytes": len(data), "content": data},
                metadata={"source": "genesis_distill", "mode": "read"},
            )

        # inventory mode
        files = [target] if target.is_file() else sorted(p for p in target.rglob("*") if p.is_file())
        text_files, binary_files = [], []
        for p in files:
            ext = p.suffix.lower()
            rec = {"path": str(p.relative_to(root)), "ext": ext, "bytes": p.stat().st_size}
            if ext in _BINARY_EXTS:
                binary_files.append(rec)
            elif ext in _TEXT_EXTS:
                rec["hint"] = _purpose_hint(p)
                text_files.append(rec)
            else:
                binary_files.append(rec)

        written_to = None
        if args.write_inventory:
            try:
                out_dir = root / "distilled"
                out_dir.mkdir(parents=True, exist_ok=True)
                safe = (args.area or "all").replace("/", "_") or "all"
                out_path = out_dir / f"inventory_{safe}.md"
                lines = [f"# Inventory: {args.area or '(whole corpus)'}", ""]
                lines.append(f"Text files: {len(text_files)} · Binary/deferred: {len(binary_files)}")
                lines.append("")
                lines.append("## Text (distillable)")
                for r in text_files:
                    lines.append(f"- `{r['path']}` ({r['bytes']}b) — {r.get('hint','')}")
                lines.append("")
                lines.append("## Binary / deferred (need deeper pass)")
                for r in binary_files:
                    lines.append(f"- `{r['path']}` ({r['bytes']}b) [{r['ext']}]")
                out_path.write_text("\n".join(lines), encoding="utf-8")
                written_to = str(out_path.relative_to(root))
            except Exception as exc:
                return ToolResult(ok=False, error=f"write_error: {exc!r}")

        return ToolResult(
            ok=True,
            output={
                "area": args.area or "(whole corpus)",
                "text_count": len(text_files),
                "binary_count": len(binary_files),
                "text_files": text_files[:200],
                "binary_files": binary_files[:200],
                "written_to": written_to,
            },
            metadata={"source": "genesis_distill", "mode": "inventory"},
        )
