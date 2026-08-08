"""
compression.py — High-leverage context compression (M36).

Compresses a session's event list into a value-preserving summary atom.
The algorithm classifies events by leverage:

  HIGH VALUE (always preserve as-is):
    commit-d, decision-d, workflow-create-d, blocked-x, lesson-d,
    context-compressed-d, plan-approval-d, mode-switch-d

  MEDIUM (preserve with summary only — strip payload):
    model-d, *-d success events with artifacts, workflow-step-d

  LOW (compress — just count):
    token-usage-d, tool-start-d, cache-hit-d, ingest-d, llm-retry-d,
    budget-d

The result is a CompressedContext containing the summary string, counts,
and the preserved high-value events. Writing this to atoms gives future
sessions a compact, meaningful context.

NOTE: No events are deleted. Compression writes a NEW summary atom.
      The original events remain in events.db for auditing.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Flags that carry the highest signal — always preserved verbatim
_HIGH_VALUE: frozenset[str] = frozenset({
    "commit-d",
    "decision-d",
    "workflow-create-d",
    "blocked-x",
    "lesson-d",
    "context-compressed-d",
    "plan-approval-d",
    "mode-switch-d",
    "objective-added-d",
    "hypothesis-d",
    "circuit-open-x",
})

# Flags that carry medium signal — preserve summary line only
_MEDIUM_VALUE: frozenset[str] = frozenset({
    "model-d",
    "workflow-step-d",
    "workflow-complete-d",
    "settle-d",
    "poison-d",
    "tool-start-d",  # if it has artifacts
})

# Flags that are low signal — just count them
_LOW_VALUE: frozenset[str] = frozenset({
    "token-usage-d",
    "cache-hit-d",
    "ingest-d",
    "llm-retry-d",
    "budget-d",
    "observatory-d",
})


@dataclass
class CompressedContext:
    """Result of compressing a session's events."""
    summary: str
    preserved_count: int
    compressed_count: int
    low_count: int
    tokens_saved_estimate: int
    high_value_events: list[dict] = field(default_factory=list)


def compress_events(
    events: list[dict[str, Any]],
    preserve_tags: set[str] | None = None,
    min_age_seconds: int = 300,
) -> CompressedContext:
    """Compress a list of event dicts into a summary.

    Args:
        events: list of event dicts, each with at least {"flag": str, "payload": dict}
        preserve_tags: additional flags to treat as HIGH_VALUE
        min_age_seconds: events newer than this are never compressed (safety margin)

    Returns:
        CompressedContext with summary text and statistics.
    """
    import time
    now = time.time()
    high = _HIGH_VALUE | (preserve_tags or set())

    high_value: list[dict] = []
    medium_lines: list[str] = []
    low_counts: dict[str, int] = {}
    too_recent: list[dict] = []
    compressed_count = 0
    low_count = 0

    for event in events:
        flag = event.get("flag", "")
        payload = event.get("payload", {})
        ts = event.get("created_at") or event.get("ts") or 0

        # Never compress recent events
        if ts and (now - float(ts)) < min_age_seconds:
            too_recent.append(event)
            continue

        if flag in high:
            high_value.append(event)
        elif flag in _MEDIUM_VALUE:
            # Summarize to one line
            summary_line = _summarize_medium(flag, payload)
            medium_lines.append(summary_line)
            compressed_count += 1
        else:
            # Low value — just count
            low_counts[flag] = low_counts.get(flag, 0) + 1
            low_count += 1
            compressed_count += 1

    # Build summary text
    parts: list[str] = []

    if high_value:
        parts.append("=== HIGH-VALUE EVENTS (preserved verbatim) ===")
        for ev in high_value:
            parts.append(f"[{ev.get('flag', '?')}] {_brief(ev.get('payload', {}))}")

    if medium_lines:
        parts.append("\n=== MEDIUM-VALUE EVENTS (summaries) ===")
        parts.extend(medium_lines)

    if low_counts:
        parts.append("\n=== COMPRESSED COUNTS ===")
        for flag, count in sorted(low_counts.items()):
            parts.append(f"  {flag}: {count}×")

    if too_recent:
        parts.append(f"\n(+{len(too_recent)} recent events not compressed)")

    summary = "\n".join(parts) if parts else "(no compressible events)"

    # Rough token estimate: average event ~150 tokens; compressed to ~10 tokens
    tokens_saved_estimate = max(0, (low_count * 150) + (len(medium_lines) * 100) - len(summary) // 4)

    return CompressedContext(
        summary=summary,
        preserved_count=len(high_value),
        compressed_count=compressed_count,
        low_count=low_count,
        tokens_saved_estimate=tokens_saved_estimate,
        high_value_events=high_value,
    )


def compression_opportunity_score(events: list[dict[str, Any]]) -> float:
    """Return 0.0–1.0 score for how much compression would help.

    High score = lots of low-value events crowding out high-value ones.
    """
    if not events:
        return 0.0
    total = len(events)
    low = sum(1 for e in events if e.get("flag", "") in _LOW_VALUE)
    medium = sum(1 for e in events if e.get("flag", "") in _MEDIUM_VALUE)
    compressible = low + medium
    return round(compressible / total, 3)


# ── Internal helpers ──────────────────────────────────────────────────────────

def _summarize_medium(flag: str, payload: dict) -> str:
    if flag == "model-d":
        model = payload.get("model", "?")
        kind = payload.get("kind", "?")
        return f"  model-d: {model} [{kind}]"
    if flag == "workflow-step-d":
        wid = payload.get("workflow_id", "?")
        step = payload.get("step_title", "?")
        ok = payload.get("succeeded", "?")
        return f"  workflow-step-d: {wid}/{step} → {'ok' if ok else 'failed'}"
    if flag in ("settle-d", "poison-d"):
        return f"  {flag}: {payload.get('outcome', '?')}"
    return f"  {flag}: {_brief(payload)}"


def _brief(payload: dict, max_chars: int = 100) -> str:
    """Return a short string representation of a payload dict."""
    text = str(payload)
    return text[:max_chars] + "..." if len(text) > max_chars else text


__all__ = ["CompressedContext", "compress_events", "compression_opportunity_score"]
