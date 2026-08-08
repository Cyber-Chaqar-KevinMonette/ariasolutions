"""unverified_claims.py — prove the say-so, don't just print it.

Sourced from reading `long-running-agent-main` (MIT, hardware-liberation
corpus): "never trust the model's say-so, only real test/lint/build/
typecheck results." Aria's subtask completion (`agent_session.py`) marks a
subtask `done` purely from `loop_result.ok` — the model's own verdict on
its own work, with no cross-check against what that subtask's own action
trace shows it actually verified.

This module does NOT change what "done" means — that's a load-bearing
session path deliberately left alone here (mirroring `review_journal`'s own
precedent: ship the library first, touch the session gate as its own
reviewed follow-up). It adds an independent, additive OBSERVABILITY check:
does a subtask's own `result_summary` claim verification ("tests pass",
"all green", "confirmed working"...) that its own trace never actually
performed? If so, flag it plainly in the session review doc, next to the
sentinel warnings — the same grounded-truth standard `scout_verify.py`
already applies to retailer web pages (✓ verified / ⚠ unconfirmed, never a
faked green check), applied here to Aria's own claims about her own work.
"""
from __future__ import annotations

import re
from typing import Any

__all__ = [
    "claims_verification",
    "subtask_verified_by_trace",
    "find_unverified_claims",
    "render_unverified_claims_section",
]

_CLAIM_PATTERNS = [
    re.compile(p, re.I) for p in (
        r"\btests?\s+pass(?:es|ed|ing)?\b",
        r"\ball\s+(?:tests?\s+)?green\b",
        r"\bverified\b",
        r"\bconfirmed\s+working\b",
        r"\bworks?\s+correctly\b",
        r"\bno\s+(?:errors?|failures?)\b",
    )
]

_VERIFY_TOOL_HINTS = ("pytest", "test", "lint", "build", "typecheck", "mypy",
                      "floor_check", "verify")


def claims_verification(text: str) -> bool:
    """Does this text assert something was checked/passing, in the model's
    own words? A plain textual claim, nothing more."""
    if not text:
        return False
    return any(p.search(text) for p in _CLAIM_PATTERNS)


def subtask_verified_by_trace(trace_id: str, actions: list[dict[str, Any]]) -> bool:
    """Did a real verification-shaped tool/command actually run under this
    subtask's own trace? Matches on the action's flag/payload text — never
    trusts the claim itself, only what's independently in the trace."""
    if not trace_id:
        return False
    for a in actions or []:
        if str(a.get("trace_id", "")) != trace_id:
            continue
        haystack = f"{a.get('flag', '')} {a.get('payload', '')}".lower()
        if any(h in haystack for h in _VERIFY_TOOL_HINTS):
            return True
    return False


def find_unverified_claims(
    subtasks: list[dict[str, Any]], actions: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Subtasks whose own result_summary claims verification language but
    whose own action trace shows no matching real check. Best-effort,
    additive — never raises; this is a review-time signal, not a gate."""
    out: list[dict[str, Any]] = []
    for s in subtasks or []:
        summary = s.get("result_summary") or ""
        if not claims_verification(summary):
            continue
        trace_id = s.get("trace_id") or ""
        if subtask_verified_by_trace(trace_id, actions):
            continue
        out.append({
            "subtask_id": s.get("id", "?"),
            "description": s.get("description", ""),
            "claim": summary[:200],
        })
    return out


def render_unverified_claims_section(
    subtasks: list[dict[str, Any]], actions: list[dict[str, Any]]
) -> str:
    """Markdown section for the review README — an honest second check next
    to the sentinel warnings, same grounded-truth standard as
    `scout_verify.py`'s live-page checks, applied to Aria's own claims about
    her own work instead of a retailer's page."""
    findings = find_unverified_claims(subtasks, actions)
    lines = ["## Unverified claims (say-so vs. proof)"]
    if not findings:
        lines.append("- No claim/proof gaps detected — every claim of "
                      "verification in a result summary lines up with a "
                      "real check in that subtask's own trace.")
    else:
        lines.append(f"- {len(findings)} subtask(s) claimed verification "
                      "with no matching check found in their own trace:")
        for f in findings:
            lines.append(f"  - **{f['description']}** — claimed: "
                         f"\"{f['claim']}\"")
    lines.append("")
    return "\n".join(lines)
