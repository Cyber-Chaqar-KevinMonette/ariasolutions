"""record_game_lesson — Tier 1. Durable, cross-project game-dev memory.

Kevin (2026-08-02): "make sure she remembers and learns her best workflows
and production techniques, so in the future I can ask her to make full
games with only natural language." Two real gaps this closes:

  1. game_dev_xp.py's "lesson_logged" event exists but only writes to that
     ONE project's XP ledger — invisible to any future, different project.
     A lesson learned building Ember Keep (idle-incremental) should be
     retrievable while building the NEXT game, whatever genre it is.
  2. memory_write's Atom schema is real and durable (atoms.db), but its
     shape is generic — nothing steers a game-dev lesson into the same
     structure every time, which is what makes them retrievable/comparable
     later instead of a pile of free-text notes.

Deliberately mirrors mos_canon.py's "mos-lesson-capture" clause (added
this same session): trigger, context, failure_mode, correction, rule,
confidence — the same shape, so a lesson written here is structurally
consistent with the rest of the system's own lesson-capture doctrine, not
a one-off game-specific format. confidence < 0.5 is provisional (a
hunch); only confidence > 0.8 lessons are the kind a future "build a full
game from scratch" session should actually treat as an enforced rule
rather than a hint — see check_sprite_quality/ANTI_COLLAGE_TERMS in
sprite_qa.py for a real example of exactly this graduation already
having happened once (a live-observed failure -> a rule baked into the
tool itself, not just a note).

Records to BOTH:
  - The project's own game_dev_xp ledger (lesson_logged, visible locally,
    same convention GETTING_STARTED.md already documents to her).
  - atoms.db via memory_write's Atom (scope_tags=["game-dev", genre,
    engine] plus the project slug) — durable, cross-project, retrievable
    by memory_search/retrieve_memory from ANY future game project, which
    is the actual mechanism that lets accumulated technique compound
    across projects instead of resetting with each new one.
"""
from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from .. import game_dev_xp
from ..game_projects import load_by_slug
from .base import Tool, ToolResult

try:
    from ..db import open_atoms_db
    from ..memory import Atom, index_atom_vector, write_atom
except ImportError:  # pragma: no cover — mirrors git_reflect.py's own degrade
    open_atoms_db = None  # type: ignore[assignment]
    Atom = None  # type: ignore[assignment]
    write_atom = None  # type: ignore[assignment]
    index_atom_vector = None  # type: ignore[assignment]


class _Args(BaseModel):
    project_slug: str = Field(description="Slug of a registered game project")
    trigger: str = Field(description="What situation/action triggered this — concrete, not vague.")
    context: str = Field(description="What was being attempted when this happened.")
    failure_mode: str = Field(description="What actually went wrong (or, for a positive "
                                          "technique, what would go wrong WITHOUT it).")
    correction: str = Field(description="The fix or technique that actually worked.")
    rule: str = Field(description="The generalizable rule future work should follow — "
                                  "phrased so it applies beyond this one project.")
    confidence: float = Field(
        ge=0.0, le=1.0,
        description="Genuine calibration, not inflated. <0.5 = provisional hint. "
                    ">0.8 = seen repeat / clearly root-caused, treat as an enforced rule.",
    )


class RecordGameLessonTool(Tool[_Args]):
    name = "record_game_lesson"
    tier = 1
    description = (
        "Record a durable, cross-project game-dev lesson (trigger/context/"
        "failure_mode/correction/rule/confidence — same shape as mos_canon's "
        "lesson-capture doctrine). Writes to both the project's local XP "
        "ledger AND atoms.db, so future game projects (any genre) can "
        "retrieve it via memory_search — this is the real mechanism that "
        "lets technique compound across projects instead of resetting each "
        "time. Use right after root-causing a real bug or confirming a "
        "design/workflow technique actually worked — not for routine notes. "
        "FAILURE MODES: unknown_project; schema_violation; db_unavailable."
    )
    failure_modes = ("unknown_project", "schema_violation", "db_unavailable")
    Args = _Args

    def __init__(self, data_dir: Path | None = None) -> None:
        self._data_dir = data_dir

    async def execute(self, args: _Args, *, trace_id: str) -> ToolResult:
        data_dir = self._data_dir
        if data_dir is None:
            from ..config import SETTINGS
            data_dir = SETTINGS.paths.data_dir

        project = load_by_slug(args.project_slug, data_dir)
        if project is None:
            return ToolResult(ok=False, error=f"unknown_project: {args.project_slug!r}")

        lesson_note = (
            f"[{args.rule}] trigger: {args.trigger} | context: {args.context} | "
            f"failure_mode: {args.failure_mode} | correction: {args.correction} "
            f"(confidence={args.confidence:.2f})"
        )
        game_dev_xp.award(args.project_slug, "lesson_logged", lesson_note, data_dir)

        atom_id = None
        vector_indexed = False
        if Atom is not None and open_atoms_db is not None:
            try:
                atom = Atom(
                    type="game_lesson",
                    summary=args.rule[:1000],
                    content_ref={"kind": "inline", "content": lesson_note},
                    claims=[
                        {"text": args.failure_mode, "evidence_ref": f"trace:{trace_id}"},
                    ],
                    parents=[trace_id],
                    confidence=args.confidence,
                    created_by={"actor": "agent", "tool": "record_game_lesson"},
                    scope_path=f"game-dev/{args.project_slug}",
                    scope_tags=["game-dev", project.genre, project.engine, args.project_slug],
                )
            except ValueError as e:
                return ToolResult(ok=False, error=f"schema_violation: {e}")

            import asyncio

            def _write() -> str:
                # write_atom() also indexes into fts_atoms now (found live
                # 2026-08-02, see memory/atom.py's write_atom docstring).
                conn = open_atoms_db()
                try:
                    aid = write_atom(conn, atom)
                    conn.commit()
                    return aid
                finally:
                    conn.close()

            try:
                atom_id = await asyncio.to_thread(_write)
            except Exception as exc:  # noqa: BLE001
                return ToolResult(ok=False, error=f"db_unavailable: {exc!r}")

            vector_indexed = False
            try:
                vconn = open_atoms_db()
                try:
                    await index_atom_vector(vconn, atom)
                    vconn.commit()
                    vector_indexed = True
                finally:
                    vconn.close()
            except Exception:  # noqa: BLE001 — embedding/Ollama down: FTS-only is still searchable
                vector_indexed = False

        return ToolResult(ok=True, output={
            "project": project.project_name,
            "atom_id": atom_id,
            "vector_indexed": vector_indexed,
            "scope_tags": ["game-dev", project.genre, project.engine, args.project_slug],
            "message": f"Lesson recorded for {project.project_name!r}"
                      + (f" (atom {atom_id})" if atom_id else " (XP ledger only — atoms.db unavailable)")
                      + " — retrievable from any future game project via memory_search.",
        })


__all__ = ["RecordGameLessonTool"]
