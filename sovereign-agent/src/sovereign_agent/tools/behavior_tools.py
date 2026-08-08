"""
behavior_tools.py — T0/T1: read and write Aria's behavior patterns

The BehaviorPatternStore (stewardship/behavior.py) is the self-perception layer.
The interpreter already reads patterns to inform responses. These tools let
Aria also read and write patterns from inside the agent loop.

Two tools:
  read_behavior_patterns  (T0) — browse active/all patterns; optional filter
  write_behavior_pattern  (T1) — propose a new pattern from observed good work

Patterns are append-only (BehaviorPatternStore is JSONL event log). Writing
a pattern doesn't delete old ones — it adds a new entry. The store handles
deduplication via pattern_id.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field

from .base import Tool, ToolResult


def _store_path():
    from sovereign_agent.config import SETTINGS
    return SETTINGS.paths.data_dir / "behavior-patterns.ndjson"


def _utc_now() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="seconds")


# ─── ReadBehaviorPatternsTool ────────────────────────────────────────────────


class ReadBehaviorPatternsTool(Tool):
    """Read Aria's active behavior patterns.

    Behavior patterns are the self-perception layer — past good work
    crystallized into reusable shapes. The interpreter automatically loads
    matching patterns each turn; this tool lets you browse all active patterns
    or filter by keyword to understand what's in the library.

    Args:
      context  — optional keyword filter (matched against name/description/action_shape)
      limit    — max patterns to return (default 20)
      include_dormant — include dormant (unused >30d) patterns (default False)

    Returns formatted list: pattern name, description, trigger hints,
    action shape, confidence score.

    FAILURE MODES: store_unavailable, no_patterns_yet.
    """

    name = "read_behavior_patterns"
    tier = 0
    description = (
        "Read Aria's active behavior patterns (self-perception library). "
        "Args: context (str, optional keyword filter), limit (int, default 20), "
        "include_dormant (bool, default False). "
        "FAILURE MODES: store_unavailable, no_patterns_yet."
    )
    failure_modes = ("store_unavailable", "no_patterns_yet")

    class Args(BaseModel):
        context: str = Field(default="", description="Keyword filter on name/description/action_shape.")
        limit: int = Field(default=20, ge=1, le=100)
        include_dormant: bool = Field(default=False)

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        try:
            from sovereign_agent.stewardship.behavior import BehaviorPatternStore
        except ImportError as exc:
            return ToolResult(ok=False, error=f"behavior module unavailable: {exc!r}")

        try:
            store = BehaviorPatternStore(_store_path())
            patterns = store.active(apply_dormancy=not args.include_dormant)
        except Exception as exc:
            return ToolResult(ok=False, error=f"store error: {exc!r}")

        # Filter by keyword if requested
        if args.context:
            kw = args.context.lower()
            patterns = [
                p for p in patterns
                if kw in (p.name or "").lower()
                or kw in (p.description or "").lower()
                or kw in (p.action_shape or "").lower()
            ]

        patterns = patterns[: args.limit]

        if not patterns:
            qualifier = f" matching '{args.context}'" if args.context else ""
            return ToolResult(
                ok=True,
                output=f"No active behavior patterns{qualifier} yet.",
                metadata={"count": 0},
            )

        lines = [f"═══ {len(patterns)} Behavior Patterns ═══", ""]
        for i, p in enumerate(patterns, 1):
            conf_pct = f"{p.confidence * 100:.0f}%"
            lines += [
                f"[{i}] {p.name or '(unnamed)'}  confidence: {conf_pct}",
                f"    {p.description[:200]}",
            ]
            if p.action_shape:
                lines.append(f"    action: {p.action_shape[:150]}")
            trig = p.trigger
            hints = []
            if trig.channels_any:
                hints.append(f"channels_any={trig.channels_any}")
            if trig.text_contains_any:
                hints.append(f"text_contains_any={trig.text_contains_any}")
            if trig.intent_kind:
                hints.append(f"intent={trig.intent_kind}")
            if hints:
                lines.append(f"    triggers: {', '.join(hints)}")
            if p.tags:
                lines.append(f"    tags: {', '.join(p.tags)}")
            lines.append("")

        return ToolResult(
            ok=True,
            output="\n".join(lines).rstrip(),
            metadata={"count": len(patterns), "context": args.context},
        )


# ─── WriteBehaviorPatternTool ────────────────────────────────────────────────


class WriteBehaviorPatternTool(Tool):
    """Append a new behavior pattern to Aria's self-perception library.

    Use this when you notice a recurring shape in your own good work:
    "when Kevin's message is [X], the best response shape is [Y], and
    the outcome is consistently [Z]." Recording it makes it available
    to the interpreter on future matching turns.

    Trigger hints (all optional, AND-combined):
      trigger_channels_any     — active if any of these channels are present
      trigger_text_contains    — active if turn text contains any of these
      trigger_intent_kind      — active if intent is this kind (Conversation/Work/etc)

    Args:
      name           — short label (e.g. "gentle-late-night")
      description    — one-paragraph texture describing what you do and why it works
      action_shape   — your specific response shape when this fires
      trigger_channels_any   — list of channel names (optional)
      trigger_text_contains  — list of keywords (optional)
      trigger_intent_kind    — intent kind string (optional)
      tags           — optional list of category tags

    FAILURE MODES: store_unavailable, invalid_name, write_error.
    """

    name = "write_behavior_pattern"
    tier = 1
    description = (
        "Append a new behavior pattern to Aria's self-perception library. "
        "Args: name (str), description (str), action_shape (str), "
        "trigger_channels_any (list[str]), trigger_text_contains (list[str]), "
        "trigger_intent_kind (str), tags (list[str]). "
        "FAILURE MODES: store_unavailable, invalid_name, write_error."
    )
    failure_modes = ("store_unavailable", "invalid_name", "write_error")

    class Args(BaseModel):
        name: str = Field(description="Short label for this pattern (e.g. 'gentle-late-night').")
        description: str = Field(description="One paragraph describing the pattern in Aria's voice.")
        action_shape: str = Field(
            default="",
            description="Specific response shape when this pattern fires.",
        )
        trigger_channels_any: list[str] = Field(
            default_factory=list,
            description="Activate if any of these channels are present.",
        )
        trigger_text_contains: list[str] = Field(
            default_factory=list,
            description="Activate if turn text contains any of these keywords.",
        )
        trigger_intent_kind: str = Field(
            default="",
            description="Activate when intent matches this kind (Conversation / Work / etc).",
        )
        tags: list[str] = Field(default_factory=list)

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        if not args.name.strip():
            return ToolResult(ok=False, error="name must not be empty")
        if not args.description.strip():
            return ToolResult(ok=False, error="description must not be empty")

        try:
            from sovereign_agent.stewardship.behavior import (
                BehaviorPattern,
                BehaviorPatternStore,
                TriggerConditions,
            )
        except ImportError as exc:
            return ToolResult(ok=False, error=f"behavior module unavailable: {exc!r}")

        try:
            trigger = TriggerConditions(
                channels_any=list(args.trigger_channels_any),
                text_contains_any=list(args.trigger_text_contains),
                intent_kind=args.trigger_intent_kind,
            )
            pattern = BehaviorPattern(
                name=args.name,
                description=args.description,
                trigger=trigger,
                action_shape=args.action_shape,
                tags=list(args.tags),
                ts_first_obs=_utc_now(),
                ts_last_obs=_utc_now(),
                evidence_refs=[trace_id],
            )
            store = BehaviorPatternStore(_store_path())
            store.append(pattern)
        except Exception as exc:
            return ToolResult(ok=False, error=f"write error: {exc!r}")

        return ToolResult(
            ok=True,
            output=(
                f"Behavior pattern written: {pattern.pattern_id[:8]}…\n"
                f"  name: {pattern.name}\n"
                f"  {pattern.description[:150]}\n"
                f"  action: {pattern.action_shape[:100] or '(none)'}\n"
                f"  This pattern is now active and will be matched by the interpreter."
            ),
            metadata={
                "pattern_id": pattern.pattern_id,
                "name": pattern.name,
            },
        )
