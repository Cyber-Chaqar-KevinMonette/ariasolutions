"""Read-files planner: for each matching file, ask the agent to read it
and write a memory atom. Simpler than inventory — no aggregation file,
result lives in atoms.db. Useful for corpus ingestion into hybrid retrieval.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ..continuation import Step
from .base import PlanResult, Planner, PlannerError


class ReadFilesPlanner(Planner):
    name = "read-files"
    description = "Read each matching file and write a memory atom for it."

    def required_args(self) -> tuple[str, ...]:
        return ("root",)

    def plan(self, **kwargs: Any) -> PlanResult:
        root_arg = kwargs.get("root")
        patterns = kwargs.get("patterns") or ["*.md", "*.txt"]
        max_files = int(kwargs.get("max_files") or 0)
        recursive = bool(kwargs.get("recursive", True))
        topic_tag = str(kwargs.get("tag") or "ingest")

        if not root_arg:
            raise PlannerError("read-files: 'root' is required")

        root = Path(str(root_arg)).expanduser().resolve()
        if not root.exists() or not root.is_dir():
            raise PlannerError(f"read-files: root not a directory: {root}")

        seen: set[Path] = set()
        for pat in patterns:
            it = root.rglob(pat) if recursive else root.glob(pat)
            for p in it:
                if p.is_file():
                    seen.add(p.resolve())
        files = sorted(seen)
        if max_files > 0:
            files = files[:max_files]
        if not files:
            raise PlannerError(
                f"read-files: no files matched {patterns} under {root}"
            )

        steps = [
            Step(
                id=i,
                kind="read_and_remember",
                args={"path": str(p), "tag": topic_tag},
            )
            for i, p in enumerate(files)
        ]
        return PlanResult(
            goal=f"Read {len(files)} files under {root} into memory (tag={topic_tag!r})",
            steps=steps,
            notes=f"patterns={patterns} recursive={recursive}",
        )

    def render_step(self, step: Step, planner_args: dict) -> str:
        path = step.args.get("path", "(missing)")
        tag = step.args.get("tag", "ingest")
        return (
            f"Read the file at {path}. Identify its topic and 2-4 key "
            f"claims or facts. Write a single memory atom via memory_write "
            f"that captures the topic, the key claims, and a confidence "
            f"score (0.0-1.0). Tag the atom with '{tag}'. When the atom is "
            f"written, you are done. Do not modify any file."
        )
