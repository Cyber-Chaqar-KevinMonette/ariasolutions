"""Inventory planner: for each matching file in a directory tree, generate
one step that asks the agent to read it and write a summary line per file
into an output file. The classic re-trigger use case — Genesis-Seeds-style
corpus distillation broken into atomic units the model can complete in
seconds.

v0.2.6 additions (all backward compatible):

- ``exclude``: list of glob patterns matched against full paths. Files
  matching ANY exclude pattern are dropped from the plan. Useful for
  skipping duplicates, build artifacts, or vendored trees.
- ``include_no_extension``: when True, also include files with no extension
  (LICENSE, NOTICE, transcripts saved without a suffix, etc.) — these
  don't match ``*.md``-style patterns but are often real prose content.
  Default False (preserves v0.2.5 behavior).
- ``max_file_size_bytes``: skip files larger than this. Defaults to 200KB,
  a safe budget for a 16K-context model with room for the prompt. Files
  exceeding the cap are reported in the plan's notes for triage.
"""
from __future__ import annotations

import fnmatch
from pathlib import Path
from typing import Any

from ..continuation import Step
from .base import PlanResult, Planner, PlannerError


class InventoryPlanner(Planner):
    name = "inventory"
    description = (
        "Read each file under <root>; append a summary line per file to <output> text file. "
        "DOES NOT write to atoms.db — use 'summaries-to-atoms' afterward, or 'read-files' "
        "for direct atomization."
    )

    def required_args(self) -> tuple[str, ...]:
        return ("root", "output")

    def plan(self, **kwargs: Any) -> PlanResult:
        root_arg = kwargs.get("root")
        output_arg = kwargs.get("output")
        patterns = kwargs.get("patterns") or ["*.md", "*.txt", "*.rst", "*.py"]
        excludes = list(kwargs.get("exclude") or [])
        max_files = int(kwargs.get("max_files") or 0)  # 0 = unbounded
        recursive = bool(kwargs.get("recursive", True))
        include_no_ext = bool(kwargs.get("include_no_extension", False))
        max_size = int(kwargs.get("max_file_size_bytes") or 200_000)

        if not root_arg:
            raise PlannerError("inventory: 'root' is required (directory to walk)")
        if not output_arg:
            raise PlannerError("inventory: 'output' is required (file to write into)")

        root = Path(str(root_arg)).expanduser().resolve()
        output = Path(str(output_arg)).expanduser().resolve()

        if not root.exists():
            raise PlannerError(f"inventory: root path does not exist: {root}")
        if not root.is_dir():
            raise PlannerError(f"inventory: root must be a directory: {root}")

        files = self._walk(root, patterns, recursive, include_no_ext)

        # Apply excludes (post-walk so they're easy to debug).
        if excludes:
            files = [f for f in files if not _any_match(str(f), excludes)]

        # Filter by size — record the oversized ones for the operator.
        oversized: list[Path] = []
        sized_files: list[Path] = []
        for f in files:
            try:
                if f.stat().st_size > max_size:
                    oversized.append(f)
                else:
                    sized_files.append(f)
            except OSError:
                # Unreadable / vanished file → skip silently
                continue
        files = sized_files

        if max_files > 0:
            files = files[:max_files]

        if not files:
            raise PlannerError(
                f"inventory: no files matched patterns {patterns} under {root}"
                + (f" (after excludes={excludes})" if excludes else "")
                + (f" (skipped {len(oversized)} oversized)" if oversized else "")
            )

        steps = [
            Step(
                id=i,
                kind="inventory_file",
                args={"path": str(p), "output": str(output)},
                required_model="orchestrator",
            )
            for i, p in enumerate(files)
        ]
        notes_parts = [f"patterns={patterns}", f"recursive={recursive}"]
        if excludes:
            notes_parts.append(f"excludes={excludes}")
        if include_no_ext:
            notes_parts.append("include_no_extension=True")
        if oversized:
            notes_parts.append(f"skipped_oversized={len(oversized)}")
        return PlanResult(
            goal=f"Inventory {len(files)} files under {root} → {output}",
            steps=steps,
            output_path=str(output),
            notes=" ".join(notes_parts),
        )

    def render_step(self, step: Step, planner_args: dict) -> str:
        path = step.args.get("path", "(missing)")
        output = step.args.get("output", "(missing)")
        return (
            f"Read the file at {path}. Produce a single-line summary "
            f"(roughly 20-40 words; one line, no preamble) describing what "
            f"the file contains and its likely purpose. Append exactly one "
            f"line to {output} in the format: '{path}: <your summary>'. "
            f"Use the write_file tool with mode='append'. Do not modify "
            f"any other file. When the line is appended, you are done."
        )

    @staticmethod
    def _walk(
        root: Path,
        patterns: list[str],
        recursive: bool,
        include_no_extension: bool,
    ) -> list[Path]:
        """Stable, deterministic file ordering."""
        seen: set[Path] = set()
        for pat in patterns:
            it = root.rglob(pat) if recursive else root.glob(pat)
            for p in it:
                if p.is_file():
                    seen.add(p.resolve())

        if include_no_extension:
            it = root.rglob("*") if recursive else root.glob("*")
            for p in it:
                if p.is_file() and not p.suffix:
                    seen.add(p.resolve())

        return sorted(seen)


def _any_match(path: str, patterns: list[str]) -> bool:
    """True if path matches any of the glob patterns."""
    return any(fnmatch.fnmatch(path, pat) for pat in patterns)
