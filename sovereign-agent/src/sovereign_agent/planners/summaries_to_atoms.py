"""summaries-to-atoms planner: salvage existing inventory text files into
Knowledge Atoms.

The classic inventory planner writes summary lines to a text file via the
``write_file`` tool — useful for human review, but doesn't populate
atoms.db. This planner reads those text files, parses each summary line,
and creates one atom per line.

Pure-Python execution (required_model='none'). ~30ms per atom on real
hardware. Idempotent via deterministic atom_ids (hash of source path +
summary content).

Usage:
    sovereign plan summaries-to-atoms \\
        --output /path/to/inventory-md.txt \\
        --tag genesis-md

This is the bridge between the v0.2.4-era inventory planner (text-file-out)
and the v0.2.7-era palace pipeline (atoms.db-in). After running this,
``palace-mine`` will have atoms to work with.

Format expectations:
    The inventory planner writes lines like:
        ``<path>: <summary text>``
    or
        ``<path> | <summary>``
    or just summary lines without explicit path prefix.
    The parser is forgiving — any non-empty line becomes an atom.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from ..continuation import Step
from .base import PlanResult, Planner, PlannerError


class SummariesToAtomsPlanner(Planner):
    name = "summaries-to-atoms"
    description = (
        "Atomize an existing inventory text file. Pure-Python, no model. "
        "Salvage path for v0.2.4-era inventory output → atoms.db."
    )

    def required_args(self) -> tuple[str, ...]:
        return ("output",)  # the inventory text file to read

    def plan(self, **kwargs: Any) -> PlanResult:
        output_arg = kwargs.get("output")
        tag = str(kwargs.get("tag") or "salvaged")
        max_atoms = int(kwargs.get("max_files") or 0)
        # Skip lines shorter than this — likely empty or noise.
        min_chars = int(kwargs.get("min_chars") or 20)

        if not output_arg:
            raise PlannerError(
                "summaries-to-atoms: 'output' is required (path to inventory text file)"
            )

        path = Path(str(output_arg)).expanduser().resolve()
        if not path.exists():
            raise PlannerError(
                f"summaries-to-atoms: file not found: {path}\n"
                f"  Hint: this should be an inventory text file produced by "
                f"`sov plan inventory --output ...`"
            )
        if not path.is_file():
            raise PlannerError(f"summaries-to-atoms: not a regular file: {path}")

        # Pre-parse: collect all non-empty lines that meet min_chars.
        # Step planning needs to know how many atoms we'll produce.
        lines: list[tuple[int, str]] = []
        try:
            with path.open("r", encoding="utf-8", errors="replace") as f:
                for lineno, line in enumerate(f, start=1):
                    line = line.strip()
                    if len(line) >= min_chars:
                        lines.append((lineno, line))
        except OSError as e:
            raise PlannerError(f"summaries-to-atoms: read failed: {e}") from e

        if not lines:
            raise PlannerError(
                f"summaries-to-atoms: no usable lines (>= {min_chars} chars) in {path}. "
                f"Check the file content or lower --min-chars."
            )

        if max_atoms > 0:
            lines = lines[:max_atoms]

        steps = [
            Step(
                id=i,
                kind="summaries_to_atoms_line",
                args={
                    "source_path": str(path),
                    "lineno": lineno,
                    "summary_line": summary,
                    "tag": tag,
                },
                required_model="none",
            )
            for i, (lineno, summary) in enumerate(lines)
        ]

        return PlanResult(
            goal=f"Atomize {len(lines)} summary lines from {path.name}",
            steps=steps,
            output_path=None,  # writes to atoms.db, not a single file
            notes=f"source={path} tag={tag!r}",
        )

    def render_step(self, step: Step, planner_args: dict) -> str:
        lineno = step.args.get("lineno", "?")
        return f"Atomize summary line {lineno} into atoms.db."


def execute_summaries_to_atoms_step(step: Step) -> str:
    """Pure-Python executor: parse one summary line into a Knowledge Atom.

    Atom shape:
      atom_id: deterministic — hash(source_path + lineno + summary)
      type: 'fact'
      summary: the line itself (truncated to 1000 chars)
      content_ref: inline JSON pointing at the source file + line number
      claims: empty list (the summary IS the claim; inventory output isn't
              structured enough to extract claims without the model)
      parents: empty
      created_by: actor='summaries_to_atoms'
    """
    from ..db import open_atoms_db

    source_path = step.args.get("source_path", "")
    lineno = int(step.args.get("lineno", 0))
    summary_line = step.args.get("summary_line", "").strip()
    tag = step.args.get("tag", "salvaged")

    if not summary_line:
        return f"line {lineno}: empty, skipped"

    # Deterministic atom_id — re-running on the same file produces the same id.
    seed = f"{source_path}:{lineno}:{summary_line}".encode("utf-8")
    atom_id = "atom-salvage-" + hashlib.sha256(seed).hexdigest()[:20]

    # Cap summary at the schema's 1000-char limit.
    summary_capped = summary_line[:990]

    conn = open_atoms_db()
    try:
        # Check if this atom already exists (idempotency)
        existing = conn.execute(
            "SELECT atom_id FROM atoms WHERE atom_id = ?", (atom_id,)
        ).fetchone()
        if existing:
            return f"line {lineno}: already atomized as {atom_id}"

        from datetime import datetime, timezone
        created_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

        conn.execute(
            "INSERT INTO atoms(atom_id, type, summary, content_ref, claims, "
            "parents, confidence, created_at, created_by) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                atom_id,
                "fact",
                summary_capped,
                json.dumps({
                    "kind": "inline",
                    "source_file": source_path,
                    "lineno": lineno,
                    "tag": tag,
                }),
                json.dumps([]),
                json.dumps([]),
                0.7,  # default confidence — these are model-generated summaries, not measurements
                created_at,
                json.dumps({
                    "actor": "summaries_to_atoms",
                    "source_file": source_path,
                    "lineno": lineno,
                }),
            ),
        )
        conn.commit()
    finally:
        conn.close()

    return f"line {lineno}: atomized as {atom_id}"
