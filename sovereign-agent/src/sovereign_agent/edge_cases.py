"""
╔══════════════════════════════════════════════════════════════════════════╗
║  edge_cases.py — Central registry of defensive checks                    ║
║  v0.2.13                                                                  ║
║                                                                           ║
║  Every defensive check in the codebase — every "if X is None, raise" —   ║
║  is registered here with: a stable id, a description, the location,     ║
║  the recovery path, and a severity. Two reasons for this:                ║
║                                                                           ║
║    1. AUDITABILITY. When a rare edge case fires in production, the      ║
║       operator can `sov edge-cases show <id>` and learn instantly what  ║
║       it means and what to do.                                           ║
║                                                                           ║
║    2. NO MAGIC FAILURES. Each check has a name and a docstring. New     ║
║       defensive checks added in code MUST also be registered here,      ║
║       which forces the author to think about the recovery path before   ║
║       merging.                                                           ║
║                                                                           ║
║  This is OUR map of where the cliffs are. Reading it should give a new  ║
║  contributor a map of "here is everywhere this code can fail" — better  ║
║  than reading every file looking for try/except.                         ║
║                                                                           ║
║  When a check fires, code should call ``track(id, payload=...)`` to     ║
║  emit an event so we can see frequency over time.                        ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

Severity = Literal["info", "warn", "error", "critical"]


@dataclass(frozen=True)
class EdgeCase:
    """One registered edge case."""
    id: str                  # e.g. "EC-DREAM-001"
    title: str               # short human-readable title
    location: str            # module:function or "various"
    description: str         # what this check guards against
    fires_when: str          # what condition triggers it
    recovery: str            # what the operator should do
    severity: Severity = "warn"
    introduced_in: str = ""  # version added


# ─── Master registry ────────────────────────────────────────────────────────
#
# IDs follow the pattern: EC-<SUBSYSTEM>-<NNN>. Subsystems:
#   DREAM    — dream sessions, cycles, atomize
#   PROJ     — project tracking
#   CONT     — continuations
#   PAL      — palace
#   FOSS     — license / lineage
#   VAL      — validators
#   OLLAMA   — model dispatch
#   IO       — disk / lock / network
#   PARSE    — directive / config parsing


REGISTRY: dict[str, EdgeCase] = {

    # ── Dream subsystem ────────────────────────────────────────────────
    "EC-DREAM-001": EdgeCase(
        id="EC-DREAM-001",
        title="Dream advance attempted on terminal session",
        location="dream_runner.advance_dream",
        description=(
            "A dream that's already paused/exhausted/completed/halted "
            "cannot be advanced. The runner returns immediately with the "
            "matching outcome rather than touching the cycle continuation."
        ),
        fires_when=(
            "Caller invokes advance_dream on a dream whose status is not "
            "'active'."
        ),
        recovery=(
            "Resume the dream (`sov dream resume <id>`) or accept the "
            "terminal state. If the loop driver hits this, exit code 8 "
            "ends the loop gracefully."
        ),
        severity="info",
        introduced_in="0.2.12",
    ),
    "EC-DREAM-002": EdgeCase(
        id="EC-DREAM-002",
        title="File cap exceeded mid-cycle",
        location="dream_runner.advance_dream",
        description=(
            "After a cycle finalizes, the dream's files_written count "
            "may exceed its max_files cap. The dream transitions to "
            "'exhausted' and the next advance is refused."
        ),
        fires_when=(
            "Recomputed files_written >= max_files at cycle finalize OR "
            "at the start of advance_dream."
        ),
        recovery=(
            "Raise the cap with `sov dream show` to inspect, or accept "
            "the stop. Files written so far are preserved on disk."
        ),
        severity="info",
        introduced_in="0.2.12",
    ),
    "EC-DREAM-003": EdgeCase(
        id="EC-DREAM-003",
        title="Hard backstop cycle cap reached",
        location="dream_runner.advance_dream",
        description=(
            "Even with max_cycles=None, dreams cannot exceed "
            "HARD_CAP_CYCLES (100,000). This prevents pathological "
            "runaway from a misconfigured session."
        ),
        fires_when="cycles_completed >= 100,000",
        recovery=(
            "If you legitimately need more cycles, start a fresh dream "
            "with the existing dream's atoms still in atoms.db (so no "
            "memory is lost). The HARD_CAP_CYCLES ceiling itself is "
            "intentionally unconfigurable."
        ),
        severity="warn",
        introduced_in="0.2.12",
    ),
    "EC-DREAM-004": EdgeCase(
        id="EC-DREAM-004",
        title="Cycle continuation file deleted out from under dream",
        location="dream_runner.advance_dream",
        description=(
            "The dream's current_cycle_task_id refers to a continuation "
            "YAML that no longer exists on disk (operator deleted it, "
            "or atomic-write race lost it)."
        ),
        fires_when=(
            "ContinuationStore.get raises ContinuationNotFound for "
            "current_cycle_task_id."
        ),
        recovery=(
            "Runner treats the cycle as ended and plans a fresh one on "
            "the next advance. No data loss for prior cycles."
        ),
        severity="warn",
        introduced_in="0.2.12",
    ),
    "EC-DREAM-005": EdgeCase(
        id="EC-DREAM-005",
        title="Dream is active but underlying cycle is paused",
        location="dream_runner.advance_dream",
        description=(
            "Someone paused the cycle continuation directly without "
            "pausing the dream. Without this check, the inline driver "
            "would spin forever returning 'paused' outcomes."
        ),
        fires_when=(
            "step_outcome == 'paused' from run_one_step on an active "
            "dream."
        ),
        recovery=(
            "Runner auto-pauses the dream as well and surfaces the "
            "discrepancy. Resume both: `sov dream resume <id>`."
        ),
        severity="warn",
        introduced_in="0.2.13",
    ),
    "EC-DREAM-006": EdgeCase(
        id="EC-DREAM-006",
        title="Idle cycle detected (zero novelty)",
        location="dream_runner.advance_dream",
        description=(
            "The last N cycles produced ≤ idle_threshold atoms each. "
            "Likely the agent has saturated the idea space and is "
            "looping. The dream auto-pauses to avoid wasting tokens."
        ),
        fires_when=(
            "len(recent_cycles) >= 3 AND each recent cycle's "
            "atoms_written <= IDLE_ATOM_THRESHOLD (default 1)."
        ),
        recovery=(
            "Inspect the cycles (`sov dream show`), nudge with a steering "
            "prompt or new --project, and resume; or accept the pause."
        ),
        severity="info",
        introduced_in="0.2.13",
    ),

    # ── Project subsystem ──────────────────────────────────────────────
    "EC-PROJ-001": EdgeCase(
        id="EC-PROJ-001",
        title="Project root directory missing on update",
        location="cli.projects_update_cmd",
        description=(
            "The project's saved root no longer exists on disk. We "
            "refuse to silently re-scan a moved directory because that "
            "would mark every file as 'removed'."
        ),
        fires_when="Path(snapshot.root).is_dir() returns False.",
        recovery=(
            "Re-create the project: `sov projects delete <name>` then "
            "`sov projects scan <name> <new-root>`."
        ),
        severity="error",
        introduced_in="0.2.12",
    ),
    "EC-PROJ-002": EdgeCase(
        id="EC-PROJ-002",
        title="Project name contains forbidden characters",
        location="projects.ProjectStore._path",
        description=(
            "Project names may only contain alphanumerics and -._ to "
            "guarantee safe use as filenames."
        ),
        fires_when="Name contains separators, whitespace, quotes, or empty.",
        recovery="Pick a different name (e.g., 'my-repo' not 'my repo').",
        severity="error",
        introduced_in="0.2.12",
    ),

    # ── Continuation subsystem ─────────────────────────────────────────
    "EC-CONT-001": EdgeCase(
        id="EC-CONT-001",
        title="Continuation paused — runner refuses advance",
        location="continue_runner.run_one_step",
        description=(
            "A paused continuation must not be advanced. The runner "
            "returns outcome='paused' before any model invocation."
        ),
        fires_when="continuation.status == 'paused' at lock acquisition.",
        recovery="`sov resume <task_id>` to clear the pause.",
        severity="info",
        introduced_in="0.2.12",
    ),
    "EC-CONT-002": EdgeCase(
        id="EC-CONT-002",
        title="Stale lock detected (zombie process)",
        location="health.scan_zombies",
        description=(
            "A continuation's .lock file references a PID no longer "
            "running. The lock will never be released by its owner."
        ),
        fires_when=(
            "Lock owner PID is not in the process table AND lock file is "
            "older than STALE_LOCK_THRESHOLD (default 1 hour)."
        ),
        recovery=(
            "`sov health repair --stale-locks` to remove confirmed-dead "
            "lock files. Always dry-run first."
        ),
        severity="warn",
        introduced_in="0.2.13",
    ),
    "EC-CONT-003": EdgeCase(
        id="EC-CONT-003",
        title="Continuation status is unrecognized",
        location="continuation._from_yaml_dict",
        description=(
            "A continuation YAML has a status value not in the known "
            "set. Likely a typo or a forward-incompat schema."
        ),
        fires_when="status not in _VALID_CONT_STATUSES.",
        recovery=(
            "Inspect the YAML; restore from backup if corrupted; "
            "downgrade to the right version if cross-version."
        ),
        severity="error",
        introduced_in="0.2.12",
    ),

    # ── Validators ─────────────────────────────────────────────────────
    "EC-VAL-001": EdgeCase(
        id="EC-VAL-001",
        title="Generated Python file failed AST parse",
        location="validators.validate_python_source",
        description=(
            "The dream-builder produced a .py file with syntax errors. "
            "The atomize step quarantines it rather than committing it "
            "to atoms.db where it would mislead future cycles."
        ),
        fires_when="ast.parse() raises SyntaxError.",
        recovery=(
            "File moves to <cycle_dir>/quarantine/ with .errors.json. "
            "Inspect the errors and decide if the cycle should be "
            "discarded entirely (`sov dream show` to assess)."
        ),
        severity="warn",
        introduced_in="0.2.13",
    ),
    "EC-VAL-002": EdgeCase(
        id="EC-VAL-002",
        title="Mixed tabs and spaces in Python file",
        location="validators.validate_python_source",
        description=(
            "A common LLM failure mode: indentation that LOOKS right "
            "but mixes tabs and spaces. AST parse passes but Python "
            "rejects at runtime."
        ),
        fires_when=(
            "Same logical block contains both leading-tab and "
            "leading-space lines."
        ),
        recovery=(
            "Same as EC-VAL-001 — quarantined, atomize skips."
        ),
        severity="warn",
        introduced_in="0.2.13",
    ),
    "EC-VAL-003": EdgeCase(
        id="EC-VAL-003",
        title="Generated JSON failed parse",
        location="validators.validate_json",
        description=(
            "A JSON file (typically manifest.json) didn't parse. The "
            "build step relies on the manifest being valid JSON; an "
            "invalid manifest poisons the cycle."
        ),
        fires_when="json.loads() raises JSONDecodeError.",
        recovery=(
            "Cycle is marked degraded. Best to discard and start a fresh "
            "cycle — the architect step needs a re-do."
        ),
        severity="error",
        introduced_in="0.2.13",
    ),

    # ── Health / anti-zombie / anti-ghost ──────────────────────────────
    "EC-HEALTH-001": EdgeCase(
        id="EC-HEALTH-001",
        title="Zombie continuation (stalled in_progress)",
        location="health.scan_zombies",
        description=(
            "A continuation has been in_progress for hours with no step "
            "advance and no held lock. Almost certainly orphaned by a "
            "crashed process."
        ),
        fires_when=(
            "status='in_progress' AND no lock file AND "
            "now - updated_at > ZOMBIE_THRESHOLD (default 6 hours)."
        ),
        recovery=(
            "If you know the work is dead: `sov continuations cancel <id>`. "
            "Otherwise: `sov resume --drive <id>` to pick up where it "
            "stopped."
        ),
        severity="warn",
        introduced_in="0.2.13",
    ),
    "EC-HEALTH-002": EdgeCase(
        id="EC-HEALTH-002",
        title="Ghost dream (no current cycle, status=active)",
        location="health.scan_ghosts",
        description=(
            "A dream is marked active but has no current_cycle_task_id "
            "and no recent updated_at. Most likely the runner died "
            "between cycle finalize and new cycle plan."
        ),
        fires_when=(
            "status='active' AND current_cycle_task_id is None AND "
            "now - updated_at > GHOST_THRESHOLD (default 1 hour)."
        ),
        recovery=(
            "Resume drives the next cycle. If the dream should be done, "
            "`sov dream stop <id>`."
        ),
        severity="warn",
        introduced_in="0.2.13",
    ),
    "EC-HEALTH-003": EdgeCase(
        id="EC-HEALTH-003",
        title="Orphan cycle (continuation exists but no dream owns it)",
        location="health.scan_ghosts",
        description=(
            "A continuation with task_id matching the cycle-* pattern "
            "exists, but no dream session lists it in its cycles[]."
        ),
        fires_when=(
            "task_id starts with 'cycle-' AND no dream's "
            "cycles[*].task_id matches."
        ),
        recovery=(
            "Likely a leftover from a deleted dream session. "
            "`sov continuations cancel <id>` if confirmed dead."
        ),
        severity="info",
        introduced_in="0.2.13",
    ),

    # ── FOSS / license ─────────────────────────────────────────────────
    "EC-FOSS-001": EdgeCase(
        id="EC-FOSS-001",
        title="License compatibility unknown — needs human review",
        location="foss.is_compatible_for_redistribution",
        description=(
            "Asked to validate a license combination not in our "
            "conservative known-safe pairs."
        ),
        fires_when=(
            "Either license is not in KNOWN_LICENSES, or the combination "
            "isn't an enumerated safe pair."
        ),
        recovery=(
            "Read the rationale string; consult a human; do not let the "
            "agent auto-resolve license questions."
        ),
        severity="warn",
        introduced_in="0.2.13",
    ),

    # ── Parse / directive ──────────────────────────────────────────────
    "EC-PARSE-001": EdgeCase(
        id="EC-PARSE-001",
        title="Directive could not be classified",
        location="directives.parse_directive",
        description=(
            "Plain-English directive doesn't match any known intent."
        ),
        fires_when="No keyword set matched the directive.",
        recovery=(
            "Run `sov do help` to see recognized phrasings, or use the "
            "explicit subcommand."
        ),
        severity="info",
        introduced_in="0.2.12",
    ),
}


def get(edge_case_id: str) -> EdgeCase:
    """Lookup by id. Raises KeyError on miss."""
    if edge_case_id not in REGISTRY:
        raise KeyError(f"unknown edge case id: {edge_case_id!r}")
    return REGISTRY[edge_case_id]


def list_all() -> list[EdgeCase]:
    """All registered edge cases, sorted by id."""
    return [REGISTRY[k] for k in sorted(REGISTRY.keys())]


def by_subsystem(prefix: str) -> list[EdgeCase]:
    """Filter by id prefix (e.g. 'EC-DREAM' for the dream subsystem)."""
    pref = prefix.upper()
    return [REGISTRY[k] for k in sorted(REGISTRY.keys()) if k.startswith(pref)]


def by_severity(sev: Severity) -> list[EdgeCase]:
    """Filter by severity level."""
    return [REGISTRY[k] for k in sorted(REGISTRY.keys()) if REGISTRY[k].severity == sev]


def track(edge_case_id: str, payload: dict[str, Any] | None = None) -> None:
    """Emit an event when an edge case fires.

    The event is sent through the standard events plane so it lands in
    whatever observability surface the operator has wired up. We
    deliberately don't raise if the id is unknown — observability code
    should never break the work it's observing.
    """
    try:
        from .events import emit_event
        ec = REGISTRY.get(edge_case_id)
        emit_event(
            "edge-case-fired-d",
            plane="control",
            trace_id=f"edge-case:{edge_case_id}",
            payload={
                "edge_case_id": edge_case_id,
                "title": ec.title if ec else "(unknown)",
                "severity": ec.severity if ec else "warn",
                "details": payload or {},
            },
        )
    except Exception:  # noqa: BLE001
        # Observability must never break the caller. Swallow.
        pass


def render_table(entries: list[EdgeCase] | None = None) -> str:
    """Render registered edge cases as a table-shaped markdown string.

    Pure formatting — no rich/console dependency, so this works in plain
    text contexts (e.g. emitted to a file or piped to `less`). The CLI
    has its own rich version.
    """
    entries = entries if entries is not None else list_all()
    if not entries:
        return "(no edge cases registered)\n"
    lines = ["| ID | Title | Severity | Where |", "| --- | --- | --- | --- |"]
    for ec in entries:
        lines.append(f"| {ec.id} | {ec.title} | {ec.severity} | {ec.location} |")
    return "\n".join(lines) + "\n"


__all__ = [
    "EdgeCase",
    "REGISTRY",
    "Severity",
    "by_severity",
    "by_subsystem",
    "get",
    "list_all",
    "render_table",
    "track",
]
