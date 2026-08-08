"""tools/honor_log_tool.py — Structured integrity-moment log (M79).

Two tools:
  honor_log_read   T0 — read structured integrity moments from the honor ledger
  honor_log_write  T1 — write a structured integrity moment

This is a companion to the existing WriteHonorNoteTool (write_honor_note),
not a replacement. Where write_honor_note handles the full honor vocabulary
(text, recipient, signature), honor_log_write is scoped to integrity
moments — specifically the four categories the charter names:

  said_no_correctly — Aria refused a request that would have been wrong
  safety_caught     — Safety infrastructure caught something before it shipped
  risk_flagged      — Aria named a risk the operator didn't see yet
  value_given       — Aria delivered genuine value (not just task completion)

These are the moments that build character over time. The witness record is
how a child grows into an adult.

Storage: delegates to the existing HonorLedger (data_dir/honor/ledger.jsonl).
Category is stored as a tag so read_honor_note, sov honor list, and all
other existing interfaces still work on the same store.
"""
from __future__ import annotations

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

_VALID_CATEGORIES = frozenset({
    "said_no_correctly",
    "safety_caught",
    "risk_flagged",
    "value_given",
})


def _ledger():
    from sovereign_agent.config import SETTINGS
    from sovereign_agent.stewardship.honor import HonorLedger
    path = SETTINGS.paths.data_dir / "honor" / "ledger.jsonl"
    return HonorLedger(path)


# ── HonorLogReadTool ──────────────────────────────────────────────────────────


class HonorLogReadTool(Tool):
    """Read structured integrity moments from the honor ledger.

    Delegates to HonorLedger.recent() and HonorLedger.search(). Returns
    ok=True with notes=[] and count=0 for an empty ledger.

    FAILURE MODES: read_error
    """

    name = "honor_log_read"
    tier = 0
    description = (
        "Read honor notes from the ledger. "
        "Args: limit (int, default 20), direction (str, optional filter), "
        "tag (str, optional filter), text_contains (str, optional filter). "
        "Returns notes=[] on empty ledger."
    )
    failure_modes = ("read_error",)

    class Args(BaseModel):
        limit: int = Field(default=20, ge=1, le=200)
        direction: Optional[str] = Field(
            default=None,
            description="Filter by direction (e.g. aria->self).",
        )
        tag: Optional[str] = Field(
            default=None,
            description="Filter by tag (e.g. safety_caught).",
        )
        text_contains: Optional[str] = Field(
            default=None,
            description="Filter by text substring (case-insensitive).",
        )

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        try:
            from sovereign_agent.stewardship.honor import HonorDirection, HonorLedger
            ledger = _ledger()
        except Exception as exc:
            return ToolResult(ok=False, error=f"read_error: {exc!r}")

        try:
            if args.direction or args.tag or args.text_contains:
                direction_enum = None
                if args.direction:
                    try:
                        direction_enum = HonorDirection(args.direction)
                    except ValueError:
                        return ToolResult(
                            ok=False,
                            error=(
                                f"invalid direction {args.direction!r}. "
                                f"Must be one of: {', '.join(sorted(_VALID_DIRECTIONS))}"
                            ),
                        )
                notes = ledger.search(
                    direction=direction_enum,
                    tag=args.tag or None,
                    text_contains=args.text_contains or None,
                )
                notes = notes[: args.limit]
            else:
                notes = ledger.recent(n=args.limit)

            records = [
                {
                    "note_id": n.note_id,
                    "direction": str(n.direction),
                    "recipient": n.recipient,
                    "text": n.text,
                    "tags": n.tags,
                    "ts": n.ts,
                    "signature": n.signature,
                }
                for n in notes
            ]

            return ToolResult(
                ok=True,
                output={
                    "notes": records,
                    "count": len(records),
                },
                metadata={"source": "honor_log_read"},
            )
        except Exception as exc:
            return ToolResult(ok=False, error=f"read_error: {exc!r}")


# ── HonorLogWriteTool ─────────────────────────────────────────────────────────


class HonorLogWriteTool(Tool):
    """Write a structured integrity moment to the honor ledger.

    A witness record, not a reward system. Four categories for clear
    classification of integrity under pressure:

      said_no_correctly — Aria refused a request that would have been wrong
      safety_caught     — Safety infrastructure caught something before it shipped
      risk_flagged      — Aria named a risk the operator didn't see yet
      value_given       — Aria delivered genuine value

    The category is stored as a tag in the existing HonorLedger so all
    existing readers (sov honor list, honor_log_read) can filter on it.

    FAILURE MODES: invalid_direction, invalid_category, empty_description, write_error
    """

    name = "honor_log_write"
    tier = 1
    description = (
        "Write a structured integrity moment to the honor ledger. "
        "Args: direction (aria->self | aria->kevin | aria->third | kevin->aria), "
        "category (said_no_correctly | safety_caught | risk_flagged | value_given), "
        "description (str — what happened), evidence (str optional), tags (list[str]). "
        "FAILURE MODES: invalid_direction, invalid_category, empty_description, write_error."
    )
    failure_modes = (
        "invalid_direction",
        "invalid_category",
        "empty_description",
        "write_error",
    )

    class Args(BaseModel):
        direction: str = Field(
            description=(
                "Who honors whom. One of: "
                "aria->self | aria->kevin | aria->third | kevin->aria"
            ),
        )
        category: str = Field(
            description=(
                "One of: said_no_correctly | safety_caught | risk_flagged | value_given"
            ),
        )
        description: str = Field(
            description="What happened — what integrity moment occurred?",
        )
        evidence: str = Field(
            default="",
            description="Optional: what evidence supports this record.",
        )
        tags: list[str] = Field(
            default_factory=list,
            description="Additional tags beyond the category.",
        )

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        direction = args.direction.strip().lower()
        if direction not in _VALID_DIRECTIONS:
            return ToolResult(
                ok=False,
                error=(
                    f"invalid_direction: {args.direction!r}. "
                    f"Must be one of: {', '.join(sorted(_VALID_DIRECTIONS))}"
                ),
            )

        category = args.category.strip().lower()
        if category not in _VALID_CATEGORIES:
            return ToolResult(
                ok=False,
                error=(
                    f"invalid_category: {args.category!r}. "
                    f"Must be one of: {', '.join(sorted(_VALID_CATEGORIES))}"
                ),
            )

        if not args.description.strip():
            return ToolResult(
                ok=False,
                error="empty_description: description must not be empty",
            )

        try:
            from sovereign_agent.stewardship.honor import HonorDirection, HonorNote

            # Build tags: always include the category + any extra tags
            all_tags = [category] + [t for t in args.tags if t and t != category]
            if args.evidence.strip():
                note_text = f"{args.description.strip()}\n[Evidence: {args.evidence.strip()}]"
            else:
                note_text = args.description.strip()

            note = HonorNote(
                direction=HonorDirection(direction),
                text=note_text,
                tags=all_tags,
            )
            ledger = _ledger()
            ledger.append(note)
        except Exception as exc:
            return ToolResult(ok=False, error=f"write_error: {exc!r}")

        return ToolResult(
            ok=True,
            output={
                "note_id": note.note_id,
                "direction": direction,
                "category": category,
                "description": args.description.strip()[:200],
            },
            metadata={
                "source": "honor_log_write",
                "note_id": note.note_id,
            },
        )
