"""PDF inventory planner: for each PDF, generate a step that extracts text
from the PDF (via pdftotext or pypdf), then summarizes.

The agent is given the EXTRACTED TEXT in the goal string, not the path to
the PDF. This is intentional: the agent's read_file tool can't parse PDF
binary, so we extract upfront in pure Python during planning, and the model
sees only the resulting plain text.

Trade-off: the continuation file becomes larger because each step's args
contain the extracted text. For typical research PDFs (10-50KB of extracted
text per file), this is fine. For multi-hundred-page PDFs, the planner
truncates extraction to ``max_extract_chars`` (default 40000, ~10K tokens).

Skipped:
  - encrypted PDFs (extraction returns nothing)
  - image-only / scanned PDFs (no embedded text)
  - PDFs that fail extraction for any reason

Skipped PDFs are reported in the plan's notes; the operator can re-process
them later with an OCR pass (not shipped in v0.2.6 — out of scope).
"""
from __future__ import annotations

import fnmatch
import shutil
import subprocess
from pathlib import Path
from typing import Any

from ..continuation import Step
from .base import PlanResult, Planner, PlannerError


# Sentinel: extraction succeeded but produced empty text → skip
_EMPTY_EXTRACTION = ""


class PdfInventoryPlanner(Planner):
    name = "pdf-inventory"
    description = "Extract text from each PDF, summarize one line per PDF into <output>."

    def required_args(self) -> tuple[str, ...]:
        return ("root", "output")

    def plan(self, **kwargs: Any) -> PlanResult:
        root_arg = kwargs.get("root")
        output_arg = kwargs.get("output")
        patterns = kwargs.get("patterns") or ["*.pdf", "*.PDF"]
        excludes = list(kwargs.get("exclude") or [])
        max_files = int(kwargs.get("max_files") or 0)
        recursive = bool(kwargs.get("recursive", True))
        max_extract_chars = int(kwargs.get("max_extract_chars") or 40_000)

        if not root_arg:
            raise PlannerError("pdf-inventory: 'root' is required")
        if not output_arg:
            raise PlannerError("pdf-inventory: 'output' is required")

        root = Path(str(root_arg)).expanduser().resolve()
        output = Path(str(output_arg)).expanduser().resolve()

        if not root.exists() or not root.is_dir():
            raise PlannerError(f"pdf-inventory: root not a directory: {root}")

        # Choose extractor — pdftotext (poppler) preferred; fallback to pypdf.
        if shutil.which("pdftotext"):
            extractor = "pdftotext"
        else:
            try:
                import pypdf  # noqa: F401
                extractor = "pypdf"
            except ImportError:
                raise PlannerError(
                    "pdf-inventory: no PDF extractor available. Install with "
                    "'sudo apt install poppler-utils' (recommended) "
                    "or 'uv pip install pypdf' inside the sovereign-agent venv."
                )

        seen: set[Path] = set()
        for pat in patterns:
            it = root.rglob(pat) if recursive else root.glob(pat)
            for p in it:
                if p.is_file():
                    seen.add(p.resolve())
        files = sorted(seen)

        if excludes:
            files = [f for f in files if not _any_match(str(f), excludes)]

        if max_files > 0:
            files = files[:max_files]

        if not files:
            raise PlannerError(
                f"pdf-inventory: no PDFs matched {patterns} under {root}"
            )

        steps: list[Step] = []
        skipped: list[tuple[Path, str]] = []
        for i, p in enumerate(files):
            text = _extract(p, extractor, max_extract_chars)
            if text == _EMPTY_EXTRACTION:
                skipped.append((p, "no extractable text (image-only or encrypted?)"))
                continue
            steps.append(Step(
                id=len(steps),
                kind="pdf_inventory_file",
                args={
                    "path": str(p),
                    "output": str(output),
                    "extracted_text": text,
                    "extracted_via": extractor,
                },
                required_model="orchestrator",
            ))

        if not steps:
            raise PlannerError(
                f"pdf-inventory: extracted no text from any of {len(files)} PDFs. "
                f"They may all be image-only / scanned. OCR is not yet supported."
            )

        notes_parts = [f"extractor={extractor}", f"max_extract_chars={max_extract_chars}"]
        if excludes:
            notes_parts.append(f"excludes={excludes}")
        if skipped:
            skipped_names = ", ".join(p.name for p, _ in skipped[:5])
            tail = f" (+{len(skipped) - 5} more)" if len(skipped) > 5 else ""
            notes_parts.append(f"skipped={len(skipped)}: {skipped_names}{tail}")

        return PlanResult(
            goal=f"PDF-inventory {len(steps)}/{len(files)} PDFs under {root} → {output}",
            steps=steps,
            output_path=str(output),
            notes=" ".join(notes_parts),
        )

    def render_step(self, step: Step, planner_args: dict) -> str:
        path = step.args.get("path", "(missing)")
        output = step.args.get("output", "(missing)")
        text = step.args.get("extracted_text", "")
        # Embed the extracted text directly into the goal — the agent
        # doesn't need to call read_file. It just summarizes what it sees.
        return (
            f"Below is text extracted from a PDF located at {path}. Read it, "
            f"then produce a single-line summary (roughly 25-50 words; one line, "
            f"no preamble) describing the PDF's topic and likely purpose. "
            f"Append exactly one line to {output} in the format: "
            f"'{path}: <your summary>'. Use the write_file tool with mode='append'. "
            f"Do not modify any other file.\n\n"
            f"---BEGIN PDF TEXT---\n{text}\n---END PDF TEXT---"
        )


def _extract(path: Path, extractor: str, max_chars: int) -> str:
    """Extract text from a PDF. Returns empty string on failure (NOT exception)."""
    try:
        if extractor == "pdftotext":
            result = subprocess.run(
                ["pdftotext", "-layout", "-q", str(path), "-"],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode != 0:
                return _EMPTY_EXTRACTION
            text = result.stdout
        elif extractor == "pypdf":
            import pypdf
            with open(path, "rb") as f:
                reader = pypdf.PdfReader(f)
                if reader.is_encrypted:
                    return _EMPTY_EXTRACTION
                parts: list[str] = []
                for page in reader.pages:
                    try:
                        parts.append(page.extract_text() or "")
                    except Exception:  # noqa: BLE001
                        continue
                text = "\n".join(parts)
        else:
            return _EMPTY_EXTRACTION
    except (subprocess.TimeoutExpired, OSError, Exception):  # noqa: BLE001
        return _EMPTY_EXTRACTION

    text = (text or "").strip()
    if not text:
        return _EMPTY_EXTRACTION
    if len(text) > max_chars:
        text = text[:max_chars] + f"\n\n[TRUNCATED — original was {len(text)} chars]"
    return text


def _any_match(path: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(path, pat) for pat in patterns)
