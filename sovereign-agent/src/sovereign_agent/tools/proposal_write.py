"""proposal_write — Tier 0. Record a structured proposal in the proposal store.

This is how the orchestrator participates in the self-reflection loop.
During a ``palace-reflect`` step, the model receives a section of the
palace understanding (orphans, duplicates, suspicion, distribution) and
calls this tool to write proposals — never to mutate the palace directly.

Each proposal lands in 'pending' state. The operator reviews via
``sovereign proposals list`` / ``sovereign proposals show``, then approves
selectively via ``sovereign proposals approve <id>``.

Approved proposals are executed by the ``palace-apply`` planner, which
re-verifies the HMAC signature at execution time as defense-in-depth.

This tool is **always available to the agent** but most useful in
reflection contexts. Authority tier 0 because writing a proposal does
not change any palace state — it just files a suggestion.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .base import Tool, ToolResult


_VALID_KINDS = ("reorganize", "insight", "enhancement", "clean")


class _Args(BaseModel):
    kind: Literal["reorganize", "insight", "enhancement", "clean"] = Field(
        description=(
            "Type of proposal. 'clean' = remove/invalidate stale data. "
            "'reorganize' = restructure existing data (e.g., merge entities). "
            "'insight' = additive observation worth recording. "
            "'enhancement' = roadmap-style improvement note."
        ),
    )
    title: str = Field(
        min_length=1, max_length=200,
        description="One-line summary shown in proposal lists.",
    )
    rationale: str = Field(
        default="", max_length=2000,
        description="Why this change is being proposed. Be concrete.",
    )
    action: dict = Field(
        description=(
            "Structured payload describing the change. Schema depends on kind:\n"
            "- clean+remove_triple: {type:'remove_triple', triple_id:'...'}\n"
            "- clean+remove_closet: {type:'remove_closet', closet_id:'...'}\n"
            "- reorganize+merge_entities: {type:'merge_entities', canonical_id:'...', duplicate_ids:[...]}\n"
            "- insight+record: {type:'record', text:'...', related_entities:[...]}\n"
            "- enhancement+note: {type:'note', title:'...', body:'...'}"
        ),
    )
    notes: str = Field(default="", max_length=2000)


class ProposalWriteTool(Tool[_Args]):
    name = "proposal_write"
    tier = 0
    description = (
        "Record a structured proposal in the proposal store for the operator "
        "to review. Does NOT change palace state. The proposal lands in "
        "'pending' status; the operator approves before any change applies. "
        "FAILURE MODES: invalid_kind; invalid_action_schema; storage_error."
    )
    failure_modes = (
        "invalid_kind",
        "invalid_action_schema",
        "storage_error",
    )
    Args = _Args

    async def execute(self, args: _Args, *, trace_id: str) -> ToolResult:  # noqa: ARG002
        # Validate the (kind, action.type) pair maps to something we can apply.
        # If not, refuse — recording proposals we can't execute creates pending
        # backlog that the operator can't make use of.
        from ..planners.palace_apply import supported_action_types

        action_type = args.action.get("type", "")
        if not action_type:
            return ToolResult(
                ok=False,
                error="action must include 'type' key",
            )

        valid = supported_action_types()
        if (args.kind, action_type) not in valid:
            return ToolResult(
                ok=False,
                error=(
                    f"unsupported (kind, action.type) pair: ({args.kind!r}, {action_type!r}). "
                    f"Supported pairs: {valid}"
                ),
            )

        try:
            from ..proposals import open_store
            store = open_store()
            store.ensure_root()
            proposal = store.create(
                kind=args.kind,
                title=args.title,
                rationale=args.rationale,
                action=args.action,
                source=f"trace:{trace_id}",
                notes=args.notes,
            )
        except Exception as e:  # noqa: BLE001
            return ToolResult(ok=False, error=f"storage_error: {type(e).__name__}: {e}")

        return ToolResult(
            ok=True,
            output=proposal.id,
            metadata={
                "proposal_id": proposal.id,
                "kind": proposal.kind,
                "status": proposal.status,
            },
        )
