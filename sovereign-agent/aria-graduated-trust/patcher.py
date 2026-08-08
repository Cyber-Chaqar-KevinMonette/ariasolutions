"""patcher.py — FABLE II M7: graduated trust (hold-and-continue at Gate 4).

Kevin: *"propose not act should not prevent her from being a forward-motion
worker."* The doctrine lives at DECISION BOUNDARIES, not micro-actions:
inside an armed mode + scope + garden + budget she moves freely; proposing
is reserved for crossing walls. The concrete bottleneck this closes: Gate
4 used to pause the WHOLE session at the first over-tier subtask, no
matter how much of the queue was still runnable.

Patches:
  1. agent_session.py — SubtaskStatus gains "awaiting_approval";
     SessionState gains hold_and_continue (default True) + PlanRevision
     tracking; Gate 4 HOLDS the over-tier subtask and keeps the queue
     flowing; session end batches every held subtask into ONE pause;
     approve_subtask accepts "awaiting_approval"; new approve_all_held()
     and revise_pending_subtasks() (Kevin's mid-round ask: update the plan
     while the rest of the work keeps flowing — the running subtask is
     NEVER touched).
  2. cli.py — `sov session status|approve|approve-all|skip|revise`: the
     CLI surface the code's own reason strings already promised
     ("Use `sov session approve <id>`") but that never existed.
  3. cockpit/app.py — `/approve [id]` slash verb (mirrors `/resume`'s shape).
  4. proving_ground/runner.py — the trust wing (suite v2 → v3).
  5. Doctrine text, same words, one place each: loop.py's AUTONOMY prompt
     section, handoff/02_SAFETY_MODEL.md item 3, CLAUDE.md golden rule 1.

Anchored transforms only; MARK-idempotent; a moved anchor raises loudly."""
from __future__ import annotations

MARK = "graduated-trust-d"
DOCTRINE_WORDS = "propose at boundaries; move freely inside grants"


class PatchError(Exception):
    pass


def _replace_once(text: str, old: str, new: str, *, label: str) -> str:
    if text.count(old) != 1:
        raise PatchError(f"{label}: expected 1 anchor, found {text.count(old)}")
    return text.replace(old, new, 1)


# ── 1. agent_session.py ──────────────────────────────────────────────────

STATUS_ANCHOR = ('SubtaskStatus = Literal["pending", "in_progress", "done", '
                 '"blocked", "skipped"]\n')
STATUS_NEW = (
    'SubtaskStatus = Literal["pending", "in_progress", "done", "blocked", '
    f'"skipped", "awaiting_approval"]  # {MARK}\n'
)

STATE_FIELDS_ANCHOR = """    extensions: list[QueueExtension] = field(default_factory=list)
    original_subtask_count: int = 0                 # snapshot of initial plan size

    # ── derived ────────────────────────────────────────────────────────
"""

STATE_FIELDS_NEW = f"""    extensions: list[QueueExtension] = field(default_factory=list)
    original_subtask_count: int = 0                 # snapshot of initial plan size

    # {MARK} — graduated trust: hold-and-continue (default ON) means an
    # over-tier subtask is HELD, never a full-session stop; plan revisions
    # (mid-work plan edits, never touching the running subtask) tracked
    # the same audit-trail way extensions already are.
    hold_and_continue: bool = True
    plan_revisions: list[PlanRevision] = field(default_factory=list)

    def held_subtask_ids(self) -> list[str]:  # {MARK}
        return [s.id for s in self.subtasks if s.status == "awaiting_approval"]

    # ── derived ────────────────────────────────────────────────────────
"""

GATE4_ANCHOR = """            # ── Gate 4: Authority check at queue level ────────────────
            auth = check_subtask_authority(current, mode)
            if not auth.allowed:
                if auth.requires_operator:
                    # Pause; operator can approve or skip via CLI
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
"""

