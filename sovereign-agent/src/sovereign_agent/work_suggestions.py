"""work_suggestions — grounded ideas for what Aria could work on next.

Kevin, 2026-07-26: "a suggestions button next to our new buttons so when
I want to ask her for things she could or would like to work on — she
could give me a list of important and/or valuable task she can work on
or practice doing."

Every suggestion traces to real, already-computed system state:
  • a stewardship sentinel's own scan finding something concrete worth
    fixing (`Sentinel.proposals()`) or a real gap in what it can reach
    yet (`Sentinel.coverage_gaps()`) — the same machinery `sov doctor`
    and the cockpit's health strips already trust;
  • a bot project Kevin named and described but never built
    (`bot_projects.BotProject(status="concept")`) — a real, durable,
    already-defined idea, not a freshly invented one.

Nothing here is generated or guessed. An empty scan produces an honest
empty list, never a filler idea to look busy.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

__all__ = ["WorkSuggestion", "gather_suggestions", "compose_suggestions_report",
           "is_suggestions_query"]


@dataclass(frozen=True)
class WorkSuggestion:
    source: str          # sentinel id, or "bot-studio"
    kind: str            # "fix" | "gap" | "build"
    summary: str
    remediation: str = ""

    @property
    def emoji(self) -> str:
        return {"fix": "✗", "gap": "◊", "build": "✦"}.get(self.kind, "·")

    def as_goal_text(self) -> str:
        """A single line suitable for pasting after `/work `."""
        if self.remediation:
            return f"{self.summary} — {self.remediation}"
        return self.summary


def _sentinel_suggestions(data_dir: Path) -> list[WorkSuggestion]:
    out: list[WorkSuggestion] = []
    try:
        from sovereign_agent.stewardship.registry import instantiate_all
    except Exception:  # noqa: BLE001
        return out
    for sentinel in instantiate_all(data_dir):
        try:
            sentinel.bootstrap()
            if not sentinel.is_enabled():
                continue
            report = sentinel.scan()
        except Exception:  # noqa: BLE001 — one bad sentinel can't block the rest
            continue
        try:
            for p in sentinel.proposals(report):
                if not isinstance(p, dict):
                    continue
                summary = p.get("summary") or p.get("file") or ""
                if not summary:
                    continue
                out.append(WorkSuggestion(
                    source=sentinel.id, kind="fix",
                    summary=str(summary), remediation=str(p.get("remediation", ""))))
        except Exception:  # noqa: BLE001
            pass
        try:
            for g in sentinel.coverage_gaps(report):
                if isinstance(g, dict):
                    summary = g.get("summary") or g.get("gap") or ""
                else:
                    summary = str(g)
                if not summary:
                    continue
                out.append(WorkSuggestion(
                    source=sentinel.id, kind="gap", summary=str(summary)))
        except Exception:  # noqa: BLE001
            pass
    return out


def _concept_bot_suggestions(data_dir: Path) -> list[WorkSuggestion]:
    out: list[WorkSuggestion] = []
    try:
        from sovereign_agent.bot_projects import list_all
    except Exception:  # noqa: BLE001
        return out
    try:
        projects = list_all(data_dir)
    except Exception:  # noqa: BLE001
        return out
    for p in projects:
        if p.status != "concept":
            continue
        out.append(WorkSuggestion(
            source="bot-studio", kind="build",
            summary=f'"{p.project_name}" ({p.kind_label}) is defined but not built yet',
            remediation=p.description or "open the Bot Studio (/bots) to move it forward"))
    return out


def _repo_root() -> Path:
    import sovereign_agent
    return Path(sovereign_agent.__file__).resolve().parent.parent.parent


def _module_is_applied(repo_root: Path, name: str) -> bool:
    """Python port of scripts/apply_queue.sh's own _is_applied() — same
    three-check order (``.applied_ok`` trusted first; the old
    ``backups/`` check is a false positive on a partially-failed apply,
    kept only as a fallback for modules applied before that marker
    existed)."""
    slug = name.removeprefix("aria-").replace("-", "_")
    if (repo_root / name / ".applied_ok").is_file():
        return True
    if (repo_root / name / "backups").is_dir():
        return True
    if (repo_root / "tests" / f"test_{slug}.py").is_file():
        return True
    return False


def _apply_queue_suggestions(repo_root: Path | None = None) -> list[WorkSuggestion]:
    """Staged-but-unapplied aria-<name>/ modules — real backlog signal
    scripts/apply_queue.sh already tracks, surfaced here so it shows up
    without a separate shell command. Best-effort: repo layout that
    doesn't match (e.g. a non-checkout deployment) just yields nothing."""
    out: list[WorkSuggestion] = []
    try:
        root = repo_root or _repo_root()
        for d in sorted(root.glob("aria-*")):
            if not d.is_dir():
                continue
            if not list(d.glob("apply_*.sh")):
                continue
            name = d.name
            if _module_is_applied(root, name):
                continue
            out.append(WorkSuggestion(
                source="apply-queue", kind="build",
                summary=f'"{name}" is staged but not applied yet',
                remediation="./scripts/apply_queue.sh run --yes (each module goes "
                            "through safe_apply: cockpit-guard + backup + gate + auto-rollback)"))
    except Exception:  # noqa: BLE001
        pass
    return out


