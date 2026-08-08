"""session_bridge.py — the natural-language front door to her finished engine.

THE ONE-LINE TRUTH this module exists for (Keys round research, 2026-07-04):
`agent_session.run_session` — Gates 1-4 (PROTOCOL-ZERO → operator-interrupt
→ session-budget-with-margin → authority), NEXT_SUBTASK decomposition,
per-subtask agent_loop execution, atomic checkpoint after every subtask —
was finished, tested, and had ZERO live callers. The autonomous engine was
never plugged into the natural-language front door. This is the plug.

Three small, honest functions:

  `start_goal_session(goal)` — the missing call site: new_session(goal) +
  run_session with the FULL tool registry and a work-interval-shaped
  budget (1h wall with a real safety margin — composing Workstream N's
  design). Sessions run in Mode.BUSY by default: tier ceiling 1, so any
  Tier-2+ subtask makes Gate 4 PAUSE for operator approval rather than
  running — the load-bearing safety default.

  `queue_operator_message(text)` / `drain_operator_messages()` — Kevin's
  no-interrupt rule. While she works, his messages never inject
  mid-iteration: the cockpit queues them into the dual-inbox `to_aria`
  direction (tagged, so notes left via `sov requests tell` are untouched),
  and the drain side folds them into her context at each subtask start —
  a safe boundary by construction. `/halt` and PROTOCOL-ZERO bypass the
  queue entirely: safety outranks politeness.

The gate that finally gets its caller: the cockpit invokes
`cockpit_modes.autonomous_loops_allowed()` before starting anything —
work mode runs, chat mode proposes and waits. `/mode work` stops being
cosmetic today.
"""
from __future__ import annotations

QUEUE_TAG = "session-queued"


def _resolve_default_mode():
    """auto-crown-tier-unify-d (Kevin, 2026-07-30): "me allowing tier 3 or
    tier 4 does nothing." Root cause: `start_goal_session` always defaulted
    to Mode.BUSY (tier ceiling 1) regardless of an active, explicitly-armed
    AutoCrownStore session at a higher tier — two tier systems that could
    disagree, and only one of them was ever something Kevin actually
    controls. His arming wins when it's genuinely active (checked fresh
    here — AutoCrownStore auto-reverts on its own if the arming expired).
    Mode.ONESHOT (ceiling 3) is the highest ceiling any existing Mode
    grants; an armed tier of 4 still lands one below what was armed — a
    real gap, not silently pretended away, since reaching a true tier-4
    ceiling for unattended dispatch needs dynamic ceiling-passing through
    the authority gate, a bigger change than this default-selection fix.
    Nothing armed (or expired) keeps the honest Mode.BUSY floor, unchanged
    — unattended-with-no-consent still gets the hard tier-1 stop."""
    from sovereign_agent.modes import Mode

    try:
        from sovereign_agent.auto_crown import get_auto_crown_store

        tier = get_auto_crown_store().get_max_trust_tier()  # reads first -- auto-reverts if expired
    except Exception:  # noqa: BLE001
        tier = None
    if tier is not None and tier >= 2:
        return Mode.ONESHOT
    return Mode.BUSY


def _request_store():
    from sovereign_agent.config import SETTINGS
    from sovereign_agent.persistence.store import ErebloStore
    from sovereign_agent.workflow.requests import RequestStore

    return RequestStore(ErebloStore(SETTINGS.paths.atoms_db))


def queue_operator_message(text: str) -> str:
    """Queue one operator message for delivery at her next safe boundary.
    Returns the request id."""
    from sovereign_agent.workflow.requests import DIRECTION_TO_ARIA

    text = (text or "").strip()
    req = _request_store().open(
        "note",
        text[:80] or "(empty)",
        body=text,
        tags=[QUEUE_TAG],
        rationale="operator message queued while a work session was running",
        direction=DIRECTION_TO_ARIA,
    )
    return req.request_id


def drain_operator_messages() -> list[str]:
    """Collect (and mark answered) every session-queued operator message.
    Called at each subtask start — a safe boundary by construction. Only
    drains messages carrying QUEUE_TAG: notes left via `sov requests tell`
    stay in the inbox for ReadInboxTool exactly as before. Never raises."""
    try:
        from sovereign_agent.workflow.requests import DIRECTION_TO_ARIA

        store = _request_store()
        out: list[str] = []
        for req in store.list_open(direction=DIRECTION_TO_ARIA):
            if QUEUE_TAG not in (req.tags or []):
                continue
            out.append(req.body or req.title)
            try:
                store.answer(req.request_id, "delivered to Aria at a safe subtask boundary")
            except Exception:  # noqa: BLE001 — delivery still counts
                pass
        return out
    except Exception:  # noqa: BLE001
        return []


