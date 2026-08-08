"""Image inventory planner: for each matching image, generate a step that
asks the vision model to describe what's in it, then writes one line
per image into an output file.

Tagged with ``required_model='vision'`` so model-affinity scheduling
batches all image steps together — your vision model loads once, processes
all images, then unloads.

This planner does NOT walk image content during planning (unlike
``pdf-inventory`` which extracts text upfront). Reason: image data lives
on disk and gets passed to the vision model at step-execution time, not
embedded into the continuation file. This keeps continuation files
small even with hundreds of images queued.

The ``--include`` flag (whitelist of subpaths) is critical for image
planning: you almost certainly DON'T want to caption personal photos in
``assets/``, only the diagrams in ``docs/`` or ``figures/``. The flag is
opt-in: omit it to scan everywhere, provide it to scope.
"""
from __future__ import annotations

import fnmatch
from pathlib import Path
from typing import Any

from ..continuation import Step
from .base import PlanResult, Planner, PlannerError


class ImageInventoryPlanner(Planner):
    name = "image-inventory"
    description = "Caption each image via the vision model; one line per image into <output>."

    def required_args(self) -> tuple[str, ...]:
        return ("root", "output")

    def plan(self, **kwargs: Any) -> PlanResult:
        root_arg = kwargs.get("root")
        output_arg = kwargs.get("output")
        patterns = kwargs.get("patterns") or ["*.png", "*.jpg", "*.jpeg", "*.webp"]
        excludes = list(kwargs.get("exclude") or [])
        includes = list(kwargs.get("include") or [])
        max_files = int(kwargs.get("max_files") or 0)
        recursive = bool(kwargs.get("recursive", True))
        max_size = int(kwargs.get("max_file_size_bytes") or 5_000_000)  # 5MB default

        if not root_arg:
            raise PlannerError("image-inventory: 'root' is required")
        if not output_arg:
            raise PlannerError("image-inventory: 'output' is required")

        root = Path(str(root_arg)).expanduser().resolve()
        output = Path(str(output_arg)).expanduser().resolve()

        if not root.exists() or not root.is_dir():
            raise PlannerError(f"image-inventory: root not a directory: {root}")

        seen: set[Path] = set()
        for pat in patterns:
            it = root.rglob(pat) if recursive else root.glob(pat)
            for p in it:
                if p.is_file():
                    seen.add(p.resolve())
        files = sorted(seen)

        # Includes (whitelist): if provided, file path MUST match at least one.
        if includes:
            files = [f for f in files if _any_match(str(f), includes)]

        # Excludes (blacklist): file path MUST NOT match any.
        if excludes:
            files = [f for f in files if not _any_match(str(f), excludes)]

        oversized: list[Path] = []
        sized: list[Path] = []
        for f in files:
            try:
                if f.stat().st_size > max_size:
                    oversized.append(f)
                else:
                    sized.append(f)
            except OSError:
                continue
        files = sized

        if max_files > 0:
            files = files[:max_files]

        if not files:
            raise PlannerError(
                f"image-inventory: no images matched {patterns} under {root}"
                + (f" (after includes={includes})" if includes else "")
                + (f" (after excludes={excludes})" if excludes else "")
                + (f" (skipped {len(oversized)} oversized)" if oversized else "")
            )

        steps = [
            Step(
                id=i,
                kind="image_inventory_file",
                args={"path": str(p), "output": str(output)},
                required_model="vision",
            )
            for i, p in enumerate(files)
        ]
        notes = f"patterns={patterns} recursive={recursive}"
        if includes:
            notes += f" includes={includes}"
        if excludes:
            notes += f" excludes={excludes}"
        if oversized:
            notes += f" skipped_oversized={len(oversized)}"
        return PlanResult(
            goal=f"Image-inventory {len(files)} images under {root} → {output}",
            steps=steps,
            output_path=str(output),
            notes=notes,
        )

    def render_step(self, step: Step, planner_args: dict) -> str:
        path = step.args.get("path", "(missing)")
        output = step.args.get("output", "(missing)")
        # The vision-capable path uses image_caption tool which the runner
        # provides when required_model='vision'. The agent loop wires this
        # at dispatch time. We instruct the agent to use it explicitly so
        # it doesn't try to read_file the binary.
        return (
            f"Caption the image at {path}. Use the image_caption tool "
            f"(do NOT use read_file — the file is binary). Produce a single-line "
            f"description (roughly 20-40 words) covering: what's visible, any "
            f"text or labels, and the apparent purpose (diagram, photo, screenshot, "
            f"chart, etc). Append exactly one line to {output} in the format: "
            f"'{path}: <your description>'. Use the write_file tool with "
            f"mode='append'. When the line is appended, you are done."
        )


def _any_match(path: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(path, pat) for pat in patterns)