GATE4_NEW = f"""            # ── Gate 4: Authority check at queue level ────────────────
            auth = check_subtask_authority(current, mode)
            if not auth.allowed:
                if auth.requires_operator:
                    if state.hold_and_continue:  # {MARK}
                        # HOLD this one subtask; the rest of the queue
                        # keeps flowing — orchestration never dies because
                        # one subtask crossed a wall.
                        current.status = "awaiting_approval"
                        current.error = auth.reason
                        emit_event("subtask-held-d", plane="control",
                                   trace_id=session_trace_id,
                                   payload={{"subtask_id": current.id,
                                            "tier": current.required_tier,
                                            "reason": auth.reason}})
                        store.save(state)
                        continue
                    # legacy behavior: full-session pause (operator opted out
                    # of hold-and-continue for this session)
                    final_status = "paused"
                    pause_reason = f"awaiting_approval:{{current.id}}"
                    state.pause_reason = pause_reason
                    emit_event("session-pause-d", plane="control",
                               trace_id=session_trace_id,
                               payload={{"reason": pause_reason,
                                        "subtask_id": current.id,
                                        "tier": current.required_tier}})
                    break
                else:
"""

COMPLETE_ANCHOR = """            current = state.next_pending()
            if current is None:
                final_status = "complete"
                emit_event("session-complete-d", plane="control",
                           trace_id=session_trace_id,
                           payload=dict(zip(("done", "total"),
                                            state.progress())))
                break
"""

COMPLETE_NEW = f"""            current = state.next_pending()
            if current is None:
                held = state.held_subtask_ids()  # {MARK}
                if held:
                    # Batch every held subtask into ONE approval ask —
                    # one human decision, zero lost momentum on the rest.
                    final_status = "paused"
                    pause_reason = "awaiting_approval:" + ",".join(held)
                    state.pause_reason = pause_reason
                    emit_event("session-held-batch-d", plane="control",
                               trace_id=session_trace_id,
                               payload={{"held_subtask_ids": held,
                                        "count": len(held)}})
                else:
                    final_status = "complete"
                    emit_event("session-complete-d", plane="control",
                               trace_id=session_trace_id,
                               payload=dict(zip(("done", "total"),
                                                state.progress())))
                break
"""

APPROVE_ANCHOR = """    for s in state.subtasks:
        if s.id == subtask_id:
            if s.status not in ("pending", "blocked"):
                raise SessionError(
                    f"subtask {subtask_id} is {s.status}, not approvable")
"""

APPROVE_NEW = f"""    for s in state.subtasks:
        if s.id == subtask_id:
            if s.status not in ("pending", "blocked", "awaiting_approval"):  # {MARK}
                raise SessionError(
                    f"subtask {{subtask_id}} is {{s.status}}, not approvable")
"""

TAIL_ANCHOR = '''__all__ = [
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
]
'''

TAIL_NEW = f'''# ─────────────────────────────────────────────────────────────────────────
# Graduated trust — {MARK}
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
    edits: {{subtask_id: new_description}} for pending subtasks only.

    Raises ValueError naming the offending id if any target is not
    currently pending — a plan can rearrange the road ahead, never the
    ground already crossed or a subtask a wall is holding.
    """
    justification = (justification or "").strip()
    if not justification:
        raise ValueError(
            "plan revision requires a justification — the audit trail "
            "must capture WHY the plan changed")

    pending_ids = {{s.id for s in state.subtasks if s.status == "pending"}}
    touched: list[str] = []

    if remove_ids:
        for sid in remove_ids:
            if sid not in pending_ids:
                raise ValueError(
                    f"cannot remove {{sid!r}}: not currently pending "
                    f"(only the road ahead can be revised)")
        for s in state.subtasks:
            if s.id in remove_ids:
                s.status = "skipped"
                s.completed_at = _utc_now()
                s.result_summary = f"skipped: plan revision — {{justification}}"
                touched.append(s.id)

    if edits:
        for sid, new_desc in edits.items():
            if sid not in pending_ids or sid in (remove_ids or []):
                raise ValueError(
                    f"cannot edit {{sid!r}}: not currently pending")
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
        by_id = {{s.id: s for s in state.subtasks}}
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
                   payload={{"session_id": state.session_id, "op": record.op,
                            "subtask_ids": record.subtask_ids,
                            "justification": justification}})
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
'''


