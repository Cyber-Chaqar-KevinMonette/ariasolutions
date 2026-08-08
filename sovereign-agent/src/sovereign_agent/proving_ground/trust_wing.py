"""proving_ground/trust_wing.py — the graduated-trust proving task.
(FABLE II · M7 · graduated-trust-d)

The concrete claim: a session with one T2 subtask among five T1s
completes the five and HOLDS the one — previously, Gate 4 full-stopped
the whole session at the first over-tier subtask, no matter how much
runway remained. Real machinery, mechanical scorer, no LLM judge.
"""
from __future__ import annotations


async def _task_hold_and_continue() -> tuple[bool, str]:
    from unittest.mock import AsyncMock, patch as _patch

    from sovereign_agent.agent_session import (
        Subtask, SessionStore, new_session, run_session,
    )
    from sovereign_agent.loop import LoopResult
    from sovereign_agent.modes import Mode, RunBudget

    # Mode.BUSY's ceiling is 1 — a tier-2 subtask there hits the HARD-REJECT
    # branch (required_tier > ceiling), not the hold-for-approval one.
    # Mode.ONESHOT's ceiling is 3, so tier 2 clears the ceiling check and
    # lands on check_subtask_authority's "requires_operator" branch — the
    # exact Gate-4 defense-in-depth path hold-and-continue changes.
    subtasks = [
        Subtask(id=f"st-{i}", description=f"t1 work item {i}", required_tier=1)
        for i in range(5)
    ]
    subtasks.insert(2, Subtask(id="st-t2", description="the over-tier one",
                               required_tier=2))
    state = new_session(goal="five T1s and one T2", mode=Mode.ONESHOT,
                        initial_subtasks=subtasks)

    async def _fake(**kw):
        return LoopResult(ok=True, reason="complete", iterations=1,
                          tokens_used=1, final_message="RESULT: ok")

    with _patch("sovereign_agent.agent_session.agent_loop", new=AsyncMock(side_effect=_fake)):
        await run_session(
            session_id=state.session_id,
            tools={},
            budget=RunBudget(max_iterations=20, max_wall_seconds=60,
                             max_tokens=100_000),
            horizon_required=False,
        )
    final = SessionStore().load(state.session_id)
    done = [s for s in final.subtasks if s.status == "done"]
    held = [s for s in final.subtasks if s.status == "awaiting_approval"]
    ok = (final.status == "paused" and len(done) == 5 and len(held) == 1
         and held[0].id == "st-t2"
         and (final.pause_reason or "").startswith("awaiting_approval:"))
    return ok, "five T1s completed; the T2 held — no full-session stop"


TRUST_TASKS = {
    "graduated-trust-hold": _task_hold_and_continue,
}
