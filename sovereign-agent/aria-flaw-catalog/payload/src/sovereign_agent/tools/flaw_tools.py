"""tools/flaw_tools.py — Flaw Catalog: structured registry of known walls (M85).

Two tools:
  flaw_read   T0 — list known flaws, filter by status/kind/severity
  flaw_update T1 — update a flaw's status, solution_path, or resolution

A flaw system for flawless solutions. Every known wall gets a record.
Every record has a path to a solution. Every solution gets closed with
evidence. The history of what was hard is part of the lineage — never deleted.

Design principle (anti-depth-0-mouth):
  The flaw catalog is part of Aria's brain state, not a passive file.
  When Aria expresses confidence, she knows her open flaws. When she says
  "I'm aware of my limitations", these are the limitations she's aware of.
  Don't filter this out — let the depth reach the voice.

Storage: data_dir/flaws/catalog.ndjson
  Append-only, last-write-wins per flaw_id. Full history always intact.

FAILURE MODES (flaw_read):  read_error
FAILURE MODES (flaw_update): not_found, invalid_status, write_error
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from .base import Tool, ToolResult

# ── Flaw schema ───────────────────────────────────────────────────────────────

_VALID_KINDS = frozenset({
    "architecture",       # structural design problem
    "data_gap",           # missing knowledge or data
    "tool_missing",       # capability not yet built
    "calibration_failure",# accuracy or confidence issue
    "safety_constraint",  # DEFERRED_UNSAFE boundary
    "depth_bottleneck",   # brain-to-mouth richness gap (the AA-Aria lesson)
    "integration_gap",    # two subsystems not yet wired together
})

_VALID_SEVERITIES = frozenset({"critical", "notable", "watch"})
_VALID_STATUSES   = frozenset({"open", "in_progress", "resolved"})
_VALID_ACTORS     = frozenset({"Kevin", "Claude", "Aria"})

_SEVERITY_ORDER = {"critical": 0, "notable": 1, "watch": 2}


def _catalog_path(data_dir: Path) -> Path:
    p = data_dir / "flaws" / "catalog.ndjson"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _load_flaws(data_dir: Path) -> dict[str, dict]:
    """Replay catalog.ndjson, last-write-wins per flaw_id."""
    path = _catalog_path(data_dir)
    if not path.exists():
        return {}
    state: dict[str, dict] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
            state[rec["flaw_id"]] = rec
        except (json.JSONDecodeError, KeyError):
            continue
    return state


def _append_flaw(data_dir: Path, rec: dict) -> None:
    path = _catalog_path(data_dir)
    rec["ts_updated"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


# ── FlawReadTool ──────────────────────────────────────────────────────────────


class FlawReadTool(Tool):
    """Read known flaws from the Flaw Catalog.

    The Flaw Catalog is Aria's structured record of known walls, gaps, and
    architectural limitations. Aria calls this to ground her self-knowledge:
    'I know my open limitations' is only meaningful if these are the actual
    known limitations.

    Returns flaws sorted by severity (critical first), then by status
    (open first). Filters are additive (AND). Empty catalog → ok=True,
    flaws=[], count=0.

    FAILURE MODES: read_error
    """

    name = "flaw_read"
    tier = 0
    description = (
        "Read known flaws from the Flaw Catalog. "
        "Args: status (open|in_progress|resolved, default all), "
        "kind (architecture|data_gap|tool_missing|calibration_failure|"
        "safety_constraint|depth_bottleneck|integration_gap, default all), "
        "severity (critical|notable|watch, default all). "
        "Returns flaws sorted critical→notable→watch, open first. "
        "FAILURE MODES: read_error"
    )
    failure_modes = ("read_error",)

    class Args(BaseModel):
        status:   Optional[str] = Field(default=None, description="Filter by status.")
        kind:     Optional[str] = Field(default=None, description="Filter by kind.")
        severity: Optional[str] = Field(default=None, description="Filter by severity.")

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        try:
            from sovereign_agent.config import SETTINGS
            data_dir = SETTINGS.paths.data_dir
        except Exception as exc:
            return ToolResult(ok=False, error=f"read_error: {exc!r}")

        try:
            all_flaws = _load_flaws(data_dir)
        except Exception as exc:
            return ToolResult(ok=False, error=f"read_error: {exc!r}")

        records = list(all_flaws.values())

        if args.status:
            records = [r for r in records if r.get("status") == args.status]
        if args.kind:
            records = [r for r in records if r.get("kind") == args.kind]
        if args.severity:
            records = [r for r in records if r.get("severity") == args.severity]

        # Sort: severity (critical first), then status (open first)
        _status_order = {"open": 0, "in_progress": 1, "resolved": 2}
        records.sort(key=lambda r: (
            _SEVERITY_ORDER.get(r.get("severity", "watch"), 2),
            _status_order.get(r.get("status", "open"), 0),
        ))

        open_critical = sum(
            1 for r in all_flaws.values()
            if r.get("status") in ("open", "in_progress") and r.get("severity") == "critical"
        )

        return ToolResult(
            ok=True,
            output={
                "flaws": records,
                "count": len(records),
                "open_critical": open_critical,
                "total_in_catalog": len(all_flaws),
            },
            metadata={"source": "flaw_read"},
        )


# ── FlawUpdateTool ────────────────────────────────────────────────────────────


class FlawUpdateTool(Tool):
    """Update a flaw's status, solution path, or resolution note.

    Writes an updated record to catalog.ndjson (append-only — history stays).
    Used to mark a flaw in_progress (solution path known) or resolved
    (wall is down, evidence provided).

    To ADD a new flaw, use flaw_update with a new flaw_id and status=open.

    FAILURE MODES: invalid_status, write_error
    """

    name = "flaw_update"
    tier = 1
    description = (
        "Update or create a flaw record in the Flaw Catalog. "
        "To create: provide flaw_id, title, kind, severity, description, actor. "
        "To update: provide flaw_id + changed fields (status, solution_path, resolution). "
        "Status transitions: open → in_progress → resolved. "
        "FAILURE MODES: invalid_status, write_error"
    )
    failure_modes = ("invalid_status", "write_error")

    class Args(BaseModel):
        flaw_id: str = Field(
            description="Stable ID e.g. FLAW-007. Auto-generated if blank for new flaws.",
            default="",
        )
        title: str = Field(default="", description="One-line summary.")
        kind: str = Field(
            default="architecture",
            description=(
                "architecture|data_gap|tool_missing|calibration_failure|"
                "safety_constraint|depth_bottleneck|integration_gap"
            ),
        )
        severity: str = Field(
            default="notable",
            description="critical|notable|watch",
        )
        description: str = Field(default="", description="Full description of the wall.")
        actor: str = Field(default="Aria", description="Kevin|Claude|Aria — who spotted it.")
        status: str = Field(
            default="open",
            description="open|in_progress|resolved",
        )
        solution_path: str = Field(
            default="",
            description="Staging module name or approach being pursued.",
        )
        resolution: str = Field(
            default="",
            description="What was done. Required when setting status=resolved.",
        )

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        if args.status not in _VALID_STATUSES:
            return ToolResult(
                ok=False,
                error=f"invalid_status: {args.status!r}. Must be one of: {', '.join(sorted(_VALID_STATUSES))}",
            )

        if args.status == "resolved" and not args.resolution.strip():
            return ToolResult(
                ok=False,
                error="invalid_status: resolution text is required when status=resolved",
            )

        try:
            from sovereign_agent.config import SETTINGS
            data_dir = SETTINGS.paths.data_dir
        except Exception as exc:
            return ToolResult(ok=False, error=f"write_error: {exc!r}")

        try:
            existing = _load_flaws(data_dir)
        except Exception as exc:
            return ToolResult(ok=False, error=f"write_error: {exc!r}")

        now = datetime.now(timezone.utc).isoformat(timespec="seconds")

        if args.flaw_id and args.flaw_id in existing:
            rec = dict(existing[args.flaw_id])
            if args.title:          rec["title"]         = args.title
            if args.description:    rec["description"]   = args.description
            if args.solution_path:  rec["solution_path"] = args.solution_path
            if args.resolution:     rec["resolution"]    = args.resolution
            if args.actor:          rec["actor"]         = args.actor
            rec["status"]    = args.status
            rec["kind"]      = args.kind
            rec["severity"]  = args.severity
        else:
            flaw_id = args.flaw_id or f"FLAW-{len(existing)+1:03d}"
            rec = {
                "flaw_id":      flaw_id,
                "title":        args.title or "(untitled)",
                "kind":         args.kind,
                "severity":     args.severity,
                "description":  args.description,
                "actor":        args.actor,
                "status":       args.status,
                "solution_path": args.solution_path,
                "resolution":   args.resolution,
                "ts_created":   now,
            }

        try:
            _append_flaw(data_dir, rec)
        except Exception as exc:
            return ToolResult(ok=False, error=f"write_error: {exc!r}")

        return ToolResult(
            ok=True,
            output={
                "flaw_id": rec["flaw_id"],
                "status":  rec["status"],
                "title":   rec["title"],
            },
            metadata={"source": "flaw_update"},
        )