def patch_agent_session(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    text = _replace_once(text, STATUS_ANCHOR, STATUS_NEW, label="status literal")
    text = _replace_once(text, STATE_FIELDS_ANCHOR, STATE_FIELDS_NEW,
                         label="state fields")
    text = _replace_once(text, GATE4_ANCHOR, GATE4_NEW, label="gate 4")
    text = _replace_once(text, COMPLETE_ANCHOR, COMPLETE_NEW, label="complete branch")
    text = _replace_once(text, APPROVE_ANCHOR, APPROVE_NEW, label="approve_subtask")
    text = _replace_once(text, TAIL_ANCHOR, TAIL_NEW, label="tail + __all__")
    return text, True


# ── 2. cli.py — `sov session ...` ────────────────────────────────────────

CLI_ANCHOR = 'app.add_typer(vault_app, name="vault")\n'

CLI_BLOCK = f'''

# ─── sov session — graduated trust: status / approve / revise (FABLE II M7) {MARK} ───

session_app = typer.Typer(
    help="Inspect and steer a running/paused agent_session: held "
         "subtasks batch into one approval ask; plans can be revised "
         "mid-work without touching the subtask currently running.")


@session_app.command("status")
def session_status_cmd(session_id: str = typer.Argument(...)) -> None:
    """Show a session's progress, held subtasks, and revision history."""
    from sovereign_agent.agent_session import SessionStore

    try:
        state = SessionStore().load(session_id)
    except Exception as e:  # noqa: BLE001
        _die(ExitCode.USAGE, str(e))
    done, total = state.progress()
    held = state.held_subtask_ids()
    if STATE.json_out:
        _emit_json({{"session_id": state.session_id, "status": state.status,
                    "done": done, "total": total, "held": held}})
        raise typer.Exit(ExitCode.OK)
    _print(f"session {{state.session_id}} · {{state.status}} · {{done}}/{{total}} done")
    if held:
        _print(f"  held (awaiting approval): {{', '.join(held)}}")
        for s in state.subtasks:
            if s.id in held:
                _print(f"    {{s.id}}: tier {{s.required_tier}} — {{s.description[:80]}}")
    if state.plan_revisions:
        _print(f"  {{len(state.plan_revisions)}} plan revision(s)")


@session_app.command("approve")
def session_approve_cmd(
    session_id: str = typer.Argument(...),
    subtask_id: str = typer.Argument(
        "", help="Subtask id to approve; omit with --all to approve every held one."),
    all_held: bool = typer.Option(False, "--all", help="Approve every held subtask."),
) -> None:
    """Approve a held (or every held) subtask so it can run on resume."""
    from sovereign_agent.agent_session import (
        SessionError, approve_all_held, approve_subtask,
    )

    try:
        if all_held or not subtask_id:
            state = approve_all_held(session_id)
        else:
            state = approve_subtask(session_id, subtask_id)
    except SessionError as e:
        _die(ExitCode.USAGE, str(e))
    _print(f"[green]approved.[/green] `sov session resume {{session_id}}` "
           f"(or /resume in the cockpit) to continue.")


@session_app.command("skip")
def session_skip_cmd(
    session_id: str = typer.Argument(...),
    subtask_id: str = typer.Argument(...),
    reason: str = typer.Option("operator_skip", "--reason"),
) -> None:
    """Mark a subtask skipped — it will not run."""
    from sovereign_agent.agent_session import SessionError, skip_subtask

    try:
        skip_subtask(session_id, subtask_id, reason=reason)
    except SessionError as e:
        _die(ExitCode.USAGE, str(e))
    _print("[green]skipped.[/green]")


@session_app.command("revise")
def session_revise_cmd(
    session_id: str = typer.Argument(...),
    remove: list[str] = typer.Option([], "--remove", help="Pending subtask id to drop (repeatable)."),
    justification: str = typer.Option(..., "--why", help="Required — the audit trail's WHY."),
) -> None:
    """Revise the plan's PENDING half mid-work — never touches the
    subtask currently running."""
    from sovereign_agent.agent_session import (
        SessionStore, revise_pending_subtasks,
    )

    store = SessionStore()
    state = store.load(session_id)
    try:
        record = revise_pending_subtasks(
            state, remove_ids=remove or None, justification=justification)
    except ValueError as e:
        _die(ExitCode.USAGE, str(e))
    store.save(state)
    _print(f"[green]plan revised[/green] ({{record.op}}): {{record.subtask_ids}}")


app.add_typer(session_app, name="session")

'''

CLI_NEW = CLI_ANCHOR + CLI_BLOCK


def patch_cli(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    return _replace_once(text, CLI_ANCHOR, CLI_NEW, label="cli anchor"), True


# ── 3. cockpit/app.py — /approve slash verb ──────────────────────────────

APP_SLASH_ANCHOR = """        elif verb == "resume":  # resume-spine-d
            self._resume_work_session(arg)
"""

APP_SLASH_NEW = APP_SLASH_ANCHOR + f'''        elif verb == "approve":  # {MARK}
            self._approve_held_subtask(arg)
'''

APP_HANDLER_ANCHOR = "    def _resume_work_session(self, arg: str) -> None:  # resume-spine-d\n"

APP_HANDLER_NEW = f'''    def _approve_held_subtask(self, arg: str) -> None:  # {MARK}
        """`/approve [id]` — approve a held subtask (or every held one with
        no id given) on the most recently resumable session, then hint at
        `/resume`. Mirrors `/resume`'s discovery shape."""
        from sovereign_agent.agent_session import SessionError, approve_all_held, approve_subtask
        from sovereign_agent.session_bridge import resumable_sessions

        arg = (arg or "").strip()
        candidates = [s for s in resumable_sessions(limit=10) if s.held_subtask_ids()]
        if not candidates:
            self._write_meta("[dim]◈ nothing held — every session's queue is clear[/dim]")
            return
        state = candidates[0]
        try:
            if arg:
                approve_subtask(state.session_id, arg)
                self._write_meta(f"[green]◈ approved {{arg}}[/green] — /resume to continue")
            else:
                approved = approve_all_held(state.session_id)
                self._write_meta(
                    f"[green]◈ approved {{len(state.held_subtask_ids())}} held "
                    f"subtask(s)[/green] — /resume to continue")
        except SessionError as exc:
            self._write_meta(f"[yellow]{{exc}}[/yellow]")

    def _resume_work_session(self, arg: str) -> None:  # resume-spine-d
'''


def patch_app(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    text = _replace_once(text, APP_SLASH_ANCHOR, APP_SLASH_NEW, label="slash verb")
    text = _replace_once(text, APP_HANDLER_ANCHOR, APP_HANDLER_NEW, label="handler")
    return text, True


# ── 4. proving_ground/runner.py — the trust wing (v2 → v3) ──────────────

VERSION_ANCHOR = 'SUITE_VERSION = "v2"  # memory-proof-d — v2 adds the memory wing (5 tasks); stored scores keep naming the suite they scored\n'
VERSION_NEW = (f'SUITE_VERSION = "v3"  # {MARK} — v3 adds the graduated-trust '
              'wing (hold-and-continue); stored scores keep naming the suite '
              'they scored\n')

TASKS_ANCHOR = "OFFLINE_TASKS.update(MEMORY_TASKS)\n"
TASKS_NEW = TASKS_ANCHOR + f"""
# {MARK} — FABLE II M7: the graduated-trust wing (hold-and-continue: five
# T1s complete, one T2 holds — no full-session stop).
from .trust_wing import TRUST_TASKS  # noqa: E402

OFFLINE_TASKS.update(TRUST_TASKS)
"""


def patch_runner(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    text = _replace_once(text, VERSION_ANCHOR, VERSION_NEW, label="suite version")
    text = _replace_once(text, TASKS_ANCHOR, TASKS_NEW, label="offline tasks")
    return text, True


# ── 5. doctrine text — same words, one place each ────────────────────────

LOOP_ANCHOR = """═══ AUTONOMY ═══
Within Tier 0 (read/search/embed) and Tier 1 (sandbox writes, memory writes)
you act WITHOUT permission. Read what you need, write to your sandbox, record
what you learn in memory. The user expects you to do useful work without
asking — silence and progress are the goal.
"""

LOOP_NEW = LOOP_ANCHOR + f'''
The doctrine lives at DECISION BOUNDARIES, not micro-actions: {DOCTRINE_WORDS}.
Inside an armed mode, a scope contract, a garden, and a budget you act
FREELY at full speed — proposing is reserved for crossing walls (tier
ceiling, scope, garden, irreversible/outward acts, adopting a new goal),
never for walking inside them. When one subtask in a session's queue
crosses a wall, it is HELD for approval and the rest of the queue keeps
flowing — one held subtask is never the whole session stopping.  # {MARK}
'''


def patch_loop(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    return _replace_once(text, LOOP_ANCHOR, LOOP_NEW, label="autonomy section"), True


SAFETY_MODEL_ANCHOR = """3. **The four session gates** (`run_session`): PROTOCOL-ZERO (`/halt`,
   instant) → operator interrupt (pause at boundary) → session budget
   WITH safety margin → per-subtask authority (over-tier pauses for
   approval).
"""

SAFETY_MODEL_NEW = f"""3. **The four session gates** (`run_session`): PROTOCOL-ZERO (`/halt`,
   instant) → operator interrupt (pause at boundary) → session budget
   WITH safety margin → per-subtask authority (over-tier subtasks are
   HELD, not a full-session stop — hold-and-continue, default on; every
   held subtask batches into ONE approval ask; `sov session approve`
   resumes them). Doctrine: {DOCTRINE_WORDS}.
"""


def patch_safety_model(text: str) -> tuple[str, bool]:
    if DOCTRINE_WORDS in text:
        return text, False
    return _replace_once(text, SAFETY_MODEL_ANCHOR, SAFETY_MODEL_NEW,
                         label="safety model item 3"), True


CLAUDE_MD_ANCHOR = ("1. **Propose, then let the human apply.** Prefer **Plan Mode** for "
                    "anything structural. Show diffs.\n   Never make irreversible "
                    "changes without explicit approval. This mirrors the project's own "
                    "sentinels:\n   they observe and advise — the operator acts.\n")

CLAUDE_MD_NEW = (
    "1. **Propose, then let the human apply.** Prefer **Plan Mode** for "
    "anything structural. Show diffs.\n   Never make irreversible changes "
    "without explicit approval. This mirrors the project's own sentinels:\n"
    "   they observe and advise — the operator acts. The doctrine lives at "
    f"decision boundaries, not micro-actions: {DOCTRINE_WORDS}.\n"
)


def patch_claude_md(text: str) -> tuple[str, bool]:
    if DOCTRINE_WORDS in text:
        return text, False
    return _replace_once(text, CLAUDE_MD_ANCHOR, CLAUDE_MD_NEW,
                         label="claude.md golden rule 1"), True


ALL_PATCHES = {
    "agent_session.py": patch_agent_session,
    "cli.py": patch_cli,
    "cockpit/app.py": patch_app,
    "proving_ground/runner.py": patch_runner,
    "loop.py": patch_loop,
}

DOC_PATCHES = {
    "handoff/02_SAFETY_MODEL.md": patch_safety_model,
    "CLAUDE.md": patch_claude_md,
}
