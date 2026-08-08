"""Code inventory planner: for each matching code/data file, generate a
step that asks the agent to summarize what it does (not what's in it).

Different from the prose ``inventory`` planner because the prompt frames
the file as code/data: the agent is asked for purpose, main functions,
inputs/outputs — not a paraphrase of the contents.

Tagged with ``required_model='coder'`` so model-affinity scheduling can
batch all code steps together. Your config's ``coder_model`` (e.g.
``qwen2.5-coder``) handles these efficiently.

Skips files larger than ``max_file_size_bytes`` (default 100KB — code
files are usually smaller than prose, and the model's tokenization of
code uses more tokens per byte than prose).
"""
from __future__ import annotations

import fnmatch
from pathlib import Path
from typing import Any

from ..continuation import Step
from .base import PlanResult, Planner, PlannerError


class CodeInventoryPlanner(Planner):
    name = "code-inventory"
    description = "Summarize each code/data file's purpose into <output>. Tags steps for the coder model."

    def required_args(self) -> tuple[str, ...]:
        return ("root", "output")

    def plan(self, **kwargs: Any) -> PlanResult:
        root_arg = kwargs.get("root")
        output_arg = kwargs.get("output")
        patterns = kwargs.get("patterns") or ["*.py", "*.ipynb", "*.json"]
        excludes = list(kwargs.get("exclude") or [])
        max_files = int(kwargs.get("max_files") or 0)
        recursive = bool(kwargs.get("recursive", True))
        max_size = int(kwargs.get("max_file_size_bytes") or 100_000)

        if not root_arg:
            raise PlannerError("code-inventory: 'root' is required")
        if not output_arg:
            raise PlannerError("code-inventory: 'output' is required")

        root = Path(str(root_arg)).expanduser().resolve()
        output = Path(str(output_arg)).expanduser().resolve()

        if not root.exists() or not root.is_dir():
            raise PlannerError(f"code-inventory: root not a directory: {root}")

        seen: set[Path] = set()
        for pat in patterns:
            it = root.rglob(pat) if recursive else root.glob(pat)
            for p in it:
                if p.is_file():
                    seen.add(p.resolve())
        files = sorted(seen)

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
                f"code-inventory: no files matched {patterns} under {root}"
                + (f" (skipped {len(oversized)} oversized)" if oversized else "")
            )

        steps = [
            Step(
                id=i,
                kind="code_inventory_file",
                args={"path": str(p), "output": str(output)},
                required_model="coder",
            )
            for i, p in enumerate(files)
        ]
        notes = f"patterns={patterns} recursive={recursive}"
        if excludes:
            notes += f" excludes={excludes}"
        if oversized:
            notes += f" skipped_oversized={len(oversized)}"
        return PlanResult(
            goal=f"Code-inventory {len(files)} files under {root} → {output}",
            steps=steps,
            output_path=str(output),
            notes=notes,
        )

    def render_step(self, step: Step, planner_args: dict) -> str:
        path = step.args.get("path", "(missing)")
        output = step.args.get("output", "(missing)")
        return (
            f"Read the code/data file at {path}. Produce a single-line summary "
            f"(roughly 25-50 words; one line, no preamble) covering: (1) the "
            f"file's primary purpose, (2) the most important functions, classes, "
            f"or data structures it defines, (3) key dependencies or inputs. "
            f"Append exactly one line to {output} in the format: "
            f"'{path}: <your summary>'. Use the write_file tool with mode='append'. "
            f"Do not modify any other file. When the line is appended, you are done."
        )


def _any_match(path: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(path, pat) for pat in patterns)
