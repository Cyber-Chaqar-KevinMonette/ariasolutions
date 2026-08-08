"""Metadata-inventory planner: for each file, record metadata (filename,
size, type, magic bytes) directly into the output file.

This planner does NOT use a model. Steps are tagged ``required_model='none'``
and the runner short-circuits them into a pure-Python action: open file →
read first bytes → write summary line. No tokens spent.

Designed for binary stragglers: MP4, ZIP, PPTX, executables, anything
where summarizing content requires specialized tooling that doesn't exist.
The metadata line is enough to know what's in the corpus and decide
whether to invest in a content-aware planner later.

Output line format:
    /path/to/file: TYPE size=N kind=DESCRIPTION

Examples:
    /path/foo.mp4: video size=4193280 kind=ISO Media (mp4)
    /path/data.zip: archive size=87642 kind=ZIP archive
    /path/slides.pptx: document size=12384 kind=Microsoft PowerPoint
"""
from __future__ import annotations

import fnmatch
from pathlib import Path
from typing import Any

from ..continuation import Step
from .base import PlanResult, Planner, PlannerError


# (magic_bytes, type_label, kind_description). Order matters — first match wins.
# Keep this small and obvious; we're not trying to be `file(1)`.
_MAGIC_TABLE: list[tuple[bytes, str, str]] = [
    (b"%PDF",                    "document", "PDF"),
    (b"PK\x03\x04",              "archive",  "ZIP / Office (docx/xlsx/pptx)"),
    (b"\x89PNG\r\n\x1a\n",       "image",    "PNG"),
    (b"\xff\xd8\xff",             "image",    "JPEG"),
    (b"GIF87a",                  "image",    "GIF87a"),
    (b"GIF89a",                  "image",    "GIF89a"),
    (b"RIFF",                    "media",    "RIFF (WAV/AVI/WebP)"),
    (b"\x00\x00\x00 ftypisom",   "video",    "ISO Media (mp4)"),
    (b"\x00\x00\x00\x18ftypmp4", "video",    "ISO Media (mp4)"),
    (b"OggS",                    "media",    "OGG"),
    (b"ID3",                     "media",    "MP3 (ID3)"),
    (b"\x1f\x8b",                "archive",  "gzip"),
    (b"BZh",                     "archive",  "bzip2"),
    (b"7z\xbc\xaf\x27\x1c",      "archive",  "7-zip"),
    (b"Rar!\x1a\x07",            "archive",  "RAR"),
]


class MetadataInventoryPlanner(Planner):
    name = "metadata-inventory"
    description = "Record filename/size/type for each file. No model invocation. Useful for binary stragglers."

    def required_args(self) -> tuple[str, ...]:
        return ("root", "output")

    def plan(self, **kwargs: Any) -> PlanResult:
        root_arg = kwargs.get("root")
        output_arg = kwargs.get("output")
        patterns = kwargs.get("patterns") or ["*"]
        excludes = list(kwargs.get("exclude") or [])
        max_files = int(kwargs.get("max_files") or 0)
        recursive = bool(kwargs.get("recursive", True))

        if not root_arg:
            raise PlannerError("metadata-inventory: 'root' is required")
        if not output_arg:
            raise PlannerError("metadata-inventory: 'output' is required")

        root = Path(str(root_arg)).expanduser().resolve()
        output = Path(str(output_arg)).expanduser().resolve()

        if not root.exists() or not root.is_dir():
            raise PlannerError(f"metadata-inventory: root not a directory: {root}")

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
                f"metadata-inventory: no files matched {patterns} under {root}"
            )

        steps = [
            Step(
                id=i,
                kind="metadata_inventory_file",
                args={"path": str(p), "output": str(output)},
                required_model="none",
            )
            for i, p in enumerate(files)
        ]
        notes = f"patterns={patterns} recursive={recursive}"
        if excludes:
            notes += f" excludes={excludes}"
        return PlanResult(
            goal=f"Metadata-inventory {len(files)} files under {root} → {output}",
            steps=steps,
            output_path=str(output),
            notes=notes,
        )

    def render_step(self, step: Step, planner_args: dict) -> str:
        # Even though this planner is model-free, render_step still produces
        # a goal string for trace logs — it's the human-readable summary of
        # what the no-model executor will do.
        path = step.args.get("path", "(missing)")
        output = step.args.get("output", "(missing)")
        return f"Record metadata for {path} → append one line to {output}."


def execute_metadata_step(step: Step) -> str:
    """Pure-Python execution of a metadata_inventory_file step.

    Called by the runner when ``step.required_model == 'none'``. Returns
    the output line that was appended (for the event log). Raises OSError
    on file IO failure — the runner converts this to a poison.
    """
    path = Path(step.args["path"])
    output = Path(step.args["output"])

    try:
        size = path.stat().st_size
    except OSError as e:
        raise OSError(f"cannot stat {path}: {e}") from None

    type_label, kind = _classify(path)
    line = f"{path}: {type_label} size={size} kind={kind}\n"

    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "a", encoding="utf-8") as f:
        f.write(line)

    return line.rstrip()


def _classify(path: Path) -> tuple[str, str]:
    """Return (type_label, kind_description) for a file. Best-effort."""
    try:
        with open(path, "rb") as f:
            head = f.read(16)
    except OSError:
        return ("unknown", f"unreadable ({path.suffix or 'no ext'})")

    for magic, type_label, kind in _MAGIC_TABLE:
        if head.startswith(magic):
            return (type_label, kind)

    # No magic match — fall back to extension.
    ext = path.suffix.lower().lstrip(".")
    if not ext:
        return ("unknown", "no extension, no recognized magic bytes")
    return ("unknown", f".{ext} (no magic match)")


def _any_match(path: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(path, pat) for pat in patterns)
