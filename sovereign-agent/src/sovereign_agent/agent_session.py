"""
╔══════════════════════════════════════════════════════════════════════════╗
║  agent_session.py — the persistent multi-step agent loop                ║
║  v0.2.27.0 · the long-horizon work envelope                              ║
║                                                                           ║
║  WHAT THIS IS                                                            ║
║                                                                           ║
║    The inner ``agent_loop`` runs one tool-using LLM conversation until  ║
║    the model either settles (no more tool calls) or hits a budget. That ║
║    is the right primitive for ONE focused task. It is the wrong shape   ║
║    for long-horizon work that needs to be:                              ║
║                                                                           ║
║      • decomposed into many sub-tasks                                   ║
║      • tracked across pauses, restarts, and operator interruptions      ║
║      • bounded by authority tier at every step                          ║
║      • resumable from exactly where it stopped                          ║
║                                                                           ║
║    ``agent_session`` is the outer layer. One session = one durable      ║
║    plan with a queue of subtasks. Aria works the queue one subtask at  ║
║    a time, each subtask being one inner ``agent_loop`` invocation. She ║
║    can grow the queue as she learns. She pauses at safe checkpoints.   ║
║    The state lives on disk; ``sov session resume`` picks up where she  ║
║    left off — even after a kernel crash.                                ║
║                                                                           ║
║  THE LOOP                                                                ║
║                                                                           ║
║    ┌──────────────────────────────────────────────────────────────┐    ║
║    │ load or create SessionState                                  │    ║
║    │                                                              │    ║
║    │ ┌──── repeat until queue drained / halted / paused ────┐    │    ║
║    │ │                                                      │    │    ║
║    │ │  1. PROTOCOL-ZERO check  → break "halted"            │    │    ║
║    │ │  2. interrupts.checkpoint → break "paused"           │    │    ║
║    │ │  3. budget check         → break "budget"            │    │    ║
║    │ │  4. authority check on next subtask                  │    │    ║
║    │ │       Tier 0/1 → proceed                             │    │    ║
║    │ │       Tier 2   → require operator confirmation       │    │    ║
║    │ │       Tier 3   → require approval token              │    │    ║
║    │ │  5. constitutional check (calibrated, bounded, …)   │    │    ║
║    │ │  6. horizon scan (Tier 2+) → attach atom             │    │    ║
║    │ │  7. run agent_loop(subtask.description)              │    │    ║
║    │ │  8. parse model's update_plan proposals             │    │    ║
║    │ │       — mark subtask done                            │    │    ║
║    │ │       — add any new subtasks to queue                │    │    ║
║    │ │  9. atomic write of SessionState                     │    │    ║
║    │ │                                                      │    │    ║
║    │ └──────────────────────────────────────────────────────┘    │    ║
║    │                                                              │    ║
║    │ on exit: reflect, force_fsync, emit session-{settle|x}      │    ║
║    └──────────────────────────────────────────────────────────────┘    ║
║                                                                           ║
║  WHAT MAKES THIS SAFE                                                    ║
║                                                                           ║
║    Six gates between the model's plan and any side-effect:              ║
║      1. ◊ PROTOCOL-ZERO          — sacred halt, checked first           ║
║      2. ◊ Operator interrupt     — soft pause, checkpoint hook          ║
║      3. ◊ Budget                 — wall, tokens, iterations             ║
║      4. ◊ Authority tier         — never above mode ceiling             ║
║      5. ◊ Constitution           — calibrated, bounded, no-delegation   ║
║      6. ◊ Horizon (Tier 2+)      — 3m/12m/3y projection emitted first  ║
║                                                                           ║
║    Authority is bounded by mode. PROTOCOL-ZERO can fire at any safe    ║
║    boundary and the session exits cleanly with state preserved. The    ║
║    operator can `sov session halt <id>` at any time and the next       ║
║    checkpoint catches it.                                               ║
║                                                                           ║
║  WHAT THIS IS NOT                                                        ║
║                                                                           ║
║    • Not a replacement for ``agent_loop``. It IS ``agent_loop`` with   ║
║      a durable queue around it.                                         ║
║    • Not a planner. It uses a planner (the decomposer is one model    ║
║      call at session start; Aria can also `propose_subtask` mid-run). ║
║    • Not a daemon. One session = one process. Resume creates a new   ║
║      process that picks up the file.                                  ║
║                                                                           ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from . import protocol_zero
from .config import SETTINGS
from .events import emit_child_event, emit_event, force_fsync, trace
from .interrupts import checkpoint as interrupt_checkpoint
from .interrupts import consume_resume
from .loop import LoopResult, agent_loop
from .modes import BudgetExceeded, Mode, RunBudget, effective_wall_limit
from .tools.base import Tool

# ─────────────────────────────────────────────────────────────────────────
# State shape
# ─────────────────────────────────────────────────────────────────────────


# inbox-cadence-d (Kevin, 2026-07-26): "she needs to be emptying her inbox
# every 15 minutes or so." How often (wall-clock, in-session) the subtask
# boundary below re-checks whether she has open to_aria notes and, if so,
# auto-enqueues one real subtask to close them out — a structural nudge,
# not a reminder she could miss. Module-level so a test can shrink it.
INBOX_CADENCE_S = 900.0  # 15 minutes

SubtaskStatus = Literal["pending", "in_progress", "done", "blocked", "skipped", "awaiting_approval"]  # graduated-trust-d
SessionStatus = Literal[
    "active",      # currently running this process
    "paused",      # operator interrupted; state preserved; resumable
    "halted",      # PROTOCOL-ZERO; resume requires explicit operator restart
    "complete",    # all subtasks done
    "budget",      # ran out of wall/tokens/iterations
    "error",       # uncaught error; needs operator inspection
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


@dataclass
class Subtask:
    """One unit of work inside a session.

    Tied to exactly one ``agent_loop`` invocation. The agent_loop runs to
    settle/poison/budget within ONE subtask; multi-turn LLM tool use happens
    inside the loop. When the loop returns, this subtask is closed and the
    session moves to the next.

    ``parent_id`` records which subtask discovered this one (for the dynamic
    queue case where Aria proposes new work mid-session). None for subtasks
    in the initial decomposition.

    ``required_tier`` is the *maximum* authority tier this subtask is allowed
    to use. The session refuses to dispatch a subtask whose required_tier
    exceeds the mode's ceiling. This is bounded-authority enforced at the
    queue level, not just the tool level.
    """

    id: str
    description: str
    status: SubtaskStatus = "pending"
    required_tier: int = 1  # default: routine work; sandbox writes only
    parent_id: str | None = None
    created_at: str = field(default_factory=_utc_now)
    started_at: str | None = None
    completed_at: str | None = None
    result_summary: str = ""              # what Aria learned, ≤500 chars
    iterations: int = 0
    tokens: int = 0
    trace_id: str | None = None           # link to events for provenance
    horizon_atom_id: str | None = None    # Phase 2 — set if horizon scan ran
    error: str | None = None


@dataclass
class QueueExtension:
    """One mid-session queue extension. v0.2.32.0.

    When the agent (in work mode) discovers it needs more work than the
    original plan covered — say, it set out for 125 runs and halfway
    through realizes 10 new tools must be created — it can extend the
    queue with an explicit justification. Each extension is recorded
    here so the audit trail shows not just THAT the queue grew but
    WHY.

    Extensions can't bypass the session-level budget. The four-gate loop
    in run_session still checks max_iterations, wall_seconds, etc. — the
    extension just adds new subtasks for the loop to chew through within
    those bounds.
    """
    at: str                                   # ISO timestamp of the extension
    added_subtasks: int                       # how many new subtasks
    justification: str                        # WHY — operator-readable
    cushion: int = 0                          # extra subtasks added as safety margin


@dataclass
class SessionState:
    """The durable shape of a session.

    Written to ``<data>/sessions/<session_id>.json`` after every state
    transition. Atomic writes (tempfile + rename) so a crash mid-write
    cannot corrupt the file.

    Read fields freely. Mutations must go through ``SessionStore`` so the
    file stays in sync with memory.
    """

    session_id: str
    goal: str
    mode: str                                       # serialized Mode value
    subtasks: list[Subtask] = field(default_factory=list)
    status: SessionStatus = "active"
    created_at: str = field(default_factory=_utc_now)
    updated_at: str = field(default_factory=_utc_now)
    total_iterations: int = 0
    total_tokens: int = 0
    started_at_monotonic: float | None = None       # in-memory only; not persisted
    max_subtasks: int = 50                          # hard cap on queue growth
    pause_reason: str | None = None                 # filled when status==paused
    last_error: str | None = None                   # filled when status==error

    # v0.2.32.0 — queue-of-queues extension tracking
    # When the agent discovers mid-run that more work is needed, it can
    # extend the queue with explicit justification. Each extension is
    # recorded here for the audit trail.
    extensions: list[QueueExtension] = field(default_factory=list)
    original_subtask_count: int = 0                 # snapshot of initial plan size

    # graduated-trust-d — graduated trust: hold-and-continue (default ON) means an
    # over-tier subtask is HELD, never a full-session stop; plan revisions
    # (mid-work plan edits, never touching the running subtask) tracked
    # the same audit-trail way extensions already are.
    hold_and_continue: bool = True
    plan_revisions: list[PlanRevision] = field(default_factory=list)

    def held_subtask_ids(self) -> list[str]:  # graduated-trust-d
        return [s.id for s in self.subtasks if s.status == "awaiting_approval"]

    # ── derived ────────────────────────────────────────────────────────

    def next_pending(self) -> Subtask | None:
        return next((s for s in self.subtasks if s.status == "pending"), None)

    def progress(self) -> tuple[int, int]:
        total = len(self.subtasks)
        done = sum(1 for s in self.subtasks if s.status in ("done", "skipped"))
        return done, total

    def extension_summary(self) -> str:
        """One-line description of queue extensions for the cockpit/status bar.

        Examples:
          - "no extensions" — original queue ran as planned
          - "1 extension (+10 subtasks)" — one mid-run growth
          - "3 extensions (+10, +15, +5 subtasks)" — multiple growths
        """
        if not self.extensions:
            return "no extensions"
        if len(self.extensions) == 1:
            e = self.extensions[0]
            return f"1 extension (+{e.added_subtasks} subtasks)"
        deltas = ", ".join(f"+{e.added_subtasks}" for e in self.extensions)
        return f"{len(self.extensions)} extensions ({deltas} subtasks)"

    def current_run_number(self) -> int:
        """How many subtasks have completed (done/skipped/blocked)? Used
        for the cockpit's run-progress display."""
        return sum(
            1 for s in self.subtasks
            if s.status in ("done", "skipped", "blocked")
        )

    def is_drained(self) -> bool:
        return all(s.status != "pending" and s.status != "in_progress"
                   for s in self.subtasks)

    def completed_summary_for_prompt(self, *, max_chars: int = 4000) -> str:
        """A compact narrative of what's been done, for inclusion in the model
        prompt of the next subtask. Truncates oldest-first to fit ``max_chars``.

        Kept compact on purpose — the agent_loop's own message history is
        the rich context within one subtask; this is the bridge between
        subtasks, not a replacement for the loop's internal state.
        """
        lines: list[str] = []
        for s in self.subtasks:
            if s.status not in ("done", "skipped", "blocked"):
                continue
            marker = {"done": "✓", "skipped": "·", "blocked": "✗"}[s.status]
            summary = s.result_summary.strip() or "(no summary)"
            lines.append(f"{marker} {s.description} — {summary}")
        joined = "\n".join(lines)
        if len(joined) <= max_chars:
            return joined
        # Truncate oldest entries
        return "… (older entries elided)\n" + joined[-max_chars:]


