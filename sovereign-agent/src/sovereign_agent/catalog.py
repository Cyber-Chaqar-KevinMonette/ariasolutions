"""catalog — a real, read-only list of what Kevin could have Aria work on.

Kevin, 2026-07-25: "I always ask her what she would like for me to have
her do. Let's make it where she can always find a grand catalog of
things that I could have her do or work on, and sessions I could have
her resume/continue."

Deliberately NOT an "AI decides what you should do next" generator — that
would brush against the standing autonomous-goal-generation limit
(DEFERRED_UNSAFE in CLAUDE.md). Every entry here is something that
GENUINELY already exists and is waiting: a resumable session, an open
mistake case still needing follow-up, a note Kevin already left her. This
surfaces them; Kevin picks.

Composed from:
  • session_bridge.resumable_sessions() + resume_blocked_reason() —
    honest about which are actually resumable right now (Phase 1's
    resume-gating-clarity-d), not just listed.
  • diagnosis.ConflictCatalog — open (unresolved) mistake/conflict cases.
  • workflow.requests.RequestStore — notes Kevin already left her
    (direction=to_aria) that are still open.
"""
from __future__ import annotations

from pathlib import Path

__all__ = ["compose_catalog"]


def _resumable_section(data_dir: Path) -> list[str]:
    from sovereign_agent.session_bridge import resumable_sessions, resume_blocked_reason

    sessions = resumable_sessions(limit=10)
    if not sessions:
        return ["  _nothing paused right now._"]
    lines = []
    for s in sessions:
        reason = resume_blocked_reason(s.session_id)
        goal = (s.goal or "(no goal)")[:80]
        done = sum(1 for st in s.subtasks if st.status in ("done", "skipped"))
        total = len(s.subtasks)
        if reason is None:
            lines.append(f"  · **{goal}** — {s.status}, {done}/{total} done — "
                        f"`/resume {s.session_id[-6:]}`")
        else:
            lines.append(f"  · **{goal}** — {s.status}, {done}/{total} done — "
                        f"blocked: {reason}")
    return lines


def _open_mistakes_section(data_dir: Path) -> list[str]:
    try:
        from sovereign_agent.diagnosis import ConflictCatalog
        catalog = ConflictCatalog(Path(data_dir) / "diagnoses")
        open_cases = [c for c in catalog.all_cases()
                     if c.status not in ("resolved", "archived")]
    except Exception:  # noqa: BLE001
        open_cases = []
    if not open_cases:
        return ["  _no open mistake/conflict cases._"]
    lines = []
    for c in open_cases[:10]:
        lines.append(f"  · **{c.trigger_event[:80]}** — {c.status} "
                    f"({c.severity}, `{c.case_id}`)")
    return lines


def _kevin_left_for_her_section(data_dir: Path) -> list[str]:
    try:
        from sovereign_agent.persistence.store import ErebloStore
        from sovereign_agent.workflow.requests import RequestStore
        from sovereign_agent.config import SETTINGS
        rs = RequestStore(ErebloStore(SETTINGS.paths.atoms_db))
        items = [r for r in rs.list_for_aria() if r.status == "open"]
    except Exception:  # noqa: BLE001
        items = []
    if not items:
        return ["  _nothing pending._"]
    return [f"  · **{r.title}** [{r.short_id}]" for r in items[:10]]


def compose_catalog(data_dir: Path) -> str:
    lines = [
        "# Catalog — what's real and waiting",
        "",
        "## Resumable sessions",
        *_resumable_section(data_dir),
        "",
        "## Open mistake/conflict cases (from record_mistake)",
        *_open_mistakes_section(data_dir),
        "",
        "## Notes Kevin already left for her",
        *_kevin_left_for_her_section(data_dir),
        "",
        "This lists what genuinely already exists — it never invents "
        "new goals. `/recap` for what already finished, `/work <goal>` to "
        "start something new.",
    ]
    return "\n".join(lines)