_OPEN_CONFLICT_STATUSES = ("intake", "diagnosing", "resolving")


def _conflict_catalog_suggestions(data_dir: Path) -> list[WorkSuggestion]:
    """Open Conflict->Diagnosis->Resolution cases from diagnosis.py's
    ConflictCatalog — a real human-decision queue that previously had no
    presence in the Suggestions screen at all."""
    out: list[WorkSuggestion] = []
    try:
        from sovereign_agent.diagnosis import ConflictCatalog
        catalog = ConflictCatalog(Path(data_dir) / "diagnoses")
        cases = []
        for status in _OPEN_CONFLICT_STATUSES:
            cases.extend(catalog.by_status(status))
        for c in cases:
            out.append(WorkSuggestion(
                source="diagnosis", kind="fix",
                summary=f"conflict {c.case_id} ({c.type}, {c.status}): {c.trigger_event}"[:200],
                remediation=f"owner: {c.owner}" if c.owner else "needs diagnosis/resolution"))
    except Exception:  # noqa: BLE001
        pass
    return out


def gather_suggestions(data_dir: Path | None = None) -> list[WorkSuggestion]:
    """Every grounded suggestion, sentinel fixes/gaps first (they're the
    most concrete and time-sensitive), then the apply queue, open
    diagnosis cases, and unbuilt bot-project ideas — unifying four
    previously-disconnected backlog signals into the one screen Kevin
    already opens."""
    if data_dir is None:
        from sovereign_agent.config import SETTINGS
        data_dir = SETTINGS.paths.data_dir
    return (
        _sentinel_suggestions(data_dir)
        + _apply_queue_suggestions()
        + _conflict_catalog_suggestions(data_dir)
        + _concept_bot_suggestions(data_dir)
    )


_TRIGGERS = (
    # deliberately distinct from next_report's "any suggestions" / "what
    # should we work on" (that bridge answers what's BLOCKING you; this
    # one proposes real work for HER to do) — see the collision matrix
    # in tests/test_bridge_patterns.py.
    "what should you work on", "what could you work on",
    "give me some suggestions", "give me a suggestion",
    "what could we work on", "what would you like to work on",
    "what can you practice", "suggest something to work on",
    "suggest a task", "what's worth working on",
)


def is_suggestions_query(text: str) -> bool:
    if not text:
        return False
    from sovereign_agent.bridge_patterns import match_any
    return match_any(text, _TRIGGERS)


def compose_suggestions_report(data_dir: Path | None = None) -> str:
    """Deterministic chat-bridge answer — reads the same grounded list
    the cockpit's Suggestions screen shows, never invents its own."""
    items = gather_suggestions(data_dir)
    if not items:
        return ("Nothing concrete jumps out right now — every sentinel's "
                "clean and every named bot idea is already built. Ask me "
                "again after the next scan, or open the Bot Studio (/bots) "
                "to define a fresh one.")
    lines = [f"Here's what's real and worth doing ({len(items)}):"]
    for s in items[:12]:
        lines.append(f"  {s.emoji} [{s.source}] {s.summary}")
        if s.remediation:
            lines.append(f"      → {s.remediation}")
    if len(items) > 12:
        lines.append(f"  … and {len(items) - 12} more (open ✧ suggestions in the cockpit).")
    return "\n".join(lines)