def resumable_sessions(limit: int = 5) -> list:  # resume-spine-d
    """Sessions worth offering /resume for, newest first: paused, budget,
    error — and 'active' corpses (a crash/quit mid-run leaves status
    active with no worker; within the cockpit _session_running guards the
    genuinely-running one).

    resume-orphan-recovery-d (Kevin, 2026-08-01): also counts a session
    with an orphaned "in_progress" subtask (an abrupt exit mid-subtask,
    never cleanly finished) as resumable, not just "pending" ones — run_session
    resets in_progress -> pending on re-entry, so this subtask WILL run
    again on /resume. Before this, a session interrupted on its last
    actionable subtask had zero "pending" subtasks and silently vanished
    from the menu even though it was exactly the "active corpse" case this
    function's docstring already describes."""
    try:
        from sovereign_agent.agent_session import SessionStore

        out = [s for s in SessionStore().list_all()
               if s.status in ("paused", "budget", "error", "active")
               and any(st.status in ("pending", "in_progress") for st in s.subtasks)]
        return out[:limit]
    except Exception:  # noqa: BLE001
        return []


def resume_blocked_reason(session_id: str = "") -> str | None:  # resume-gating-clarity-d
    """resume-gating-clarity-d (Kevin, 2026-07-25): "It says they are
    resumable but when I click on it nothing happens... I selected the
    session I wanted... but it still did not resume." Root cause: two
    SEPARATE gates block a resume -- chat-mode's autonomous_loops_allowed()
    (checked by the cockpit before it even tries) and the crown profile's
    _crown_gate() (only ever checked deep inside resume_goal_session,
    after the cockpit had already said "resuming" — its PermissionError
    was only ever caught generically and shown as a terse "resume error:"
    line). This runs the SAME _crown_gate() check as a dry run, so both
    reasons are knowable up front, before committing to a resume attempt.
    None means nothing is blocking (crown-side; the caller still checks
    autonomous_loops_allowed() separately for the chat/work toggle)."""
    try:
        _crown_gate("resume", None, session_id=session_id)
        return None
    except PermissionError as exc:
        return str(exc)
    except Exception:  # noqa: BLE001 — crown not applied → nothing to gate
        return None


def forget_session(session_id: str) -> bool:  # resume-menu-forget-d
    """Permanently remove a session Kevin no longer wants offered in the
    Resume Menu. Thin wrapper over SessionStore.delete() -- exists so
    the cockpit (and anything else) has one call site, not a direct
    reach into SessionStore. Returns True iff something was actually
    removed."""
    from sovereign_agent.agent_session import SessionStore

    return SessionStore().delete(session_id)