def extend_session_queue(
    state: SessionState,
    new_subtasks: list[Subtask],
    *,
    justification: str,
    cushion: int = 0,
) -> QueueExtension:
    """Append new subtasks to a running session's queue. v0.2.32.0.

    This is the queue-of-queues mechanic: when the agent (in work mode)
    discovers it needs more work than the original plan covered, it calls
    this to extend the queue with explicit justification.

    The four-gate session loop in ``run_session`` picks up the new
    subtasks naturally — it pulls "next pending" each iteration. So a
    well-timed extension extends the working horizon without busting any
    budget or restarting the loop.

    Requires work mode. In chat mode, the operator decides whether to
    extend; the agent stops and asks. This function does NOT check the
    mode itself — that's the caller's responsibility. The check is
    enforced at the level where the agent decides to call this function,
    so that operator-driven extensions (e.g. an operator typing "add 20
    more runs") can pass through cleanly.

    Args:
        state: the live SessionState being extended.
        new_subtasks: subtasks to append. Each will be assigned a fresh
                      `id` and `created_at` if not already set.
        justification: REQUIRED — operator-readable reason. The audit
                       trail captures this verbatim.
        cushion: extra subtasks added as a safety margin. The agent's
                 "I think I need 10 more, plus 2 for cushion" should be
                 expressed as `len(new_subtasks)=12, cushion=2`.

    Returns:
        The QueueExtension record that was appended to state.extensions.

    Raises:
        ValueError: if justification is empty.
    """
    justification = (justification or "").strip()
    if not justification:
        raise ValueError(
            "queue extension requires a justification — "
            "the audit trail must capture WHY the queue grew"
        )
    if not new_subtasks:
        raise ValueError("extend_session_queue called with no new subtasks")

    state.subtasks.extend(new_subtasks)
    record = QueueExtension(
        at=_utc_now(),
        added_subtasks=len(new_subtasks),
        justification=justification,
        cushion=cushion,
    )
    state.extensions.append(record)
    state.updated_at = _utc_now()

    # Best-effort event emission for the audit trail
    try:
        emit_event(
            "session-extend-d",
            plane="control",
            trace_id=state.session_id,
            payload={
                "session_id": state.session_id,
                "added_subtasks": record.added_subtasks,
                "cushion": cushion,
                "justification": justification,
                "new_total_subtasks": len(state.subtasks),
                "extension_count": len(state.extensions),
            },
        )
    except Exception:  # noqa: BLE001 — event emission is best-effort
        pass

    return record


# ─────────────────────────────────────────────────────────────────────────
# Store — durable persistence with atomic writes
# ─────────────────────────────────────────────────────────────────────────


class SessionError(Exception):
    """Raised for unrecoverable session-state errors. Caller decides outcome."""


