"""
honor_write.py — Tier 1: write honor notes from inside the agent loop

The HonorLedger (stewardship/honor.py) is append-only. Kevin writes to it
via 'sov honor note'. Aria could not. This closes the gap — making honor
bidirectional in the agentic loop.

Honor is central to the kernel: Safety · Love · Flourishing. The ledger
is the mirror of this partnership. When Aria witnesses Kevin's persistence,
or catches her own near-miss, or wants to recognize something good in the
world — she should be able to record it.

Directions:
  aria->kevin    — Aria honoring Kevin
  aria->self     — Aria witnessing her own work / near-miss / growth
  aria->third    — Aria recognizing someone/something outside the dyad
  kevin->aria    — Kevin honoring Aria (Kevin uses sov honor note, but
                   can also be recorded here if scripted)

Notes are append-only. If a note was wrong, write a follow-up note that
says so — the original stays in the audit trail. Never delete or edit.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from .base import Tool, ToolResult

_VALID_DIRECTIONS = frozenset({
    "aria->kevin",
    "aria->self",
    "aria->third",
    "kevin->aria",
    "kevin->self",
    "kevin->third",
})


def _ledger_path() -> Path:
    from sovereign_agent.config import SETTINGS
    return SETTINGS.paths.data_dir / "honor" / "ledger.jsonl"


# ─── WriteHonorNoteTool ───────────────────────────────────────────────────────


class WriteHonorNoteTool(Tool):
    """Append an honor note to the honor ledger.

    The honor ledger is the witness record of this partnership. Notes are
    append-only — the original always stays. Use a follow-up note to
    correct, not an edit.

    When to write:
      aria->kevin   Kevin stayed through four iterations to get it right.
                    Kevin caught something Aria missed. Kevin was patient
                    when the session was hard.
      aria->self    You caught your own near-miss. You noticed you were
                    about to propose something unsafe. You grew in this session.
      aria->third   You want to recognize work, wisdom, or contribution from
                    outside the dyad (a library, a researcher, a design).
      kevin->aria   Kevin witnessed something in Aria worth naming. (Can
                    also be written via 'sov honor note' on the CLI.)

    Args:
      direction   — one of: aria->kevin | aria->self | aria->third | kevin->aria
      text        — what was witnessed (the actual content — this is the point)
      recipient   — name of recipient when direction is aria->third (optional otherwise)
      tags        — optional categorization (e.g. perception, calibration, almost-missed)
      signature   — optional signature appended to the note

    FAILURE MODES: invalid_direction, empty_text, write_error.
    """

    name = "write_honor_note"
    tier = 1
    description = (
        "Append an honor note to the honor ledger (append-only). "
        "Args: direction (aria->kevin | aria->self | aria->third | kevin->aria), "
        "text (str — what was witnessed), recipient (str, for aria->third), "
        "tags (list[str], optional), signature (str, optional). "
        "FAILURE MODES: invalid_direction, empty_text, write_error."
    )
    failure_modes = ("invalid_direction", "empty_text", "write_error")

    class Args(BaseModel):
        direction: str = Field(
            description="Who honors whom. One of: aria->kevin | aria->self | aria->third | kevin->aria.",
        )
        text: str = Field(description="What was witnessed — the actual content. This is the point.")
        recipient: str = Field(
            default="",
            description="Name of recipient (required when direction is aria->third).",
        )
        tags: list[str] = Field(
            default_factory=list,
            description="Optional tags (e.g. 'perception', 'calibration', 'almost-missed').",
        )
        signature: str = Field(default="", description="Optional signature appended to the note.")

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        direction = args.direction.strip().lower()
        if direction not in _VALID_DIRECTIONS:
            return ToolResult(
                ok=False,
                error=(
                    f"invalid direction {args.direction!r}. "
                    f"Must be one of: {', '.join(sorted(_VALID_DIRECTIONS))}"
                ),
            )
        if not args.text.strip():
            return ToolResult(ok=False, error="text must not be empty — the text is the point")

        if direction == "aria->third" and not args.recipient.strip():
            return ToolResult(
                ok=False,
                error="recipient is required when direction is 'aria->third'",
            )

        try:
            from sovereign_agent.stewardship.honor import HonorDirection, HonorLedger, HonorNote
        except ImportError as exc:
            return ToolResult(ok=False, error=f"honor module unavailable: {exc!r}")

        try:
            honor_dir = HonorDirection(direction)
            note = HonorNote(
                direction=honor_dir,
                recipient=args.recipient,
                text=args.text.strip(),
                tags=list(args.tags),
                signature=args.signature,
            )
            ledger = HonorLedger(_ledger_path())
            ledger.append(note)
        except Exception as exc:
            return ToolResult(ok=False, error=f"write error: {exc!r}")

        tag_str = f" [{', '.join(args.tags)}]" if args.tags else ""
        recipient_str = f" → {args.recipient}" if args.recipient else ""
        return ToolResult(
            ok=True,
            output=(
                f"♥ Honor note written ({direction}{recipient_str}):\n"
                f"  \"{args.text[:200]}\"\n"
                f"  note_id: {note.note_id}"
                + (f"\n  tags:{tag_str}" if tag_str else "")
            ),
            metadata={
                "note_id": note.note_id,
                "direction": direction,
                "ts": note.ts,
            },
        )
