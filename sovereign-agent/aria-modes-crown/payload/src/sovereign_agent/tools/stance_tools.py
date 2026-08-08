"""tools/stance_tools.py — her inner stances + the observatory read.
(FABLE II · M6 · modes-crown-d)

Two Tier-0 tools:
  set_stance   T0 — declare an inner working stance (planning, thinking,
                    auditing, scoping, horizon, verifying, cool-down) or
                    clear it. Stances never touch authority or the
                    operator's mode — they are observable posture, and
                    cool-down pauses NEW goal dispatches only.
  observatory  T0 — read the watching window's data: mode + lease,
                    stance trail, emotion surface, mechanical load.

FAILURE MODES (set_stance):  unknown_stance, write_error
FAILURE MODES (observatory): read_error
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from .base import Tool, ToolResult


class SetStanceTool(Tool):
    """Declare (or clear) Aria's inner working stance.

    A stance is a posture, not a mode: Tier 0 by construction, it never
    widens authority and never changes the operator's mode. Every change
    is an inner-stance-d event and a history line the observatory shows.
    cool-down is the one stance with a tooth: while cooling down, the
    bridge refuses NEW goals (the running one finishes untouched).

    FAILURE MODES: unknown_stance, write_error
    """

    name = "set_stance"
    tier = 0
    cacheable = False   # declaring a stance is a WRITE — never serve it stale
    description = (
        "Declare your inner working stance: planning | thinking | auditing "
        "| scoping | horizon | verifying | cool-down — or '' to clear. "
        "Observable posture only; never changes the operator's mode. "
        "cool-down pauses NEW goal dispatches until you step out. "
        "Args: stance, note (optional why). "
        "FAILURE MODES: unknown_stance, write_error"
    )
    failure_modes = ("unknown_stance", "write_error")

    class Args(BaseModel):
        stance: str = Field(description="One of the safe stances, or '' to clear.")
        note: str = Field(default="", description="Optional one-line why.")

    async def execute(self, args: "SetStanceTool.Args", *, trace_id: str) -> ToolResult:
        from sovereign_agent.modes_crown.stances import set_stance

        try:
            rec = set_stance(args.stance, note=args.note, actor="aria")
        except ValueError as exc:
            return ToolResult(ok=False, output="", error=f"unknown_stance: {exc}")
        except OSError as exc:
            return ToolResult(ok=False, output="", error=f"write_error: {exc}")
        stance = rec.get("stance") or "(cleared)"
        return ToolResult(
            ok=True,
            output=f"stance → {stance}"
                   + (f" — {args.note}" if args.note else ""),
            metadata={"stance": stance, "prior": rec.get("prior", "")},
        )


class ObservatoryTool(Tool):
    """Read the observatory: mode + lease, stance trail, emotion surface,
    mechanical load. The same data the operator's watching window shows —
    she and Kevin look through the same glass.

    FAILURE MODES: read_error
    """

    name = "observatory"
    tier = 0
    cacheable = False   # a watching window served stale is a lying window
    description = (
        "Read the observatory window data: current mode and lease "
        "remaining, inner stance and its trail, emotion surface, and the "
        "mechanical load read (queue depth, blocked ratio, lease pressure). "
        "No args. FAILURE MODES: read_error"
    )
    failure_modes = ("read_error",)

    class Args(BaseModel):
        pass

    async def execute(self, args: "ObservatoryTool.Args", *, trace_id: str) -> ToolResult:
        try:
            from sovereign_agent.modes_crown.observatory import gather_observatory

            data = gather_observatory()
        except Exception as exc:  # noqa: BLE001
            return ToolResult(ok=False, output="", error=f"read_error: {exc}")
        lease = (f" · lease {data['lease_remaining_s'] // 60}m left"
                 if data.get("lease_seconds") else "")
        return ToolResult(
            ok=True,
            output=(f"mode {data['mode']}{lease} · stance {data['stance']} · "
                    f"mood {data.get('emotion_mood') or '?'} · "
                    f"queue {data['stress'].get('queue_depth', 0)}"),
            metadata=data,
        )
