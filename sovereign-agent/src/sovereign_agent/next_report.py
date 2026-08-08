"""next_report — she reaches toward you: "what do you need / what's next?"

Bridge #4 (human↔Aria). The three report bridges let her answer about
herself; this is the one where SHE initiates — when the operator asks "what
do you need from me?", "what should we do next?", "what's on your plate?",
she answers from her real pending state:
  • requests waiting on the human (RequestStore, direction=to_human)
  • parked items whose revisit time has arrived (RequestStore.due)
  • sessions that can be resumed (session_bridge.resumable_sessions)
and proposes a concrete next step. Deterministic; grounded in real state.
"""
from __future__ import annotations

__all__ = ["is_next_query", "compose_next_report"]

_TRIGGERS = (
    "what should we do", "what's next", "whats next", "what do you need",
    "what do you need from me", "what should i do", "what now", "what next",
    "anything you need", "what are you waiting on", "what's on your plate",
    "whats on your plate", "what should we work on", "any suggestions",
    "what do you want to do", "where should we start",
)


def is_next_query(text: str) -> bool:
    if not text:
        return False
    from sovereign_agent.bridge_patterns import match_any
    return match_any(text, _TRIGGERS)


def _open_requests():
    try:
        from sovereign_agent.config import SETTINGS
        from sovereign_agent.persistence.store import ErebloStore
        from sovereign_agent.workflow.requests import DIRECTION_TO_HUMAN, RequestStore
        rs = RequestStore(ErebloStore(SETTINGS.paths.atoms_db))
        return rs.list_open(direction=DIRECTION_TO_HUMAN), rs.due()
    except Exception:  # noqa: BLE001
        return [], []


def _resumable():
    try:
        from sovereign_agent.session_bridge import resumable_sessions
        return resumable_sessions(limit=5)
    except Exception:  # noqa: BLE001
        return []


def compose_next_report() -> str:
    lines: list[str] = []
    open_items, due_items = _open_requests()
    resumable = _resumable()

    anything = bool(open_items or due_items or resumable)

    if open_items:
        lines.append(f"**{len(open_items)} thing(s) waiting on you:**")
        for r in open_items[:5]:
            title = getattr(r, "title", "")[:70]
            sid = getattr(r, "short_id", "")
            lines.append(f"  · {title}  [dim][{sid}][/dim]")
        lines.append("")

    if due_items:
        lines.append(f"**{len(due_items)} parked item(s) whose time has come:**")
        for r in due_items[:5]:
            lines.append(f"  · {getattr(r, 'title', '')[:70]}")
        lines.append("")

    if resumable:
        lines.append(f"**{len(resumable)} session(s) you could resume** "
                     "(F6 or /resume for the menu):")
        for s in resumable[:5]:
            done = sum(1 for st in s.subtasks if st.status in ("done", "skipped"))
            total = len(s.subtasks)
            lines.append(f"  · {(s.goal or '(no goal)')[:60]} — {s.status}, {done}/{total} steps")
        lines.append("")

    if not anything:
        return (
            "Nothing's pressing on my side — I'm caught up, no requests waiting "
            "on you and no paused sessions. If you'd like to start something, "
            "just say `/work <goal>` and I'll run it as a bounded, reviewable "
            "session. Or we can just talk. 💛"
        )

    lines.append("That's what's on my plate. Point me at any of it, or say "
                 "`/work <goal>` for something new. 💛")
    return "\n".join(lines)
