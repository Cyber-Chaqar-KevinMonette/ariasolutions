"""
session_review.py — Tier 0 tool for Aria to inspect her session state.
(v0.2.42.0)

Gives Aria the ability to ask "what have I done so far?" and "what's
still pending?" mid-execution. This fixes the persistence flakiness where
Aria would rediscover already-solved problems because the cross-subtask
bridge (2000 chars of truncated summary) didn't preserve enough context.

Usage patterns:
  • At the start of a resumed session: call with no args to review all
    completed and pending subtasks before deciding what to do next.
  • Mid-session: call to check progress without stopping.
  • With session_id: review a specific past session.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel

from .base import Tool, ToolResult


class ReadSessionTool(Tool):
    """Return the current session state: goal, subtasks, progress, budgets.

    Shows every subtask with its status (pending/active/done/blocked/skipped),
    result summary, iteration count, and error if any. Also shows session-level
    budget consumption.

    Call this at the start of a resumed session to understand what's been done
    and what remains. Call it mid-session to check your own progress.
    """

    name = "read_session"
    tier = 0
    description = (
        "Return the current session's state: goal, all subtasks with statuses "
        "and result summaries, progress through the queue, and budget usage. "
        "Call this when resuming a session or to review your own progress. "
        "Returns a readable report you can reason from."
    )
    failure_modes = (
        "session_id unknown — returns error if session file not found",
        "sessions directory missing — returns error",
        "json decode error — returns error with path for investigation",
    )

    class Args(BaseModel):
        session_id: Optional[str] = None
        """Session ID to review. If None, finds the most recently active session."""
        include_completed: bool = True
        """Include completed subtask summaries. Set False for just pending items."""

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        from sovereign_agent.agent_session import SessionState, SessionStore
        from sovereign_agent.config import SETTINGS

        store = SessionStore()

        # Resolve session_id
        sid = args.session_id
        if sid is None:
            # Use trace_id as a hint (may be subtask id, not session id)
            # Fall back to finding the most recently modified session file
            sid = self._find_recent_session(SETTINGS.paths.data_dir)
            if sid is None:
                return ToolResult(
                    ok=False,
                    error="no active session found — start a session first",
                )

        try:
            state: SessionState = store.load(sid)
        except FileNotFoundError:
            return ToolResult(ok=False, error=f"session not found: {sid!r}")
        except Exception as exc:
            return ToolResult(ok=False, error=f"session load failed: {exc!r}")

        # Build readable report
        lines: list[str] = []
        lines.append(f"# Session: {state.session_id}")
        lines.append(f"Status: {state.status}")
        lines.append(f"Goal: {state.goal}")
        lines.append(f"Mode: {getattr(state, 'mode', 'unknown')}")
        lines.append("")

        subtasks = getattr(state, "subtasks", [])
        total = len(subtasks)
        done = sum(1 for s in subtasks if s.status in ("done", "skipped"))
        pending = sum(1 for s in subtasks if s.status == "pending")
        blocked = sum(1 for s in subtasks if s.status == "blocked")

        lines.append(f"Progress: {done}/{total} complete, {pending} pending, {blocked} blocked")
        lines.append("")

        status_icons = {
            "done": "✓", "skipped": "·", "blocked": "✗",
            "pending": "○", "active": "►", "error": "!",
        }

        for subtask in subtasks:
            if not args.include_completed and subtask.status in ("done", "skipped"):
                continue
            icon = status_icons.get(subtask.status, "?")
            lines.append(f"{icon} [{subtask.status}] {subtask.description}")
            if subtask.result_summary:
                lines.append(f"    → {subtask.result_summary[:200]}")
            if subtask.error:
                lines.append(f"    ! error: {subtask.error[:100]}")
            if subtask.iterations:
                lines.append(f"    iterations: {subtask.iterations}")

        # Queue extensions
        extensions = getattr(state, "queue_extensions", [])
        if extensions:
            lines.append("")
            lines.append(f"Queue extensions: {len(extensions)}")
            for ext in extensions:
                lines.append(f"  + {ext.added_subtasks} subtasks: {ext.justification[:80]}")

        return ToolResult(
            ok=True,
            output="\n".join(lines),
            metadata={
                "session_id": state.session_id,
                "total_subtasks": total,
                "done": done,
                "pending": pending,
                "blocked": blocked,
            },
        )

    @staticmethod
    def _find_recent_session(data_dir) -> str | None:
        """Find the most recently written session file."""
        import json
        from pathlib import Path
        if data_dir is None:
            return None
        sessions_dir = Path(data_dir) / "sessions"
        if not sessions_dir.exists():
            return None
        files = sorted(sessions_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        for f in files[:5]:
            try:
                data = json.loads(f.read_text())
                if data.get("status") in ("active", "planning", "paused"):
                    return data.get("session_id") or f.stem
            except Exception:
                continue
        # Fall back to most recent regardless of status
        if files:
            try:
                data = json.loads(files[0].read_text())
                return data.get("session_id") or files[0].stem
            except Exception:
                pass
        return None