class SessionStore:
    """File-backed store for SessionState. One file per session.

    ``<data>/sessions/<session_id>.json`` is the canonical location.
    ``load()`` and ``save()`` are atomic; corrupt files are detected on
    load and raise ``SessionError`` so the caller can decide whether to
    quarantine or recover.

    No locking: one process per session. If you need to inspect a running
    session, use ``sov session status <id>`` (read-only) — the same file
    is being written by the agent, but writes are atomic so readers will
    always see either the prior state or the next, never a torn write.
    """

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or (SETTINGS.paths.data_dir / "sessions")
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, session_id: str) -> Path:
        # Defensive: refuse session ids containing path separators
        if "/" in session_id or "\\" in session_id or session_id.startswith("."):
            raise SessionError(f"invalid session_id: {session_id!r}")
        return self.root / f"{session_id}.json"

    def save(self, state: SessionState) -> None:
        """Atomic write. tempfile + rename."""
        state.updated_at = _utc_now()
        # started_at_monotonic is in-memory only — exclude from serialization
        d = asdict(state)
        d.pop("started_at_monotonic", None)
        text = json.dumps(d, indent=2, default=str)
        target = self.path_for(state.session_id)
        tmp = target.with_suffix(".json.tmp")
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, target)  # POSIX atomic on same filesystem

    def load(self, session_id: str) -> SessionState:
        target = self.path_for(session_id)
        if not target.exists():
            raise SessionError(f"session not found: {session_id}")
        try:
            d = json.loads(target.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise SessionError(f"session file corrupt: {target.name}: {e}") from e
        try:
            subtasks = [Subtask(**s) for s in d.pop("subtasks", [])]
            return SessionState(subtasks=subtasks, **d)
        except TypeError as e:
            raise SessionError(f"session file schema mismatch: {e}") from e

    def list_all(self, *, status: SessionStatus | None = None) -> list[SessionState]:
        """All sessions on disk, optionally filtered by status. Most-recent first."""
        out: list[SessionState] = []
        corrupt = 0  # read-repair-d — counted skips, surfaced, never a wedge
        for p in sorted(self.root.glob("*.json"), reverse=True):
            if p.name.endswith(".scope.json"):
                continue   # scope contracts live beside sessions; not sessions
            try:
                s = self.load(p.stem)
            except SessionError:
                corrupt += 1
                continue
            if status is None or s.status == status:
                out.append(s)
        if corrupt:
            try:
                emit_event("corrupt-lines-d", plane="control",
                           trace_id="read-repair-sessions",
                           payload={"store": "sessions",
                                    "file": str(self.root),
                                    "skipped": corrupt,
                                    "total_lines": corrupt + len(out)})
            except Exception:  # noqa: BLE001
                pass
        return out

    def delete(self, session_id: str) -> bool:  # resume-menu-forget-d
        """Permanently remove a session record (and its scope contract,
        if any). Kevin, 2026-07-21: "a way to maybe delete[] selections
        if I make sessions I no longer need." Returns True iff a session
        file existed and was removed; False if there was nothing there
        (a harmless no-op, not an error — the caller may be clearing a
        stale row it's already shown)."""
        target = self.path_for(session_id)
        existed = target.exists()
        target.unlink(missing_ok=True)
        # scope.py's own _scope_path() builds this same "<id>.scope.json"
        # sibling file; deleting it here keeps a forgotten session from
        # leaving an orphaned scope contract behind.
        scope_file = target.parent / f"{session_id}.scope.json"
        scope_file.unlink(missing_ok=True)
        return existed


# ─────────────────────────────────────────────────────────────────────────
# Subtask description parser — what Aria emits when she wants to grow the queue
# ─────────────────────────────────────────────────────────────────────────


# When Aria wants to propose new subtasks, she emits lines matching this
# pattern in her final message. The session parses them out. This is the
# narrow, structured way she grows the queue — far less error-prone than
# parsing free-form prose.
#
# Format:    NEXT_SUBTASK[tier=N]: <description>
# Example:   NEXT_SUBTASK[tier=1]: read the file at /tmp/notes.md
#
# Tier defaults to 1 if omitted. Description can span until newline.
_SUBTASK_PROPOSAL_RE = re.compile(
    r"^NEXT_SUBTASK(?:\[tier=(?P<tier>\d+)\])?:\s*(?P<desc>.+)$",
    re.MULTILINE,
)


def parse_proposals(text: str) -> list[tuple[str, int]]:
    """Extract NEXT_SUBTASK proposals from a model final message.

    Returns a list of ``(description, tier)`` tuples in source order.
    Empty list if no proposals were found. Tier defaults to 1 if omitted.
    Tier is clamped to [0, 3] — out-of-range values raise SessionError so
    the operator catches a malformed model output rather than silently
    accepting a Tier-9 demand.
    """
    out: list[tuple[str, int]] = []
    if not text:
        return out
    for match in _SUBTASK_PROPOSAL_RE.finditer(text):
        tier_raw = match.group("tier")
        tier = int(tier_raw) if tier_raw else 1
        if tier < 0 or tier > 3:
            raise SessionError(
                f"subtask proposal has invalid tier {tier}; must be 0..3"
            )
        desc = match.group("desc").strip()
        if desc:
            out.append((desc, tier))
    return out


# ─────────────────────────────────────────────────────────────────────────
# The session prompt — what Aria sees on top of each subtask's agent_loop
# ─────────────────────────────────────────────────────────────────────────


SESSION_GUIDANCE_TEMPLATE = """\
═══ SESSION CONTEXT ═══

You are working on session ``{session_id}``.

The session-level goal:
  {goal}

Subtask {n_done} of {n_total} (this one):
  {current_subtask}

Completed work in this session:
{completed_summary}

═══ HOW TO GROW THE QUEUE ═══

If, while working on this subtask, you discover other subtasks the session
should also do, propose them in your final message using exactly this
format, one per line:

  NEXT_SUBTASK[tier=N]: <description>

Where ``tier`` is 0..3 (default 1). Tier 0 = read-only, Tier 1 = sandbox
writes, Tier 2 = move/trash/shell, Tier 3 = external/irreversible.

Examples:
  NEXT_SUBTASK[tier=0]: read ~/notes/topic.md to see what's already there
  NEXT_SUBTASK[tier=1]: write a draft outline to <sandbox>/outline.md

Do NOT propose more subtasks than the work actually needs. Each one runs
its own agent_loop with its own budget. Be specific and bounded; "do
research" is not a subtask, "read the three files in ~/papers/RAG and
summarize the central claim of each" is.

═══ WHEN YOU ARE DONE WITH THIS SUBTASK ═══

Respond with a final message (no tool calls). The first line should be:

  RESULT: <one-sentence summary of what you accomplished, ≤200 chars>

This is what the next subtask will see in its 'completed' summary. After
that, any NEXT_SUBTASK proposals, then any other notes.
"""


_COMPACT_GUIDANCE = """═══ SESSION {session_id} · subtask {n_done}/{n_total} ═══
Goal: {goal}
Done so far: {completed_summary}

THIS SUBTASK: {current_subtask}

When finished, reply WITHOUT tool calls. First line exactly:
RESULT: <one sentence, what happened>
If (and only if) more steps are truly needed, add lines:
NEXT_SUBTASK[tier=N]: <one concrete step>   (tier 0=read 1=sandbox 2=repo 3=external)
Propose few. Stay inside the goal."""  # guidance-diet-d


def _format_session_guidance(state: SessionState, current: Subtask) -> str:
    # guidance-diet-d — the compact guidance is the default: the measured
    # full template (2 protocols + worked examples + 4000-char summary)
    # starved the 8B vessel per-subtask. SOV_NO_GUIDANCE_DIET=1 restores
    # the original byte-for-byte.
    import os as _os

    done, total = state.progress()
    if not _os.environ.get("SOV_NO_GUIDANCE_DIET"):
        guidance = _COMPACT_GUIDANCE.format(
            session_id=state.session_id,
            goal=state.goal[:300],
            n_done=done + 1,
            n_total=total,
            current_subtask=current.description,
            completed_summary=(state.completed_summary_for_prompt(max_chars=1200)
                               or "(none yet)"),
        )
        try:
            from sovereign_agent.scope import load_scope as _qb_load_scope

            _qb_sc = _qb_load_scope(state.session_id)
            if _qb_sc is not None:
                guidance += "\n\n" + _qb_sc.format_for_prompt()
        except Exception:  # noqa: BLE001
            pass
        return guidance
    guidance = SESSION_GUIDANCE_TEMPLATE.format(
        session_id=state.session_id,
        goal=state.goal,
        n_done=done + 1,
        n_total=total,
        current_subtask=current.description,
        completed_summary=state.completed_summary_for_prompt() or "(none yet)",
    )
    # scope-contract-d — the contract she wrote before starting rides in the
    # guidance: she self-polices against her own words.
    try:
        from sovereign_agent.scope import load_scope

        _sc = load_scope(state.session_id)
        if _sc is not None:
            guidance += "\n\n" + _sc.format_for_prompt()
    except Exception:  # noqa: BLE001
        pass
    return guidance


# ─────────────────────────────────────────────────────────────────────────
# Result-summary extraction
# ─────────────────────────────────────────────────────────────────────────


_RESULT_LINE_RE = re.compile(r"^\s*RESULT:\s*(?P<summary>.+?)(?:\n|$)", re.MULTILINE)


def parse_result_summary(text: str, *, max_chars: int = 500) -> str:
    """Pull the RESULT: line out of a model final message.

    If absent, falls back to the first 200 chars of the message stripped
    of any NEXT_SUBTASK lines (so the summary doesn't carry the queue
    proposals as a sub-string). Empty string if there's nothing usable.
    """
    if not text:
        return ""
    m = _RESULT_LINE_RE.search(text)
    if m:
        return m.group("summary").strip()[:max_chars]
    # Fallback: strip proposals + truncate
    cleaned = _SUBTASK_PROPOSAL_RE.sub("", text).strip()
    return cleaned[:200]


# ─────────────────────────────────────────────────────────────────────────
# Authority gating at the queue level (not just per-tool)
# ─────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class AuthorityCheck:
    """Outcome of pre-flight authority check on a subtask.

    Three states:
      • allowed=True              → dispatch normally
      • allowed=False, requires_operator=True → pause for human; not an error
      • allowed=False, requires_operator=False → reject permanently (mark blocked)
    """
    allowed: bool
    requires_operator: bool = False
    reason: str = ""


def check_subtask_authority(subtask: Subtask, mode: Mode) -> AuthorityCheck:
    """Pre-flight check before dispatching a subtask through the agent loop.

    Bounded-authority is enforced HERE in addition to the per-tool checks
    inside agent_loop. Belt and suspenders is correct for authority.
    """
    from .modes import MODE_TIER_CEILING

    ceiling = MODE_TIER_CEILING[mode]
    if subtask.required_tier > ceiling:
        return AuthorityCheck(
            allowed=False,
            requires_operator=False,
            reason=(
                f"subtask requires tier {subtask.required_tier} but mode "
                f"{mode.value} caps at {ceiling}; this subtask cannot run "
                f"in this mode and must be skipped or the mode raised"
            ),
        )

    # Tier 2 requires operator confirmation at the queue level — defense in
    # depth on top of the per-tool gates. The session pauses; the operator
    # uses `sov session approve <subtask_id>` to allow it.
    # NOTE: per-tool approval gates inside agent_loop still apply.
    if subtask.required_tier >= 2:
        # In v0.2.27 the queue-level approval ledger is the proposals channel
        # (already exists). For now: surface as requires_operator.
        return AuthorityCheck(
            allowed=False,
            requires_operator=True,
            reason=(
                f"subtask is tier {subtask.required_tier}; requires operator "
                f"confirmation. Use `sov session approve {subtask.id}` to allow, "
                f"or `sov session skip {subtask.id}` to skip."
            ),
        )

    return AuthorityCheck(allowed=True)


# ─────────────────────────────────────────────────────────────────────────
# Main entry points
# ─────────────────────────────────────────────────────────────────────────


@dataclass
class SessionResult:
    """What ``run_session`` returns."""
    session_id: str
    status: SessionStatus
    completed_subtasks: int
    total_subtasks: int
    total_iterations: int
    total_tokens: int
    elapsed_seconds: float
    pause_reason: str | None = None
    last_error: str | None = None


def new_session(
    *,
    goal: str,
    mode: Mode,
    initial_subtasks: list[Subtask] | None = None,
    max_subtasks: int = 50,
    store: SessionStore | None = None,
) -> SessionState:
    """Create a new session record. Does NOT start it running.

    If ``initial_subtasks`` is None, the session is created with the goal as
    its single first subtask — the agent will decompose dynamically via
    NEXT_SUBTASK proposals as it works. Pass a non-empty list when you've
    already decomposed up-front (e.g. via a planner or operator script).

    Returns the persisted SessionState. To execute, call ``run_session``.
    """
    store = store or SessionStore()
    sid = _new_id("sess")

    if initial_subtasks is None:
        initial_subtasks = [
            Subtask(id=_new_id("st"), description=goal, required_tier=1)
        ]
    elif len(initial_subtasks) > max_subtasks:
        raise SessionError(
            f"initial_subtasks ({len(initial_subtasks)}) exceeds max_subtasks "
            f"({max_subtasks}); raise max or decompose less"
        )

    state = SessionState(
        session_id=sid,
        goal=goal,
        mode=mode.value,
        subtasks=initial_subtasks,
        max_subtasks=max_subtasks,
    )
    store.save(state)
    emit_event(
        "session-new-d",
        plane="control",
        trace_id=sid,
        payload={"goal": goal[:500], "mode": mode.value,
                 "initial_subtasks": len(initial_subtasks)},
    )
    return state


async def run_session(
    *,
    session_id: str,
    tools: dict[str, Tool],
    budget: RunBudget | None = None,
    store: SessionStore | None = None,
    per_subtask_budget: RunBudget | None = None,
    horizon_required: bool = True,
) -> SessionResult:
    """Execute a session until drained, paused, halted, or budget-exceeded.

    Safe to call repeatedly on the same session_id — re-entry picks up at
    the next pending subtask. The function returns when one of:

      • all subtasks are done                → status="complete"
      • PROTOCOL-ZERO is armed               → status="halted"
      • interrupts.checkpoint signals pause  → status="paused"
      • the session-level budget is hit      → status="budget"
      • an unhandled error occurs            → status="error"

    The session file is updated atomically after every subtask transition,
    so a kernel crash mid-loop loses at most one subtask's work — never
    the session-level plan.

    ``horizon_required`` controls the Tier-2+ horizon gate (Phase 2 of the
    v0.3.0 roadmap, wired in v0.2.29.0). Default True — every Tier-2+
    subtask first generates a 3m/12m/3y/7g projection through the fast
    model. If generation fails, the subtask is blocked and the operator
    sees a `horizon-gate-blocked-d` event. Pass False to disable the gate
    entirely (e.g. in airgap mode where the fast model is unavailable).
    """
    store = store or SessionStore()
    budget = budget or RunBudget(
        max_iterations=200, max_wall_seconds=7200, max_tokens=2_000_000
    )
    # goal-modulator-d (Kevin, 2026-07-21): "remember this model is slower
    # so we might need to raise some timers." Root cause traced from a
    # real session: aria-orchestrator now runs on qwen3:14b (proven at
    # ~4 tok/s vs whatever the smaller base achieved) -- the OLD 600s
    # per-subtask ceiling let a single subtask get through only ~4
    # iterations before budget-blocking the whole session, nowhere near
    # a requested multi-hour run. Raised to 1800s (30 min/subtask).
    #
    # subtask-timeout-raise-d (Kevin, 2026-07-25): "It usually takes each
    # task between 10-20+ minutes. Close to 30 so maybe 45 minutes to 1
    # hour might be better." Raised again, 1800s -> 2700s (45 min) --
    # still a real, bounded ceiling per subtask, sized with headroom
    # above the observed 10-20+ min actual, not just the old floor.
    per_subtask_budget = per_subtask_budget or RunBudget(
        max_iterations=25, max_wall_seconds=2700, max_tokens=100_000
    )

    state = store.load(session_id)
    # garden-d — plant her garden from the persisted contract (survives
    # /resume for free); cleared in the finally below.
    _garden_planted = False
    try:
        from sovereign_agent.scope import load_scope as _g_load_scope

        _g_sc = _g_load_scope(session_id)
        if _g_sc is not None and _g_sc.garden_dir:
            from sovereign_agent.pathguard import set_garden as _g_set

            _g_set(_g_sc.garden_dir)
            _garden_planted = True
    except Exception:  # noqa: BLE001
        pass
    state.status = "active"
    state.started_at_monotonic = time.monotonic()
    # resume-orphan-recovery-d (Kevin, 2026-08-01): "the resume system should
    # work when I exit the TUI... it never seems to work." Root cause: a
    # subtask is marked "in_progress" (and saved) the instant it starts, but
    # only ever reset to "done"/"blocked" on a clean return from execution.
    # An abrupt exit mid-subtask (Ctrl+Q / /quit, which never routed through
    # the /rest safe-boundary path) left it stuck "in_progress" forever —
    # next_pending() only looks for "pending", so the interrupted subtask was
    # silently skipped on every future resume, and if it was the session's
    # last actionable subtask, resumable_sessions() dropped the whole session
    # from the menu (its "any pending" filter didn't count "in_progress").
    # Re-entry (fresh run_session call, which resume_goal_session always is)
    # means nothing is actually executing that subtask anymore — safe to
    # requeue it, matching this function's own docstring promise ("re-entry
    # picks up at the next pending subtask").
    for _s in state.subtasks:
        if _s.status == "in_progress":
            _s.status = "pending"
            _s.started_at = None
    store.save(state)

    mode = Mode(state.mode)

    # If the operator armed a pending resume, consume it now (clears the flag).
    resumed, prior_continuation = consume_resume()
    if resumed:
        emit_event(
            "session-resume-d",
            plane="control",
            trace_id=session_id,
            payload={"prior_continuation": prior_continuation},
        )

    final_status: SessionStatus = "active"
    pause_reason: str | None = None
    last_error: str | None = None

    with trace() as session_trace_id:
        emit_event(
            "session-start-d",
            plane="control",
            trace_id=session_trace_id,
            payload={"session_id": session_id, "subtasks_pending":
                     sum(1 for s in state.subtasks if s.status == "pending")},
        )

        while True:
            # ── Gate 1: PROTOCOL-ZERO ─────────────────────────────────
            if protocol_zero.is_armed():
                final_status = "halted"
                state.pause_reason = "protocol_zero"
                emit_event("session-halt-d", plane="control",
                           trace_id=session_trace_id,
                           payload={"reason": "protocol_zero"})
                break

            # ── Gate 2: Operator interrupt (soft) ─────────────────────
            if interrupt_checkpoint(continuation_id=session_id):
                final_status = "paused"
                pause_reason = "operator_interrupt"
                state.pause_reason = pause_reason
                emit_event("session-pause-d", plane="control",
                           trace_id=session_trace_id,
                           payload={"reason": pause_reason})
                break

            # ── Gate 3: Session-level budget ──────────────────────────
            try:
                _check_session_budget(state, budget)
            except BudgetExceeded as e:
                final_status = "budget"
                state.pause_reason = f"budget:{e.kind}"
                emit_event("session-budget-d", plane="control",
                           trace_id=session_trace_id,
                           payload={"kind": e.kind, "used": e.used,
                                    "limit": e.limit})
                break

            # ── Pull next pending subtask ─────────────────────────────
            current = state.next_pending()
            if current is None:
                held = state.held_subtask_ids()  # graduated-trust-d
                if held:
                    # Batch every held subtask into ONE approval ask —
                    # one human decision, zero lost momentum on the rest.
                    final_status = "paused"
                    pause_reason = "awaiting_approval:" + ",".join(held)
                    state.pause_reason = pause_reason
                    emit_event("session-held-batch-d", plane="control",
                               trace_id=session_trace_id,
                               payload={"held_subtask_ids": held,
                                        "count": len(held)})
                else:
                    final_status = "complete"
                    emit_event("session-complete-d", plane="control",
                               trace_id=session_trace_id,
                               payload=dict(zip(("done", "total"),
                                                state.progress())))
                break

            # ── Gate 4: Authority check at queue level ────────────────
            auth = check_subtask_authority(current, mode)
            if not auth.allowed:
                if auth.requires_operator:
                    if state.hold_and_continue:  # graduated-trust-d
                        # HOLD this one subtask; the rest of the queue
                        # keeps flowing — orchestration never dies because
                        # one subtask crossed a wall.
                        current.status = "awaiting_approval"
                        current.error = auth.reason
                        emit_event("subtask-held-d", plane="control",
                                   trace_id=session_trace_id,
                                   payload={"subtask_id": current.id,
                                            "tier": current.required_tier,
                                            "reason": auth.reason})
                        store.save(state)
                        continue
                    # legacy behavior: full-session pause (operator opted out
                    # of hold-and-continue for this session)
                    final_status = "paused"
                    pause_reason = f"awaiting_approval:{current.id}"
                    state.pause_reason = pause_reason
                    emit_event("session-pause-d", plane="control",
                               trace_id=session_trace_id,
                               payload={"reason": pause_reason,
                                        "subtask_id": current.id,
                                        "tier": current.required_tier})
                    break
                else:
                    # Hard reject — mark blocked and continue
                    current.status = "blocked"
                    current.error = auth.reason
                    current.completed_at = _utc_now()
                    emit_event("subtask-blocked-d", plane="control",
                               trace_id=session_trace_id,
                               payload={"subtask_id": current.id,
                                        "reason": auth.reason})
                    store.save(state)
                    continue

            # ── Execute the subtask through agent_loop ─────────────────
            try:
                await _execute_subtask(
                    state=state,
                    current=current,
                    mode=mode,
                    budget=per_subtask_budget,
                    tools=tools,
                    store=store,
                    parent_trace_id=session_trace_id,
                    horizon_required=horizon_required,
                )
            except Exception as e:  # noqa: BLE001 — session must never crash dirty
                current.status = "blocked"
                current.error = f"unhandled: {e!r}"[:500]
                current.completed_at = _utc_now()
                final_status = "error"
                last_error = current.error
                state.last_error = current.error
                emit_event("subtask-x", plane="control",
                           trace_id=session_trace_id,
                           payload={"subtask_id": current.id,
                                    "error": current.error})
                store.save(state)
                break

            store.save(state)

        # garden-d — the garden is per-session: clear before the final write.
        if _garden_planted:
            try:
                from sovereign_agent.pathguard import clear_garden as _g_clear

                _g_clear()
            except Exception:  # noqa: BLE001
                pass
        # ── Final write ──────────────────────────────────────────────
        state.status = final_status
        if pause_reason:
            state.pause_reason = pause_reason
        if last_error:
            state.last_error = last_error
        store.save(state)
        force_fsync()

        elapsed = (time.monotonic() - (state.started_at_monotonic or time.monotonic()))
        done, total = state.progress()

        emit_event("session-end-d", plane="control",
                   trace_id=session_trace_id,
                   payload={"status": final_status, "done": done,
                            "total": total, "elapsed_s": round(elapsed, 1)})

        return SessionResult(
            session_id=session_id,
            status=final_status,
            completed_subtasks=done,
            total_subtasks=total,
            total_iterations=state.total_iterations,
            total_tokens=state.total_tokens,
            elapsed_seconds=elapsed,
            pause_reason=state.pause_reason,
            last_error=state.last_error,
        )


# ─────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────


def _check_session_budget(state: SessionState, budget: RunBudget) -> None:
    """Session-level budget check. Per-subtask budgets are inside agent_loop."""
    if state.total_iterations >= budget.max_iterations:
        raise BudgetExceeded("iterations", used=state.total_iterations,
                             limit=budget.max_iterations)
    if state.total_tokens >= budget.max_tokens:
        raise BudgetExceeded("tokens", used=state.total_tokens,
                             limit=budget.max_tokens)
    if state.started_at_monotonic is not None:
        elapsed = time.monotonic() - state.started_at_monotonic
        wall_limit = effective_wall_limit(budget)  # safe-interval-stop-d
        if elapsed >= wall_limit:
            raise BudgetExceeded("wall_seconds", used=elapsed,
                                 limit=wall_limit)


def _write_horizon_atom(
    state: SessionState,
    current: Subtask,
    inputs,
    rendered_markdown: str,
) -> str:
    """Persist a horizon scan as an atom in atoms.db and return the atom_id.

    The atom carries:
      • summary: a one-line distillation (best_forward_path is the natural fit)
      • content_ref: inline markdown of the full scan
      • scope_tags: ['horizon', 'session:<sid>']
      • parents: a synthetic event ULID anchoring the scan to this subtask
      • created_by.actor: 'system' (auto-generated, not operator-verified)
      • confidence: 0.6 by default — horizon scans are forward projections,
                    intentionally below the high-stakes floor of 0.7

    Lives in its own helper so the session module doesn't import atom-write
    machinery into the hot path of the loop.
    """
    from .db import open_atoms_db
    from .memory.atom import Atom, write_atom

    summary = (
        inputs.best_forward_path[:200]
        or f"Horizon scan: {current.description[:200]}"
    )
    atom = Atom(
        type="horizon",
        summary=summary,
        content_ref={"kind": "inline", "text": rendered_markdown},
        claims=[],
        parents=[f"evt_session_{state.session_id}_{current.id}"],
        confidence=0.6,
        created_by={"actor": "system", "module": "horizon_gate"},
        scope_tags=["horizon", f"session:{state.session_id}"],
        policy="local_only",
    )
    conn = open_atoms_db()
    try:
        atom_id = write_atom(conn, atom)
        conn.commit()
    finally:
        conn.close()
    return atom_id


async def _execute_subtask(
    *,
    state: SessionState,
    current: Subtask,
    mode: Mode,
    budget: RunBudget,
    tools: dict[str, Tool],
    store: SessionStore,
    parent_trace_id: str,
    horizon_required: bool = True,
) -> None:
    """Run one subtask through the inner agent_loop and update session state.

    The agent_loop sees a goal composed of (1) the subtask description, and
    (2) the session guidance preamble that explains the queue mechanics and
    how to grow them.

    For Tier-2+ subtasks, the horizon gate fires first: a 3m/12m/3y/7g
    projection is generated via the fast model and attached to the subtask
    as ``horizon_atom_id``. The gate is advisory by default — the scan is
    surfaced to the operator via the event log, but the subtask is not
    blocked if generation fails. Set ``horizon_required=True`` (the default)
    to block on generation failure. Operator can pass ``horizon_required=False``
    on ``run_session`` to disable the gate entirely.

    On agent_loop completion:
      - parses RESULT: into subtask.result_summary
      - parses NEXT_SUBTASK: into new subtasks appended to the queue
      - rolls iterations + tokens into session totals
    """
    current.status = "in_progress"
    current.started_at = _utc_now()
    store.save(state)

    # sub-events-d (Kevin, 2026-07-21): "harden her events system...
    # maybe she needs events that have sub events." Every other event
    # emitted about THIS subtask below is now a child of its own start
    # event (emit_child_event, parent_id=_subtask_start_event_id) — a
    # real, queryable parent/children tree (events.event_tree()), not
    # just a flat trace_id list to eyeball in timestamp order.
    _subtask_start_event_id = emit_event(
        "subtask-start-d", plane="control",
        trace_id=parent_trace_id,
        payload={"subtask_id": current.id,
                 "description": current.description[:300],
                 "tier": current.required_tier})

    # full-observability-d (Kevin, 2026-07-26): "I want her to be upfront
    # about everything she plans to do, is doing, and wants to do." Before
    # this, narrate_subtask only ever fired on COMPLETION — nothing
    # announced the plan before she started. Best-effort + throttled
    # inside narrate(); can never break the session.
    try:
        from sovereign_agent.work_narrator import narrate_intent
        narrate_intent(state.session_id, current.description)
    except Exception:  # noqa: BLE001
        pass

    # ── Gate 6 (per architecture §6, the deferred Phase 2 wire-up): ────
    # Horizon scan for Tier-2+ subtasks. Generates a 3m/12m/3y/7g
    # projection through the fast model and attaches the atom_id slot
    # to the subtask record. Honest degradation: on fast-model failure,
    # block (if horizon_required) or log-and-continue (if not).
    if (horizon_required
            and current.required_tier >= 2
            and current.horizon_atom_id is None):
        try:
            from .horizon import generate_for_subtask, render

            inputs = await generate_for_subtask(
                label=f"session-{state.session_id}-{current.id}",
                decision=current.description,
            )
        except Exception as e:  # noqa: BLE001
            inputs = None
            emit_child_event(
                "horizon-gate-x", plane="control",
                trace_id=parent_trace_id, parent_id=_subtask_start_event_id,
                payload={"subtask_id": current.id,
                         "error": str(e)[:200]},
            )

        if inputs is None:
            # Generation failed (fast model unreachable or empty response).
            # Block the subtask — operator will see the event and can
            # rerun with horizon_required=False if they accept the risk.
            current.status = "blocked"
            current.error = (
                "horizon scan generation failed; Tier-2+ subtask blocked. "
                "Verify fast model availability (`sov doctor`), or rerun "
                "with horizon_required=False if the gate is not needed."
            )
            current.completed_at = _utc_now()
            emit_child_event("horizon-gate-blocked-d", plane="control",
                             trace_id=parent_trace_id, parent_id=_subtask_start_event_id,
                             payload={"subtask_id": current.id})
            return

        # Generation succeeded — render the scan as an atom and attach.
        # We store the rendered markdown in the atom's content_ref so it's
        # retrievable later via the standard atom-read paths.
        try:
            atom_id = _write_horizon_atom(state, current, inputs, render(inputs))
            current.horizon_atom_id = atom_id
            emit_child_event("horizon-gate-d", plane="control",
                             trace_id=parent_trace_id, parent_id=_subtask_start_event_id,
                             payload={"subtask_id": current.id,
                                      "atom_id": atom_id,
                                      "best_path": inputs.best_forward_path[:200]})
        except Exception as e:  # noqa: BLE001
            # Atom write failed — degrade to log-only; don't block.
            # The scan was generated and the rationale was emitted; that's
            # the gate's load-bearing observability surface.
            emit_child_event("horizon-atom-x", plane="control",
                             trace_id=parent_trace_id, parent_id=_subtask_start_event_id,
                             payload={"subtask_id": current.id,
                                      "error": str(e)[:200]})

        store.save(state)

    composed_goal = (
        _format_session_guidance(state, current)
        + "\n\n═══ THIS SUBTASK ═══\n"
        + current.description
    )
    # session-bridge-d — Kevin's no-interrupt rule, delivery side: messages he
    # sent while she was mid-subtask were QUEUED (to_aria inbox, tagged);
    # each subtask start is a safe boundary by construction, so they
    # fold into her context here. Best-effort — never blocks the run.
    try:
        from sovereign_agent.session_bridge import drain_operator_messages

        _sb_notes = drain_operator_messages()
        if _sb_notes:
            emit_child_event("session-notes-d", plane="control",
                             trace_id=parent_trace_id, parent_id=_subtask_start_event_id,
                             payload={"count": len(_sb_notes)})
            composed_goal += (
                "\n\n═══ OPERATOR MESSAGES (delivered at this safe boundary) ═══\n"
                + "\n".join(f"• {_n[:500]}" for _n in _sb_notes)
            )
    except Exception:  # noqa: BLE001
        pass

    loop_result: LoopResult = await agent_loop(
        goal=composed_goal,
        mode=mode,
        budget=budget,
        tools=tools,
        enable_reflector=False,  # session-level reflection happens on end
    )

    # Record the agent_loop's trace via metadata (the loop emits its own
    # ingest-d / settle-d events; we capture the link).
    current.trace_id = parent_trace_id  # session trace for top-level join
    current.iterations = loop_result.iterations
    current.tokens = loop_result.tokens_used
    current.completed_at = _utc_now()

    state.total_iterations += loop_result.iterations
    state.total_tokens += loop_result.tokens_used

    final_text = loop_result.final_message or ""
    if loop_result.ok:
        current.status = "done"
        current.result_summary = parse_result_summary(final_text)
        emit_child_event("subtask-done-d", plane="control",
                         trace_id=parent_trace_id, parent_id=_subtask_start_event_id,
                         payload={"subtask_id": current.id,
                                  "iterations": loop_result.iterations,
                                  "tokens": loop_result.tokens_used,
                                  "summary": current.result_summary[:200]})
        # F5 (Kevin, 2026-07-19): narrate the shift to #owner-bridge —
        # best-effort + throttled inside; can never break the session
        try:
            from sovereign_agent.work_narrator import narrate_subtask
            n_done, n_total = state.progress()
            narrate_subtask(state.session_id, n_done, n_total,
                            current.result_summary)
        except Exception:  # noqa: BLE001
            pass

        # ── Grow the queue from proposals in the final message ──────
        try:
            proposals = parse_proposals(final_text)
        except SessionError as e:
            # Malformed proposal — don't fail the whole subtask; surface as warning
            emit_child_event("subtask-proposal-x", plane="control",
                             trace_id=parent_trace_id, parent_id=_subtask_start_event_id,
                             payload={"subtask_id": current.id, "error": str(e)})
            proposals = []

        room = state.max_subtasks - len(state.subtasks)
        if room <= 0 and proposals:
            emit_child_event("session-queue-full-d", plane="control",
                             trace_id=parent_trace_id, parent_id=_subtask_start_event_id,
                             payload={"dropped": len(proposals),
                                      "max": state.max_subtasks})
        # scope-contract-d — the teeth, at the exact door scope creep enters:
        # proposals tripping the contract's out list are HELD (blocked,
        # scope-review) instead of silently joining the queue; crossing
        # the drift threshold fires a one-time scope-drift-d.
        _sc_contract = None
        try:
            from sovereign_agent.scope import DRIFT_THRESHOLD, load_scope

            _sc_contract = load_scope(state.session_id)
        except Exception:  # noqa: BLE001
            _sc_contract = None
        for desc, tier in proposals[:max(0, room)]:
            new = Subtask(
                id=_new_id("st"),
                description=desc,
                required_tier=tier,
                parent_id=current.id,
            )
            if _sc_contract is not None and _sc_contract.is_out_of_scope(desc):
                new.status = "blocked"
                new.error = "scope-review: outside the declared contract"
                state.subtasks.append(new)
                emit_child_event("scope-review-d", plane="control",
                                 trace_id=parent_trace_id, parent_id=_subtask_start_event_id,
                                 payload={"subtask_id": new.id,
                                          "description": desc[:200]})
                continue
            state.subtasks.append(new)
            emit_child_event("subtask-proposed-d", plane="control",
                             trace_id=parent_trace_id, parent_id=_subtask_start_event_id,
                             payload={"subtask_id": new.id,
                                      "parent_id": current.id,
                                      "tier": tier,
                                      "description": desc[:200]})
        if (_sc_contract is not None
                and len(state.subtasks) >= DRIFT_THRESHOLD * _sc_contract.max_subtasks
                and not getattr(state, "_scope_drift_emitted", False)):
            state._scope_drift_emitted = True  # in-memory once-per-run guard
            emit_child_event("scope-drift-d", plane="control",
                             trace_id=parent_trace_id, parent_id=_subtask_start_event_id,
                             payload={"subtasks": len(state.subtasks),
                                      "max": _sc_contract.max_subtasks})

        # inbox-cadence-d (Kevin, 2026-07-26): "she needs to be emptying her
        # inbox every 15 minutes or so... keep her inbox empty." Real,
        # structural nudge at the one place every subtask already passes
        # through — never busywork on a clean inbox, never when the queue
        # is already full, and the clock resets either way so a quiet
        # inbox doesn't get re-checked every single subtask boundary.
        try:
            _now_mono = time.monotonic()
            _last_nudge = getattr(state, "_last_inbox_nudge_mono", None)
            if ((_last_nudge is None or _now_mono - _last_nudge >= INBOX_CADENCE_S)
                    and (state.max_subtasks - len(state.subtasks)) > 0):
                from sovereign_agent.persistence.store import ErebloStore
                from sovereign_agent.workflow.requests import RequestStore
                _rs = RequestStore(ErebloStore(SETTINGS.paths.atoms_db))
                _open_for_aria = _rs.list_for_aria()
                if _open_for_aria:
                    state.subtasks.append(Subtask(
                        id=_new_id("st"),
                        description=(
                            "Check your inbox (read_inbox) and close out "
                            "anything you can actually resolve now "
                            "(acknowledge_inbox_note) — keep it empty."),
                        required_tier=0,
                        parent_id=current.id,
                    ))
                    emit_child_event(
                        "inbox-cadence-nudge-d", plane="control",
                        trace_id=parent_trace_id, parent_id=_subtask_start_event_id,
                        payload={"open_count": len(_open_for_aria)})
                state._last_inbox_nudge_mono = _now_mono
        except Exception:  # noqa: BLE001 — a nudge can never break the session
            pass
    else:
        current.status = "blocked"
        current.error = loop_result.reason or "unknown"
        current.result_summary = (
            f"blocked: {loop_result.reason or 'unknown'}"
        )
        emit_child_event("subtask-blocked-d", plane="control",
                         trace_id=parent_trace_id, parent_id=_subtask_start_event_id,
                         payload={"subtask_id": current.id,
                                  "reason": loop_result.reason,
                                  "iterations": loop_result.iterations})


# ─────────────────────────────────────────────────────────────────────────
# Operator-facing helpers (used by CLI sub-app `sov session ...`)
# ─────────────────────────────────────────────────────────────────────────


def approve_subtask(
    session_id: str,
    subtask_id: str,
    *,
    store: SessionStore | None = None,
) -> SessionState:
    """Operator override: approve a Tier-2+ subtask so it can run on resume.

    Lowers the subtask's required_tier to 1 (still bounded — operator approval
    is not a tier-3 grant, that goes through the existing approval system).
    Returns the updated SessionState.

    For Tier-3 work, the per-tool approval inside agent_loop still requires
    an approval token. This function approves QUEUE dispatch only; tool-level
    gates remain enforced.
    """
    store = store or SessionStore()
    state = store.load(session_id)
    for s in state.subtasks:
        if s.id == subtask_id:
            if s.status not in ("pending", "blocked", "awaiting_approval"):  # graduated-trust-d
                raise SessionError(
                    f"subtask {subtask_id} is {s.status}, not approvable")
            # Drop to tier 1 for queue dispatch; tool-level gates still apply
            s.required_tier = min(s.required_tier, 1)
            s.status = "pending"
            s.error = None
            state.pause_reason = None
            state.status = "active"
            store.save(state)
            emit_event("subtask-approve-d", plane="control",
                       trace_id=session_id,
                       payload={"subtask_id": subtask_id})
            return state
    raise SessionError(f"subtask not found: {subtask_id}")


def skip_subtask(
    session_id: str,
    subtask_id: str,
    *,
    reason: str = "operator_skip",
    store: SessionStore | None = None,
) -> SessionState:
    """Operator override: mark a subtask skipped (it will not run)."""
    store = store or SessionStore()
    state = store.load(session_id)
    for s in state.subtasks:
        if s.id == subtask_id:
            s.status = "skipped"
            s.completed_at = _utc_now()
            s.result_summary = f"skipped: {reason}"
            state.pause_reason = None
            state.status = "active"
            store.save(state)
            emit_event("subtask-skip-d", plane="control",
                       trace_id=session_id,
                       payload={"subtask_id": subtask_id, "reason": reason})
            return state
    raise SessionError(f"subtask not found: {subtask_id}")


def halt_session(
    session_id: str,
    *,
    reason: str = "operator_halt",
    store: SessionStore | None = None,
) -> SessionState:
    """Mark a session as halted. Does NOT signal a running process — set
    PROTOCOL-ZERO via ``protocol_zero.arm()`` for that. This is the
    follow-up to record why the halt was called.
    """
    store = store or SessionStore()
    state = store.load(session_id)
    state.status = "halted"
    state.pause_reason = reason
    store.save(state)
    emit_event("session-halt-d", plane="control",
               trace_id=session_id, payload={"reason": reason})
    return state


# ─────────────────────────────────────────────────────────────────────────
# Graduated trust — graduated-trust-d
# ─────────────────────────────────────────────────────────────────────────


@dataclass
class PlanRevision:
    """One mid-work plan edit — the audit-trail twin of QueueExtension.
    Kevin: 'make sure she can update plans mid work while continuing all
    her other current tasks resiliently.' Only PENDING subtasks are ever
    touched; the in-progress subtask and any held/done ones are untouched
    by construction — work never pauses to let the plan change."""
    at: str
    op: str                    # "reorder" | "remove" | "edit"
    subtask_ids: list[str]
    justification: str


def approve_all_held(session_id: str, *, store: "SessionStore | None" = None) -> "SessionState":
    """Approve every awaiting_approval subtask in one call — the 'one
    human decision' the batched pause promises. Tool-level Tier-3 gates
    still apply inside agent_loop; this approves QUEUE dispatch only."""
    store = store or SessionStore()
    state = store.load(session_id)
    held = state.held_subtask_ids()
    for sid in held:
        state = approve_subtask(session_id, sid, store=store)
    return state


def revise_pending_subtasks(
    state: "SessionState",
    *,
    reorder: list[str] | None = None,
    remove_ids: list[str] | None = None,
    edits: dict[str, str] | None = None,
    justification: str,
) -> PlanRevision:
    """Revise the PENDING half of the plan mid-work — resiliently: the
    currently in_progress subtask (and anything done/blocked/held) is
    NEVER touched, so a plan edit never interrupts running work.

    reorder: a full permutation of PENDING ids, new relative order.
    remove_ids: pending ids to drop (marked 'skipped', reason recorded —
                the audit trail keeps them, per the skip_subtask
                convention; never a silent delete).
    edits: {subtask_id: new_description} for pending subtasks only.

    Raises ValueError naming the offending id if any target is not
    currently pending — a plan can rearrange the road ahead, never the
    ground already crossed or a subtask a wall is holding.
    """
    justification = (justification or "").strip()
    if not justification:
        raise ValueError(
            "plan revision requires a justification — the audit trail "
            "must capture WHY the plan changed")

    pending_ids = {s.id for s in state.subtasks if s.status == "pending"}
    touched: list[str] = []

    if remove_ids:
        for sid in remove_ids:
            if sid not in pending_ids:
                raise ValueError(
                    f"cannot remove {sid!r}: not currently pending "
                    f"(only the road ahead can be revised)")
        for s in state.subtasks:
            if s.id in remove_ids:
                s.status = "skipped"
                s.completed_at = _utc_now()
                s.result_summary = f"skipped: plan revision — {justification}"
                touched.append(s.id)

    if edits:
        for sid, new_desc in edits.items():
            if sid not in pending_ids or sid in (remove_ids or []):
                raise ValueError(
                    f"cannot edit {sid!r}: not currently pending")
        for s in state.subtasks:
            if s.id in edits:
                s.description = edits[s.id]
                touched.append(s.id)

    if reorder:
        remaining_pending = [sid for sid in pending_ids if sid not in (remove_ids or [])]
        if set(reorder) != set(remaining_pending):
            raise ValueError(
                "reorder must be a permutation of the currently-pending, "
                "non-removed subtask ids")
        by_id = {s.id: s for s in state.subtasks}
        new_list: list[Subtask] = []
        reorder_iter = iter(reorder)
        for s in state.subtasks:
            if s.id in remaining_pending:
                new_list.append(by_id[next(reorder_iter)])
            else:
                new_list.append(s)
        state.subtasks = new_list
        touched.extend(reorder)

    record = PlanRevision(
        at=_utc_now(),
        op="+".join(filter(None, [
            "reorder" if reorder else "",
            "remove" if remove_ids else "",
            "edit" if edits else "",
        ])) or "noop",
        subtask_ids=sorted(set(touched)),
        justification=justification,
    )
    state.plan_revisions.append(record)
    state.updated_at = _utc_now()
    try:
        emit_event("session-revise-d", plane="control", trace_id=state.session_id,
                   payload={"session_id": state.session_id, "op": record.op,
                            "subtask_ids": record.subtask_ids,
                            "justification": justification})
    except Exception:  # noqa: BLE001 — best-effort, matches extend_session_queue
        pass
    return record


__all__ = [
    "Subtask",
    "SubtaskStatus",
    "SessionState",
    "SessionStatus",
    "SessionStore",
    "SessionResult",
    "SessionError",
    "AuthorityCheck",
    "check_subtask_authority",
    "new_session",
    "run_session",
    "approve_subtask",
    "skip_subtask",
    "halt_session",
    "parse_proposals",
    "parse_result_summary",
    "PlanRevision",
    "approve_all_held",
    "revise_pending_subtasks",
]
