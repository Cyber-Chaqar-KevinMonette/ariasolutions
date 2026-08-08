"""
schedule_tool.py — Tier 1: schedule a recurring directive from the agent loop

Wraps ScheduleStore.add() so Aria can propose new scheduled tasks during
a session. The schedule is stored in config_dir/schedule.yaml and
checked on every busy-loop _drain_iteration().
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from .base import Tool, ToolResult


class ScheduleTaskTool(Tool):
    """Add a named recurring schedule entry (cron-style) to schedule.yaml.

    The schedule is checked on each busy-loop cycle. When due, the directive
    is injected into the backlog as a task.

    Cron format — 5 fields (min hour dom mon dow):
      "0 8 * * *"    — daily at 08:00 UTC
      "0 9 * * 1"    — every Monday at 09:00 UTC
      "*/30 * * * *" — every 30 minutes

    Supported: *, */N, exact integer. No ranges or comma-lists.

    Args:
      name        — unique identifier for this schedule (kebab-case)
      directive   — the goal text to inject into the backlog when due
      cron        — 5-field cron expression
      description — human-readable explanation (optional)

    FAILURE MODES: invalid_cron, write_error, schedule_store_unavailable.
    """

    name = "schedule_task"
    tier = 1
    description = (
        "Add a recurring scheduled directive to schedule.yaml. "
        "Args: name (str kebab-case), directive (str — goal text), "
        "cron (str — '0 8 * * *' format, 5 fields), description (str). "
        "FAILURE MODES: invalid_cron, write_error, schedule_store_unavailable."
    )
    failure_modes = ("invalid_cron", "write_error", "schedule_store_unavailable")

    class Args(BaseModel):
        name: str = Field(description="Unique schedule name (kebab-case, e.g. 'daily-sentinel-scan').")
        directive: str = Field(description="Goal text injected into the backlog when due.")
        cron: str = Field(description="5-field cron: 'min hour dom mon dow' (e.g. '0 8 * * *').")
        description: str = Field(default="", description="Human-readable explanation.")

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        if not args.name.strip():
            return ToolResult(ok=False, error="name must not be empty")
        if not args.directive.strip():
            return ToolResult(ok=False, error="directive must not be empty")

        cron = args.cron.strip()
        if len(cron.split()) != 5:
            return ToolResult(
                ok=False,
                error=f"invalid cron {cron!r} — must be 5 fields: 'min hour dom mon dow'",
            )

        try:
            from sovereign_agent.schedule import ScheduleEntry, ScheduleStore, _schedule_path
        except ImportError as exc:
            return ToolResult(ok=False, error=f"schedule module not available: {exc!r}")

        try:
            entry = ScheduleEntry(
                name=args.name.strip(),
                cron=cron,
                directive=args.directive.strip(),
                description=args.description,
                enabled=True,
            )
            store = ScheduleStore(_schedule_path())
            store.add(entry)
        except Exception as exc:
            return ToolResult(ok=False, error=f"write error: {exc!r}")

        return ToolResult(
            ok=True,
            output=(
                f"Schedule added: {args.name}\n"
                f"  cron: {cron}\n"
                f"  directive: {args.directive}\n"
                f"  {args.description or '(no description)'}\n"
                f"  This will fire on the next matching busy-loop cycle."
            ),
            metadata={"name": args.name, "cron": cron},
        )
