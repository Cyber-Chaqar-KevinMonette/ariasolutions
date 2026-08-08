"""trillion-dollar planner: produce one cycle of an infinite-builder dream.

A "cycle" is a fixed-shape, five-step sequence:

    1. ideate         — orchestrator: write idea.md (one trillion-dollar idea)
    2. architect      — orchestrator: write architecture.md + manifest.json
                        (5–10 modules, file paths, what each one does)
    3. build          — coder:        implement everything in manifest.json
                        into cycle/src/. Multi-file via tool calls; one step
                        from the runner's POV.
    4. document       — orchestrator: write README.md + tests outline
    5. atomize        — pure-Python:  read what was produced, write atoms
                        that summarize this cycle (so the NEXT cycle's
                        ideate step can avoid duplication via memory_search).

Determinism:

    The plan is fixed-shape. Five steps, regardless of the eventual
    file count. The build step's *content* is non-deterministic (the
    model writes what it writes), but the *plan* is deterministic in
    the input arguments — which is what the re-trigger architecture
    requires.

The dream-runner spawns one of these continuations per cycle, drives it
to completion, then either spawns the next or stops (caps reached, paused,
halted).

This planner is normally NOT invoked directly via ``sov plan trillion-
dollar``. The dream-runner calls it on each cycle. We register it in
the planner registry so the operator *can* invoke it stand-alone for a
single-shot cycle if they want — useful for smoke-testing.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ..continuation import Step
from .base import PlanResult, Planner, PlannerError


class TrillionDollarPlanner(Planner):
    name = "trillion-dollar"
    description = (
        "Run ONE cycle of the infinite-builder loop: ideate → architect → "
        "build → document → atomize. Normally driven by `sov dream` rather "
        "than invoked directly. (v0.2.12)"
    )

    def required_args(self) -> tuple[str, ...]:
        # cycle_dir is where the model writes; dream_id ties output to a
        # parent dream session for atomization later.
        return ("cycle_dir", "dream_id")

    def plan(self, **kwargs: Any) -> PlanResult:
        cycle_dir_arg = kwargs.get("cycle_dir")
        dream_id = str(kwargs.get("dream_id") or "")
        cycle_number = int(kwargs.get("cycle_number") or 1)
        # Optional: comma-separated themes the operator wants represented
        # in the ideate step. Threaded through to the prompt verbatim.
        themes = kwargs.get("themes") or ""
        # v0.2.13: optional project name. When set, atomize tags every
        # written atom with this project so memory_search can filter to
        # this dream's lineage.
        project_name = kwargs.get("project_name") or ""

        if not cycle_dir_arg:
            raise PlannerError(
                "trillion-dollar: 'cycle_dir' is required "
                "(absolute path where this cycle's files will be written)"
            )
        if not dream_id:
            raise PlannerError("trillion-dollar: 'dream_id' is required")

        cycle_dir = Path(str(cycle_dir_arg)).expanduser().resolve()
        # Pre-create so the model's write_file calls land safely. This is
        # the only filesystem mutation the planner does — everything else
        # is the model's job.
        cycle_dir.mkdir(parents=True, exist_ok=True)
        (cycle_dir / "src").mkdir(exist_ok=True)

        idea_path = cycle_dir / "idea.md"
        arch_path = cycle_dir / "architecture.md"
        manifest_path = cycle_dir / "manifest.json"
        readme_path = cycle_dir / "README.md"

        steps = [
            Step(
                id=0,
                kind="dream_ideate",
                args={
                    "idea_path": str(idea_path),
                    "dream_id": dream_id,
                    "cycle_number": cycle_number,
                    "themes": themes,
                },
                required_model="orchestrator",
            ),
            Step(
                id=1,
                kind="dream_architect",
                args={
                    "idea_path": str(idea_path),
                    "arch_path": str(arch_path),
                    "manifest_path": str(manifest_path),
                    "src_dir": str(cycle_dir / "src"),
                },
                required_model="orchestrator",
            ),
            Step(
                id=2,
                kind="dream_build",
                args={
                    "manifest_path": str(manifest_path),
                    "arch_path": str(arch_path),
                    "src_dir": str(cycle_dir / "src"),
                },
                required_model="coder",
            ),
            Step(
                id=3,
                kind="dream_document",
                args={
                    "idea_path": str(idea_path),
                    "arch_path": str(arch_path),
                    "manifest_path": str(manifest_path),
                    "readme_path": str(readme_path),
                    "src_dir": str(cycle_dir / "src"),
                },
                required_model="orchestrator",
            ),
            Step(
                id=4,
                kind="dream_atomize",
                args={
                    "cycle_dir": str(cycle_dir),
                    "dream_id": dream_id,
                    "cycle_number": cycle_number,
                    "project_name": project_name,
                },
                required_model="none",
            ),
        ]

        return PlanResult(
            goal=(
                f"Build cycle {cycle_number} of dream {dream_id}: "
                f"trillion-dollar software in {cycle_dir.name}"
            ),
            steps=steps,
            output_path=str(readme_path),
            notes=f"dream_id={dream_id} cycle={cycle_number}",
        )

    def render_step(self, step: Step, planner_args: dict) -> str:
        # Each step gets a focused prompt. Keep them concrete — vague goals
        # cause the orchestrator model to loop-bounce instead of acting.
        if step.kind == "dream_ideate":
            return _render_ideate(step)
        if step.kind == "dream_architect":
            return _render_architect(step)
        if step.kind == "dream_build":
            return _render_build(step)
        if step.kind == "dream_document":
            return _render_document(step)
        if step.kind == "dream_atomize":
            return f"Atomize cycle output in {step.args.get('cycle_dir', '?')} into atoms.db."
        return f"Unknown step kind: {step.kind!r}"


def _render_ideate(step: Step) -> str:
    """The single-line trillion-dollar idea step."""
    from ..personas import MASTER_ARCHITECT
    idea_path = step.args.get("idea_path", "")
    cycle = step.args.get("cycle_number", "?")
    themes = step.args.get("themes", "")
    theme_clause = (
        f" The operator has hinted at these themes: {themes}. "
        f"Treat them as soft preferences, not hard constraints."
    ) if themes else ""
    # First, ask memory_search to see what previous cycles already did so
    # we don't repeat ourselves. Then write the idea. Two tools, simple loop.
    return (
        f"{MASTER_ARCHITECT.render()}\n\n---\n\n"
        f"# TASK: pick ONE trillion-dollar idea for cycle {cycle}\n\n"
        f"Step 1: call memory_search with query 'trillion-dollar idea' to see "
        f"what previous cycles have produced (if any). "
        f"Step 2: pick an idea DIFFERENT from anything already produced — a "
        f"real, plausible product that could be worth a trillion dollars "
        f"(large markets, network effects, AI/biotech/energy/finance/infra "
        f"are fair game). "
        f"Step 3: write a file at {idea_path} containing exactly: a one-line "
        f"title (h1), then 3-5 short paragraphs covering: the problem, the "
        f"wedge, why now, the moat, the rough TAM. Use the write_file tool "
        f"with mode='write'. Total length ~400-700 words.{theme_clause} "
        f"When the file is written, you are done."
    )


def _render_architect(step: Step) -> str:
    """The architect step writes architecture.md and a manifest.json.

    The manifest is a structured contract the build step relies on: a JSON
    array of {path, role, summary} objects. Anything not in the manifest
    won't get built.
    """
    from ..personas import MASTER_ARCHITECT
    idea_path = step.args.get("idea_path", "")
    arch_path = step.args.get("arch_path", "")
    manifest_path = step.args.get("manifest_path", "")
    src_dir = step.args.get("src_dir", "")
    return (
        f"{MASTER_ARCHITECT.render()}\n\n---\n\n"
        f"# TASK: design the buildable MVP for the idea at {idea_path}\n\n"
        f"Step 1: read {idea_path} with read_file. "
        f"Step 2: design a buildable MVP — pick a primary language (Python "
        f"or TypeScript usually best), 5 to 10 modules, each with a clear "
        f"single responsibility. "
        f"Step 3: write {arch_path} (markdown) explaining: language choice "
        f"+ why, the module list with one-paragraph descriptions of each, "
        f"and the data flow between them. "
        f"Step 4: write {manifest_path} containing valid JSON of shape "
        f'[{{"path": "<relative path under {src_dir}>", '
        f'"role": "<short role>", '
        f'"summary": "<one sentence of intent>"}}, ...]. '
        f"Paths must be relative (e.g. 'core/engine.py'), not absolute. "
        f"Use write_file with mode='write' for both files. When both are "
        f"written, you are done."
    )


def _render_build(step: Step) -> str:
    """The build step writes all source files described in manifest.json."""
    from ..personas import FRIENDLY_BUILDER
    manifest_path = step.args.get("manifest_path", "")
    arch_path = step.args.get("arch_path", "")
    src_dir = step.args.get("src_dir", "")
    return (
        f"{FRIENDLY_BUILDER.render()}\n\n---\n\n"
        f"# TASK: write the source files described in {manifest_path}\n\n"
        f"Step 1: read {manifest_path} and parse it as JSON. "
        f"Step 2: read {arch_path} for context on each module. "
        f"Step 3: for EACH entry in the manifest, write the source file at "
        f"{src_dir}/<entry.path>. Each file should be a working, "
        f"syntactically valid skeleton: real imports, real function "
        f"signatures, docstrings, and bodies that either implement or "
        f"raise NotImplementedError with a clear message. ~50-200 lines "
        f"each. Use write_file with mode='write'. "
        f"\n\n"
        f"**SYNTAX MATTERS.** Every Python file MUST: (1) parse with "
        f"ast.parse; (2) use spaces OR tabs for indentation, never both in "
        f"the same file. Invalid files will be quarantined and not "
        f"atomized — they will not be remembered. "
        f"\n\n"
        f"Do NOT modify files outside {src_dir}. When every manifest entry "
        f"has a corresponding file, you are done."
    )


def _render_document(step: Step) -> str:
    """Final-pass documentation step."""
    from ..personas import MASTER_ARCHITECT
    idea_path = step.args.get("idea_path", "")
    arch_path = step.args.get("arch_path", "")
    manifest_path = step.args.get("manifest_path", "")
    readme_path = step.args.get("readme_path", "")
    src_dir = step.args.get("src_dir", "")
    return (
        f"{MASTER_ARCHITECT.render()}\n\n---\n\n"
        f"# TASK: write the README and tests-outline for this cycle\n\n"
        f"Step 1: read {idea_path}, {arch_path}, and {manifest_path}. "
        f"Step 2: write {readme_path} containing: a 1-paragraph elevator "
        f"pitch (drawn from idea.md), a 'Modules' section listing each "
        f"manifest entry by path with its summary, a 'Getting started' "
        f"stub (install / run), a 'Tests' subsection sketching what tests "
        f"would prove this works, and a 'License' section noting the "
        f"intended SPDX identifier (recommend MIT or Apache-2.0 unless the "
        f"idea suggests otherwise — cite reasoning). "
        f"Reference the actual file paths under {src_dir}. Use write_file "
        f"with mode='write'. ~300-500 words total. When written, you are done."
    )


# ─── Pure-Python atomize executor ───────────────────────────────────────────


def execute_dream_atomize_step(step: Step) -> str:
    """Read the cycle's outputs and write summary atoms to atoms.db.

    The atoms produced here are what the NEXT cycle's ideate step will
    surface via memory_search. Without them, the model has no awareness
    of what it already built — and tends to repeat itself.

    Idempotent: deterministic atom_ids per (dream_id, cycle, source_file).

    Atom shape:
      atom_id: 'atom-dream-' + sha256(dream_id + cycle + relative_path)[:20]
      type: 'fact'
      summary: 'dream <dream_id> cycle <N>: <relative_path> — <first line>'
      content_ref: {kind: 'dream_cycle', dream_id, cycle, path, role}
      claims: []
      confidence: 0.85 — model-generated, slightly hedged
      created_by: actor='dream_atomize'
    """
    import hashlib
    import json

    cycle_dir = Path(str(step.args.get("cycle_dir", "")))
    dream_id = str(step.args.get("dream_id", ""))
    cycle_number = int(step.args.get("cycle_number", 0))

    if not cycle_dir.exists():
        return f"cycle dir missing: {cycle_dir}"

    from datetime import datetime, timezone
    from ..db import open_atoms_db
    from ..validators import quarantine_failures, validate_tree
    from ..memory_namespaces import tag_atom, is_valid_project_name

    # ── v0.2.13: validator pass BEFORE atomize ──────────────────────────
    # Quarantine any file that fails syntax/parse. The atomize step that
    # follows must NOT atomize broken files because they'd appear in
    # memory_search and steer future cycles wrong (anti-zombie, anti-
    # propagate-broken-pattern).
    src_dir = cycle_dir / "src"
    quarantined = 0
    if src_dir.exists():
        results = validate_tree(src_dir)
        q_count, _ = quarantine_failures(results, cycle_dir=cycle_dir)
        quarantined = q_count

    # Files we care about: idea.md, architecture.md, README.md, and every
    # source file under src/. Skip manifest.json (it's structural, not
    # narrative) and any binary-shaped junk.
    docs: list[Path] = []
    for name in ("idea.md", "architecture.md", "README.md"):
        p = cycle_dir / name
        if p.is_file():
            docs.append(p)
    if src_dir.exists():
        for p in sorted(src_dir.rglob("*")):
            if p.is_file():
                # Skip anything we already moved to quarantine.
                try:
                    rel_parts = p.relative_to(cycle_dir).parts
                except ValueError:
                    continue
                if "quarantine" in rel_parts:
                    continue
                docs.append(p)

    if not docs:
        return f"no files to atomize in {cycle_dir}"

    # Project tag passed via step args by the dream-runner if the dream
    # is tied to a project. None means "no project namespace."
    project = str(step.args.get("project_name", "") or "").strip() or None
    if project and not is_valid_project_name(project):
        project = None  # silently skip rather than crash atomize

    written = 0
    skipped = 0
    conn = open_atoms_db()
    try:
        for path in docs:
            try:
                rel = str(path.relative_to(cycle_dir))
            except ValueError:
                rel = path.name
            seed = f"{dream_id}:{cycle_number}:{rel}".encode("utf-8")
            atom_id = "atom-dream-" + hashlib.sha256(seed).hexdigest()[:20]

            existing = conn.execute(
                "SELECT atom_id FROM atoms WHERE atom_id = ?", (atom_id,)
            ).fetchone()
            if existing:
                skipped += 1
                continue

            # First non-empty line as a summary anchor. Capped to 600 chars
            # so the summary column stays tidy across many cycles.
            first_line = ""
            try:
                with path.open("r", encoding="utf-8", errors="replace") as f:
                    for line in f:
                        s = line.strip()
                        if s:
                            first_line = s[:600]
                            break
            except OSError:
                first_line = "(unreadable)"

            summary = (
                f"dream {dream_id} cycle {cycle_number}: {rel} — {first_line}"
            )[:990]

            role = (
                "idea" if rel == "idea.md"
                else "architecture" if rel == "architecture.md"
                else "readme" if rel == "README.md"
                else "source"
            )

            conn.execute(
                "INSERT INTO atoms(atom_id, type, summary, content_ref, claims, "
                "parents, confidence, created_at, created_by) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    atom_id,
                    "fact",
                    summary,
                    json.dumps({
                        "kind": "dream_cycle",
                        "dream_id": dream_id,
                        "cycle": cycle_number,
                        "path": rel,
                        "role": role,
                        "abs_path": str(path),
                    }),
                    json.dumps([]),
                    json.dumps([]),
                    0.85,
                    datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                    json.dumps({
                        "actor": "dream_atomize",
                        "dream_id": dream_id,
                        "cycle": cycle_number,
                    }),
                ),
            )
            written += 1

            # v0.2.13: project namespace tagging. If the dream is tied to
            # a project, tag every atom we write with that project. Tagging
            # is idempotent and best-effort — failures here are logged but
            # do not abort the atomize step.
            if project:
                try:
                    tag_atom(conn, atom_id, project)
                except Exception:  # noqa: BLE001
                    pass
        conn.commit()
    finally:
        conn.close()

    # v0.2.13: report counts in a parseable form for the dream-runner's
    # _finalize_cycle to extract atoms_written/quarantined_count for
    # idle-cycle detection.
    return (
        f"cycle {cycle_number}: atomized {written} files "
        f"({skipped} already present, {quarantined} quarantined)"
    )
