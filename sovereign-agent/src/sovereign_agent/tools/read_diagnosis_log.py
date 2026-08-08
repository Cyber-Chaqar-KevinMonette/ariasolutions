"""
read_diagnosis_log.py — read the Conflict→Diagnosis→Resolution catalog

Tier 0 tool. Gives Aria access to the shared diagnosis catalog —
the append-only record of every conflict, its diagnosis, and its resolution.

Reading this tells Aria:
  - What has gone wrong before and why
  - What fixes were applied and whether they worked
  - What policies changed as a result
  - Who was the actor (Kevin / Claude / Aria)

This is Aria's institutional memory of past problems. She should
read it when debugging a recurring issue or before making a decision
that has burned before.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from sovereign_agent.config import SETTINGS

from .base import Tool, ToolResult


class ReadDiagnosisLogTool(Tool):
    """Read entries from the Conflict→Diagnosis→Resolution catalog.

    The catalog is the shared institutional memory of past conflicts.
    Reading it tells you what has gone wrong before, why, and what fixed it.

    Args:
      limit       — max entries to return (default 20, newest first)
      actor       — filter by actor: "kevin", "claude", "aria"
      type        — filter by conflict type (e.g. "capability_gap")
      case_id     — read one specific case in full detail

    Returns a formatted report of matching entries.
    Read this before debugging a recurring problem — someone may have
    already solved it.
    """

    name = "read_diagnosis_log"
    tier = 0
    description = (
        "Read the Conflict→Diagnosis→Resolution catalog — institutional memory of past conflicts. "
        "Args: limit (default 20), actor (kevin/claude/aria), type (conflict type), case_id (one entry). "
        "Returns formatted report: what went wrong, why, what fixed it, policy changes. "
        "Read before debugging recurring issues."
    )
    failure_modes = (
        "data_dir not configured",
        "diagnoses directory empty (no conflicts logged yet)",
        "case_id not found",
    )

    class Args(BaseModel):
        limit: int = Field(default=20, ge=1, le=200, description="Max entries to return.")
        actor: Optional[str] = Field(
            default=None,
            description="Filter by actor: kevin, claude, aria.",
        )
        type: Optional[str] = Field(
            default=None,
            description="Filter by conflict type (e.g. 'capability_gap', 'version_drift').",
        )
        case_id: Optional[str] = Field(
            default=None,
            description="Read one specific case in full detail.",
        )

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        from sovereign_agent.diagnosis import ConflictCatalog, Conflict, Diagnosis, Resolution

        data_dir = SETTINGS.paths.data_dir
        if data_dir is None:
            return ToolResult(ok=False, error="data_dir not configured")

        catalog = ConflictCatalog(data_dir)
        cases_dir = Path(data_dir) / "cases"

        if not cases_dir.exists():
            return ToolResult(
                ok=True,
                output="No conflicts logged yet. The catalog is empty.",
                metadata={"count": 0},
            )

        # ── single case ────────────────────────────────────────────────────
        if args.case_id:
            conflict = catalog.get_conflict(args.case_id)
            if conflict is None:
                return ToolResult(ok=False, error=f"case not found: {args.case_id!r}")
            diagnosis = catalog.get_diagnosis(args.case_id)
            resolution = catalog.get_resolution(args.case_id)
            timeline = catalog.timeline(args.case_id)

            lines = [
                f"═══ Case {args.case_id} ═══",
                f"Type:    {conflict.type}",
                f"Actor:   {conflict.actor}",
                f"Trigger: {conflict.trigger_event}",
                f"Opened:  {conflict.created_at}",
            ]
            if diagnosis:
                lines += [
                    "",
                    "─── Diagnosis ───",
                    f"Symptom/Cause: {diagnosis.symptom_vs_cause}",
                    f"Root Cause:    {diagnosis.root_cause}",
                    f"Confidence:    {diagnosis.confidence:.0%}",
                ]
            if resolution:
                lines += [
                    "",
                    "─── Resolution ───",
                    f"Fix applied:   {resolution.fix_applied}",
                    f"Rollback plan: {resolution.rollback_plan}",
                    f"Verified:      {'yes' if resolution.verified else 'no'}",
                    f"Policy change: {'yes' if resolution.policy_change_triggered else 'no'}",
                ]
            if timeline:
                lines += ["", "─── Timeline ───"]
                for event in timeline:
                    lines.append(f"  [{event.get('ts', '?')}] {event.get('event_type', '?')} — {event.get('note', '')}")

            return ToolResult(
                ok=True,
                output="\n".join(lines),
                metadata={"case_id": args.case_id},
            )

        # ── list cases ─────────────────────────────────────────────────────
        case_dirs = sorted(cases_dir.iterdir(), reverse=True) if cases_dir.exists() else []
        cases = []
        for cd in case_dirs:
            if not cd.is_dir():
                continue
            case_id = cd.name
            conflict = catalog.get_conflict(case_id)
            if conflict is None:
                continue
            if args.actor and conflict.actor != args.actor.lower():
                continue
            if args.type and conflict.type != args.type:
                continue
            diagnosis = catalog.get_diagnosis(case_id)
            resolution = catalog.get_resolution(case_id)
            cases.append((conflict, diagnosis, resolution))
            if len(cases) >= args.limit:
                break

        if not cases:
            return ToolResult(
                ok=True,
                output="No matching catalog entries.",
                metadata={"count": 0, "filters": {"actor": args.actor, "type": args.type}},
            )

        lines = [f"Conflict Catalog — {len(cases)} entries (newest first)"]
        for conflict, diagnosis, resolution in cases:
            status = "resolved" if resolution else ("diagnosed" if diagnosis else "open")
            lines.append(
                f"\n[{conflict.case_id}] {conflict.type} | {conflict.actor} | {status}"
            )
            lines.append(f"  Trigger: {conflict.trigger_event[:100]}")
            if diagnosis:
                lines.append(f"  Cause:   {diagnosis.root_cause[:100]}")
            if resolution:
                lines.append(f"  Fix:     {resolution.fix_applied[:100]}")

        return ToolResult(
            ok=True,
            output="\n".join(lines),
            metadata={
                "count": len(cases),
                "filters": {"actor": args.actor, "type": args.type},
            },
        )