async def resume_goal_session(  # resume-spine-d
    session_id: str,
    *,
    wall_seconds: int = 3600,
    safety_margin_seconds: int = 360,
    max_iterations: int = 200,
    max_tokens: int = 2_000_000,
):
    """Re-enter run_session on an EXISTING session — the resume half the
    engine always supported and nothing ever called. The scope contract
    reloads via load_scope; messages queued during the pause deliver at
    the first boundary — both for free, both by construction."""
    from sovereign_agent.agent_session import run_session
    from sovereign_agent.cli import _build_tools_for_mode
    from sovereign_agent.agent_session import SessionStore
    from sovereign_agent.modes import Mode, RunBudget

    _lease_check(f"resume {session_id}")  # thread-grooming-d
    _crown_gate("resume", None, session_id=session_id)  # modes-crown-d
    state = SessionStore().load(session_id)
    mode = Mode(state.mode)
    margin = min(safety_margin_seconds, max(60, wall_seconds // 10))
    if margin >= wall_seconds:
        margin = 0

    # graceful-pause-fix-d (Kevin, 2026-07-20): ANY resume must clear a
    # pending conversation-pause request first, or run_session's own Gate 2
    # sees the request flag still set on its very first iteration and
    # immediately re-pauses -- "I cannot resume any task unless I /pause
    # cancel first." Centralized here (not in the cockpit's call sites) so
    # every resume path is covered, present and future. Safe unconditionally:
    # a session never conversation-paused has no request flag to clear, and
    # consume_resume() at the top of run_session already tolerates a
    # resume-with-nothing-to-resume as a harmless no-op.
    from sovereign_agent import interrupts
    interrupts.request_resume()

    return await run_session(
        session_id=session_id,
        tools=_build_tools_for_mode(mode),
        budget=RunBudget(
            max_iterations=max_iterations,
            max_wall_seconds=wall_seconds,
            max_tokens=max_tokens,
            safety_margin_seconds=margin,
        ),
    )


async def start_goal_session(
    goal: str,
    *,
    mode=None,
    wall_seconds: int = 3600,
    min_minutes: int | None = None,
    safety_margin_seconds: int = 360,
    max_iterations: int = 200,
    max_tokens: int = 2_000_000,
):
    """new_session(goal) + run_session(...) — the call site that never
    existed. Returns the engine's own SessionResult.

    Budget shape composes Workstream N's safe-interval design: a 1h wall
    with a real margin, so the interval boundary lands between subtasks,
    never mid-tool-call. The FULL tool registry rides in (the same
    all-registered-tools build `sov agent` uses since the prompt-diet
    round); the authority gate + prompt diet decide per-iteration what the
    model actually sees.

    work-deadline-args-d (Kevin, 2026-07-25): "/work <goal> <min
    timeframe> <max deadline>" — `wall_seconds` was always the hard
    ceiling; `min_minutes`, when given, is what the modulator sizes its
    subtask decomposition toward (so the plan genuinely aims to fill at
    least that much substantive work), independent of the ceiling.
    Optional and additive: omitted, this is byte-identical to before.
    """
    from sovereign_agent.agent_session import Subtask, new_session, run_session
    from sovereign_agent.cli import _build_tools_for_mode
    from sovereign_agent.modes import Mode, RunBudget

    # scope-contract-d — `<goal> | scope: ...` declares a ScopeContract up front:
    # pre-registered honesty at the boundary of the work.
    from sovereign_agent.scope import parse_goal_with_scope, save_scope

    goal, _scope = parse_goal_with_scope(goal)
    _lease_check(goal)  # thread-grooming-d — record_action enforces the armed lease
    _crown_gate(goal, _scope)  # modes-crown-d — profile walls: work/garden/cool-down
    mode = mode or _resolve_default_mode()  # auto-crown-tier-unify-d

    # goal-modulator-d (Kevin, 2026-07-21): "add a helper or something to
    # turn ingestion into smaller task. A god tier goal to task
    # modulator." Then: "Every ingestion should be broken down into
    # timeframes and end goals, basically." Root cause this closes: "stay
    # busy for 2 hours" used to become ONE subtask that hit its own
    # per-subtask wall-clock ceiling in ~10 minutes -- nowhere near the
    # requested duration, and the stated "2 hours" was just text the
    # model read, never a real technical limit.
    #
    # EVERY goal now runs through the modulator -- not just ones that
    # heuristically look open-ended, per Kevin's "every ingestion"
    # direction. If the goal states its own duration, that becomes the
    # REAL session wall_seconds (only ever raised, never shrunk below
    # what the caller explicitly asked for). The modulator's own prompt
    # tells it not to invent busywork for an already-simple goal -- a
    # concrete one-step goal should come back as one subtask with its own
    # honest timeframe + done-criterion, not forced into many. Fully
    # additive: any failure here (unreachable fast model, malformed
    # output) falls straight back to the single-subtask shape that
    # already existed -- this can never block a session from starting.
    from uuid import uuid4

    from sovereign_agent import goal_modulator

    extracted_minutes = goal_modulator.extract_target_minutes(goal)
    if extracted_minutes is not None:
        wall_seconds = max(wall_seconds, extracted_minutes * 60)
    if min_minutes is not None:
        wall_seconds = max(wall_seconds, min_minutes * 60)  # min never exceeds the ceiling

    modulation_target = min_minutes if min_minutes is not None else wall_seconds // 60
    initial_subtasks = None
    try:
        specs = await goal_modulator.modulate_goal(
            goal, target_minutes=modulation_target)
    except Exception:  # noqa: BLE001 — modulation is a bonus, never a blocker
        specs = []
    if specs:
        initial_subtasks = [
            Subtask(id=f"st_{uuid4().hex[:12]}", description=desc, required_tier=tier)
            for desc, tier in specs
        ]

    state = new_session(goal=goal, mode=mode, initial_subtasks=initial_subtasks)
    if _scope is not None:
        try:
            save_scope(state.session_id, _scope)
        except Exception:  # noqa: BLE001 — scope is a discipline, never a crash
            pass
    # Clamp the margin to Workstream N's own design (10% of the wall,
    # 60s floor) — a margin larger than the wall would make the effective
    # limit 0 and trip the budget instantly (caught by the first live E2E
    # run of this bridge, not by inspection).
    margin = min(safety_margin_seconds, max(60, wall_seconds // 10))
    if margin >= wall_seconds:
        margin = 0
    budget = RunBudget(
        max_iterations=max_iterations,
        max_wall_seconds=wall_seconds,
        max_tokens=max_tokens,
        safety_margin_seconds=margin,
    )
    result = await run_session(
        session_id=state.session_id,
        tools=_build_tools_for_mode(mode),
        budget=budget,
    )
    # session-review-d — leave a reviewable record of what she did, so it can
    # be inspected later (by Kevin, Claude, any AI, or a human team). Composed
    # from the final SessionState + recent events. A review must NEVER break
    # the session result, so the whole thing is best-effort.
    try:
        _write_session_review(state.session_id)
    except Exception:  # noqa: BLE001
        pass
    return result


def _write_session_review(session_id: str) -> None:
    """Build the review directory for a just-finished session (best-effort)."""
    from sovereign_agent.agent_session import SessionStore
    from sovereign_agent.config import SETTINGS
    from sovereign_agent.review_journal import build_review

    final = SessionStore().load(session_id)
    events = _recent_events_for_review()
    build_review(final, data_dir=SETTINGS.paths.data_dir, events_records=events)
    # success-patterns-d — distill the outcome into her workflow-success
    # pattern store so future goals can match against real wins. Best-effort;
    # record_outcome never raises.
    try:
        from sovereign_agent.success_patterns import record_outcome
        record_outcome(final)
    except Exception:  # noqa: BLE001
        pass
    # work-updates-d (Kevin, 2026-07-18): "when aria works in auto mode,
    # can she send me work updates via discord?" — every finished work
    # session posts a short update to #aria-control (the owner's ops
    # channel). Env-resolved webhook: unset → auto dry-run, never an
    # error. Best-effort like everything on the close-out path.
    try:
        _post_work_update(final)
    except Exception:  # noqa: BLE001
        pass


def _post_work_update(final) -> None:
    from sovereign_agent.discord_runtime.delivery import WebhookDelivery
    goal = str(getattr(final, "goal", "") or "").strip()
    if not goal:
        return
    status = str(getattr(final, "status", "") or "unknown")
    subtasks = list(getattr(final, "subtasks", []) or [])
    done = sum(1 for s in subtasks
               if str(getattr(s, "status", "")) in ("done", "skipped"))
    icon = {"completed": "✅", "done": "✅", "paused": "⏸",
            "halted": "🛑", "error": "⚠"}.get(status, "🛠")
    sid = str(getattr(final, "session_id", "") or "")[:12]
    # F5: close-outs prefer the owner's private bridge when it's minted
    import os
    env = ("DISCORD_OWNER_WEBHOOK_URL"
           if (os.environ.get("DISCORD_OWNER_WEBHOOK_URL") or "").strip()
           else "DISCORD_WEBHOOK_URL")
    WebhookDelivery(env, live=True).send(
        f"{icon} **Work update** — \"{goal[:180]}\"\n"
        f"finished **{status}** · {done}/{len(subtasks)} steps done · "
        f"full trail: `sov reviews show {sid}`",
        username="Aria — on duty")


def _recent_events_for_review(window: int = 200) -> list[dict]:
    """Recent events for the review's action trace (best-effort; never raises).
    Mirrors emotion._load_recent_events's proven read pattern."""
    import json as _json
    try:
        from sovereign_agent.config import SETTINGS
        events_dir = SETTINGS.paths.events_dir
        if not events_dir.exists():
            return []
        out: list[dict] = []
        for f in sorted(events_dir.glob("events-*.jsonl"))[-2:]:
            try:
                for line in f.read_text(encoding="utf-8").splitlines():
                    if line.strip():
                        out.append(_json.loads(line))
            except Exception:  # noqa: BLE001
                pass
        return out[-window:]
    except Exception:  # noqa: BLE001
        return []


# ─── lease wiring (FABLE II M5 · thread-grooming-d) ─────────────────────────────────
# record_action — the blast-radius enforcer — finally lives in /work: when
# an auto-mode lease is armed, every goal the bridge dispatches is bound-
# checked and recorded on the lease's OBSERVABLE action log; an expired
# lease REFUSES new goals (re-approval, full stop — leases never
# self-extend). No lease armed = today's behavior, unchanged.

_ACTIVE_LEASE = None


def arm_lease(lease) -> None:
    """Arm an AutonomySession lease for the bridge (auto modes call this
    after explicit operator approval)."""
    global _ACTIVE_LEASE
    _ACTIVE_LEASE = lease


def disarm_lease() -> None:
    global _ACTIVE_LEASE
    _ACTIVE_LEASE = None


def active_lease():
    return _ACTIVE_LEASE


def _lease_check(detail: str) -> None:
    """The record_action wire. Outside a lease: no-op. Inside: the dispatch
    is recorded (observable) and an expired/over-radius lease refuses."""
    lease = _ACTIVE_LEASE
    if lease is None:
        return
    from sovereign_agent.autonomy.session import record_action, save

    entry = record_action(lease, "run_goal_session", detail=detail[:200])
    try:
        from sovereign_agent.config import SETTINGS

        save(lease, SETTINGS.paths.data_dir)   # the log is durable, watchable
    except Exception:  # noqa: BLE001 — observability must not block work
        pass
    if not entry.get("allowed"):
        raise PermissionError(
            f"lease refuses the goal dispatch: {entry.get('reason', 'unknown')}")


def _crown_gate(goal: str, scope=None, *, session_id: str = "") -> None:
    """modes-crown-d — the profile walls, enforced at the front door:
    non-work modes refuse sessions; focus requires a garden; cool-down
    pauses NEW dispatches (running work is never interrupted). A NO-OP
    until the operator explicitly arms a crown mode (F2 / /modes) —
    today's behavior (an explicit /work dispatch always ran regardless of
    the passive chat/work toggle) stays byte-identical until then."""
    try:
        from sovereign_agent.modes_crown.profiles import (
            crown_armed, current_profile,
        )
        from sovereign_agent.modes_crown.stances import cooling_down
    except Exception:  # noqa: BLE001 — crown not applied → nothing to gate
        return
    if not crown_armed():
        return
    profile = current_profile()
    if not profile.work_allowed:
        raise PermissionError(
            f"mode {profile.mode_id!r} does not run work sessions — "
            f"switch modes (F2 / /modes) to work her")
    if profile.garden_required:
        if scope is None and session_id:
            try:
                from sovereign_agent.scope import load_scope

                scope = load_scope(session_id)
            except Exception:  # noqa: BLE001
                scope = None
        if scope is None or not getattr(scope, "garden_dir", ""):
            raise PermissionError(
                "focus mode requires a garden — declare one: "
                "/work <goal> | scope: dir: <path>")
    if cooling_down():
        raise PermissionError(
            "she is cooling down — no new goals until the stance clears "
            "(set_stance to any working stance, or '')")
    try:  # quality-modes-d — the second stance with a real tooth
        from sovereign_agent.modes_crown.stances import (
            current_stance, quality_gate_clear,
        )

        if current_stance() == "quality-pass" and not quality_gate_clear():
            raise PermissionError(
                "a quality pass is running/failed — no new goals until it "
                "clears (set_stance to any working stance, or wait for the "
                "pass to pass)")
    except ImportError:  # noqa: BLE001 — quality not applied → nothing to gate
        pass
    try:  # grounding-modes-d — the third stance with a real tooth
        from sovereign_agent.modes_crown.stances import (
            current_stance as _current_stance_g, grounding_gate_clear,
        )

        if _current_stance_g() == "grounded" and not grounding_gate_clear():
            raise PermissionError(
                "a grounding pass is running/failed — no new goals until it "
                "clears (set_stance to any working stance, or wait for the "
                "pass to pass)")
    except ImportError:  # noqa: BLE001 — grounding not applied → nothing to gate
        pass
    try:  # wellbeing-modes-d — the fourth stance with a real tooth
        from sovereign_agent.modes_crown.stances import (
            current_stance as _current_stance_w, wellbeing_gate_clear,
        )

        if _current_stance_w() == "reflecting" and not wellbeing_gate_clear():
            raise PermissionError(
                "a wellbeing pass is running/failed — no new goals until it "
                "clears (set_stance to any working stance, or wait for the "
                "pass to pass)")
    except ImportError:  # noqa: BLE001 — wellbeing not applied → nothing to gate
        pass
    try:  # integrity-modes-d — the fifth stance with a real tooth
        from sovereign_agent.modes_crown.stances import (
            current_stance as _current_stance_i, integrity_gate_clear,
        )

        if _current_stance_i() == "honest" and not integrity_gate_clear():
            raise PermissionError(
                "an integrity pass is running/failed — no new goals until it "
                "clears (set_stance to any working stance, or wait for the "
                "pass to pass)")
    except ImportError:  # noqa: BLE001 — integrity not applied → nothing to gate
        pass
