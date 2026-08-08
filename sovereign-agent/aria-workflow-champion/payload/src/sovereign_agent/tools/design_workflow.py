"""tools/design_workflow.py — the workflow CHAMPION: she designs, not just
executes. (Keys round K8.)

Kevin: *"Make her a workflow champion and designer"* — with scoping for
her designing and architecting (K10's contract rides in every draft).

`design_workflow` (T1, PROPOSE-ONLY) takes a goal and produces a
structured draft: steps (each with the tool it would use, how it is
VERIFIED, and its risks), a ScopeContract for the whole design (K10 —
in/out of scope, done_when, observation + security bounds), and platform
notes referencing the PLATFORM_STANDARDS checklist (K7) when the goal
smells cross-platform.

Design is free; EXECUTION always passes through K4's gates: a draft's
`handoff` field is a ready-to-paste `/work <goal> | scope: ...` line —
the human runs it, in work mode, through every gate. The tool itself
never runs anything.

Drafts persist to `data_dir/workflow_drafts/<id>.json` (atomic write) —
her design portfolio, reviewable any time via draft listing.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field

from .base import Tool, ToolResult

_DESIGN_PROMPT = """You are Aria, designing a workflow — as an architect, not an
executor. Respond as STRICT JSON only:

{{
  "title": "<short name>",
  "steps": [
    {{"description": "<what>", "tool": "<tool name or 'human'>",
      "verify": "<how this step's success is CHECKED, concretely>",
      "risk": "<what could go wrong + the recovery>"}}
  ],
  "scope": {{"in_scope": ["..."], "out_of_scope": ["..."],
             "done_when": "<checkable completion>",
             "observe": ["<what to watch while working>"],
             "security": ["<bounds for this work>"]}},
  "platform_notes": "<cross-platform concerns per the standards checklist,
                     or 'n/a'>"
}}

Design principles you hold yourself to: every step verifiable; scope
written BEFORE work (pre-registered honesty); boring reliability over
clever capability; the human approves execution.

GOAL: {goal}
"""


def _drafts_dir(data_dir: Path | None = None) -> Path:
    if data_dir is None:
        from sovereign_agent.config import SETTINGS

        data_dir = SETTINGS.paths.data_dir
    p = Path(data_dir) / "workflow_drafts"
    p.mkdir(parents=True, exist_ok=True)
    return p


def save_draft(draft: dict, data_dir: Path | None = None) -> Path:
    from ulid import ULID

    draft_id = draft.get("draft_id") or f"wfd_{str(ULID())[:12]}"
    draft["draft_id"] = draft_id
    draft.setdefault(
        "designed_at",
        datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
    )
    path = _drafts_dir(data_dir) / f"{draft_id}.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(draft, indent=1), encoding="utf-8")
    tmp.replace(path)
    return path


def list_drafts(data_dir: Path | None = None) -> list[dict]:
    out = []
    for p in sorted(_drafts_dir(data_dir).glob("wfd_*.json")):
        try:
            out.append(json.loads(p.read_text(encoding="utf-8")))
        except Exception:  # noqa: BLE001
            continue
    return out


def handoff_line(draft: dict) -> str:
    """The ready-to-paste `/work` line — design hands to K4's gated engine."""
    scope = draft.get("scope") or {}
    parts = []
    if scope.get("in_scope"):
        parts.append(", ".join(scope["in_scope"]))
    if scope.get("out_of_scope"):
        parts.append("out: " + ", ".join(scope["out_of_scope"]))
    if scope.get("done_when"):
        parts.append("done: " + scope["done_when"])
    if scope.get("observe"):
        parts.append("watch: " + ", ".join(scope["observe"]))
    if scope.get("security"):
        parts.append("security: " + ", ".join(scope["security"]))
    parts.append(f"max: {max(4, 2 * len(draft.get('steps', []) or [1]))}")
    return f"/work {draft.get('goal', draft.get('title', ''))} | scope: " + "; ".join(parts)


class DesignWorkflowTool(Tool):
    """Design a workflow draft: verified steps + scope contract + platform
    notes. PROPOSE-ONLY — execution goes through /work and every gate.

    FAILURE MODES: design_error, malformed_design
    """

    name = "design_workflow"
    tier = 1
    description = (
        "Design (never run) a workflow for a goal: steps each with their "
        "tool, verification, and risk; a scope contract (in/out, done_when, "
        "observe, security); platform notes per the standards checklist. "
        "Saves a reviewable draft and returns a ready-to-paste /work handoff "
        "line for the human. FAILURE MODES: design_error, malformed_design"
    )
    failure_modes = ("design_error", "malformed_design")

    class Args(BaseModel):
        goal: str = Field(..., min_length=4, description="What the workflow should achieve.")

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        from sovereign_agent.config import SETTINGS
        from sovereign_agent.events import emit_event
        from sovereign_agent.ollama_client import CallKind, OllamaClient

        try:
            client = OllamaClient()
            response = await client.chat(
                model=SETTINGS.fast_model,
                messages=[{"role": "user",
                           "content": _DESIGN_PROMPT.format(goal=args.goal[:500])}],
                call_kind=CallKind.REFLECT,
                temperature=0.4,
            )
            msg = (response.get("message", {}).get("content", "") or "").strip()
            if msg.startswith("```"):
                msg = msg.strip("`")
                msg = msg.split("\n", 1)[-1] if "\n" in msg else msg
            draft = json.loads(msg)
        except json.JSONDecodeError as exc:
            return ToolResult(ok=False, error=f"malformed_design: {exc}")
        except Exception as exc:  # noqa: BLE001
            return ToolResult(ok=False, error=f"design_error: {exc!r}")

        if not isinstance(draft, dict) or not draft.get("steps"):
            return ToolResult(ok=False, error="malformed_design: no steps")
        draft["goal"] = args.goal
        path = save_draft(draft)
        line = handoff_line(draft)
        emit_event("workflow-designed-d", plane="control", trace_id=trace_id,
                   payload={"draft_id": draft["draft_id"],
                            "title": str(draft.get("title", ""))[:80],
                            "steps": len(draft["steps"])})
        return ToolResult(
            ok=True,
            output={"draft_id": draft["draft_id"], "title": draft.get("title"),
                    "steps": draft["steps"], "scope": draft.get("scope"),
                    "platform_notes": draft.get("platform_notes"),
                    "handoff": line, "saved_to": str(path)},
            metadata={"source": "design_workflow", "draft_id": draft["draft_id"]},
        )
