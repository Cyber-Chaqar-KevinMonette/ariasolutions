"""work_report — she tells you what she did and how to inspect it.

Bridge #2 (human↔Aria). When the operator asks "what did you do?", "what
have you worked on?", "show me your work", she answers from her real
**review journal** (`<data>/reviews/`, written at every session close-out)
and her session history — a warm, honest summary with concrete pointers to
where each piece of work can be reviewed. Deterministic; never invented.

Composed from:
  • `review_journal.list_reviews` + each review's `plan.json` (what/how/status)
  • `agent_session.SessionStore` as a fallback when no reviews exist yet
"""
from __future__ import annotations

import json
from pathlib import Path

__all__ = ["is_work_query", "compose_work_report"]

_TRIGGERS = (
    "what did you do", "what have you done", "what have you worked on",
    "what did you work on", "show me your work", "what did you get done",
    "what did you accomplish", "what have you been working on",
    "your recent work", "recent sessions", "your recent sessions",
    "what work did you do", "show your work", "what did you complete",
)


def is_work_query(text: str) -> bool:
    if not text:
        return False
    from sovereign_agent.bridge_patterns import match_any
    return match_any(text, _TRIGGERS)


def _data_dir(data_dir: Path | None) -> Path:
    if data_dir is not None:
        return Path(data_dir)
    from sovereign_agent.config import SETTINGS
    return SETTINGS.paths.data_dir


def _reviews_summary(data_dir: Path, limit: int) -> list[str]:
    """One line per recent review, from its plan.json. Best-effort."""
    try:
        from sovereign_agent.review_journal import list_reviews, reviews_root
    except Exception:  # noqa: BLE001
        return []
    lines: list[str] = []
    root = reviews_root(data_dir)
    for sid in list_reviews(data_dir)[:limit]:
        plan_path = root / sid / "plan.json"
        try:
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            lines.append(f"  · `{sid}` — (review present; details unavailable)")
            continue
        goal = str(plan.get("goal", ""))[:70]
        status = plan.get("status", "?")
        done = plan.get("subtasks_done", 0)
        total = plan.get("subtasks_total", 0)
        lines.append(f"  · **{goal or '(no goal recorded)'}** — {status}, "
                     f"{done}/{total} steps  [`{sid}`]")
    return lines


def _sessions_fallback(data_dir: Path, limit: int) -> list[str]:
    """When no review dirs exist yet, summarize from the session store."""
    try:
        from sovereign_agent.agent_session import SessionStore
        store = SessionStore(data_dir / "sessions")
        out: list[str] = []
        for st in store.list_all()[:limit]:
            done, total = st.progress()
            out.append(f"  · **{str(st.goal)[:70] or '(no goal)'}** — "
                       f"{st.status}, {done}/{total} steps  [`{st.session_id[-6:]}`]")
        return out
    except Exception:  # noqa: BLE001
        return []


def compose_work_report(data_dir: Path | None = None, *, limit: int = 5) -> str:
    """A warm, honest summary of her recent work + how to inspect it."""
    dd = _data_dir(data_dir)

    review_lines = _reviews_summary(dd, limit)
    if review_lines:
        body = "\n".join(review_lines)
        return (
            "Here's what I've been working on recently — each one has a full "
            "review you can open:\n\n"
            f"{body}\n\n"
            "For any of them, say `/review <id>` to see what I did, how I did "
            "it, and how to verify it — or open "
            f"`{dd}/reviews/<id>/README.md`. The full index is "
            f"`{dd}/reviews/INDEX.md`. 💛"
        )

    session_lines = _sessions_fallback(dd, limit)
    if session_lines:
        body = "\n".join(session_lines)
        return (
            "Here are my recent work sessions (full review directories start "
            "getting written on each session close-out):\n\n"
            f"{body}\n\n"
            "Say `/work <goal>` to start a bounded session — I'll leave a full "
            "reviewable record of it. 💛"
        )

    return (
        "I haven't run any work sessions yet — nothing to review. Say "
        "`/work <goal>` and I'll do it as a bounded, gated session and leave "
        "a full review (what I did · how · how to verify) you can inspect "
        "afterward. 💛"
    )
