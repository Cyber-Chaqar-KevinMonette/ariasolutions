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


async def start_goal_session(
    goal: str,
    *,
    mode=None,
    wall_seconds: int = 3600,
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
    """
    from sovereign_agent.agent_session import new_session, run_session
    from sovereign_agent.cli import _build_tools_for_mode
    from sovereign_agent.modes import Mode, RunBudget

    mode = mode or Mode.BUSY
    state = new_session(goal=goal, mode=mode)
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
    return await run_session(
        session_id=state.session_id,
        tools=_build_tools_for_mode(mode),
        budget=budget,
    )
