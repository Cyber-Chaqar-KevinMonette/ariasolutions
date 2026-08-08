"""aria-graduated-trust — hold-and-continue at Gate 4. (FABLE II · M7)

Pre-apply, everything that depends on the agent_session.py patch skips
with a written reason; the apply script re-runs this file and requires
zero skips.
"""
from __future__ import annotations

import inspect


def _patched(obj) -> bool:
    return "graduated-trust-d" in inspect.getsource(obj)


def _agent_session_patched() -> bool:
    import sovereign_agent.agent_session as m

    return _patched(m)


# ─── the core claim: five T1s complete, one T2 holds ─────────────────────


async def _run_hold_and_continue():
    from unittest.mock import AsyncMock, patch as _patch

    from sovereign_agent.agent_session import (
        Subtask, SessionStore, new_session, run_session,
    )
    from sovereign_agent.loop import LoopResult
    from sovereign_agent.modes import Mode, RunBudget

    # Mode.BUSY's ceiling (1) would hard-reject a tier-2 subtask outright;
    # Mode.ONESHOT's ceiling (3) lets it clear the ceiling check and land
    # on the "requires_operator" branch — the Gate-4 path this tests.
    subtasks = [Subtask(id=f"st-{i}", description=f"t1 {i}", required_tier=1)
               for i in range(5)]
    subtasks.insert(2, Subtask(id="st-t2", description="over-tier",
                               required_tier=2))
    state = new_session(goal="g", mode=Mode.ONESHOT, initial_subtasks=subtasks)

    async def _fake(**kw):
        return LoopResult(ok=True, reason="complete", iterations=1,
                          tokens_used=1, final_message="RESULT: ok")

    with _patch("sovereign_agent.agent_session.agent_loop",
               new=AsyncMock(side_effect=_fake)):
        await run_session(session_id=state.session_id, tools={},
                          budget=RunBudget(max_iterations=20,
                                           max_wall_seconds=60,
                                           max_tokens=100_000),
                          horizon_required=False)
    return SessionStore().load(state.session_id)


def test_five_t1s_complete_the_one_t2_holds():
    import asyncio

    import pytest

    if not _agent_session_patched():
        pytest.skip("pre-apply: Gate 4 hold-and-continue not yet applied")
    final = asyncio.run(_run_hold_and_continue())
    done = [s for s in final.subtasks if s.status == "done"]
    held = [s for s in final.subtasks if s.status == "awaiting_approval"]
    assert len(done) == 5
    assert [s.id for s in held] == ["st-t2"]
    assert final.status == "paused"
    assert final.pause_reason == "awaiting_approval:st-t2"


def test_held_subtask_carries_the_refusal_reason():
    import asyncio

    import pytest

    if not _agent_session_patched():
        pytest.skip("pre-apply: Gate 4 hold-and-continue not yet applied")
    final = asyncio.run(_run_hold_and_continue())
    held = next(s for s in final.subtasks if s.id == "st-t2")
    assert "tier" in held.error.lower() or "operator" in held.error.lower()


def test_legacy_full_stop_still_available_when_opted_out():
    """hold_and_continue=False must reproduce the OLD behavior exactly:
    the whole session pauses at the first over-tier subtask."""
    import asyncio
    from unittest.mock import AsyncMock, patch as _patch

    import pytest

    if not _agent_session_patched():
        pytest.skip("pre-apply: Gate 4 hold-and-continue not yet applied")
    from sovereign_agent.agent_session import (
        Subtask, SessionStore, new_session, run_session,
    )
    from sovereign_agent.loop import LoopResult
    from sovereign_agent.modes import Mode, RunBudget

    subtasks = [Subtask(id="st-0", description="t1", required_tier=1),
               Subtask(id="st-t2", description="over-tier", required_tier=2),
               Subtask(id="st-2", description="t1 after", required_tier=1)]
    state = new_session(goal="g", mode=Mode.ONESHOT, initial_subtasks=subtasks)
    state.hold_and_continue = False
    SessionStore().save(state)

    async def _fake(**kw):
        return LoopResult(ok=True, reason="complete", iterations=1,
                          tokens_used=1, final_message="RESULT: ok")

    async def _go():
        with _patch("sovereign_agent.agent_session.agent_loop",
                   new=AsyncMock(side_effect=_fake)):
            await run_session(session_id=state.session_id, tools={},
                              budget=RunBudget(max_iterations=20,
                                               max_wall_seconds=60,
                                               max_tokens=100_000),
                              horizon_required=False)
        return SessionStore().load(state.session_id)

    final = asyncio.run(_go())
    assert final.status == "paused"
    assert final.pause_reason == "awaiting_approval:st-t2"
    assert final.subtasks[2].status == "pending"   # st-2 never ran


def test_multiple_held_subtasks_batch_into_one_pause():
    import asyncio
    from unittest.mock import AsyncMock, patch as _patch

    import pytest

    if not _agent_session_patched():
        pytest.skip("pre-apply: Gate 4 hold-and-continue not yet applied")
    from sovereign_agent.agent_session import (
        Subtask, SessionStore, new_session, run_session,
    )
    from sovereign_agent.loop import LoopResult
    from sovereign_agent.modes import Mode, RunBudget

    subtasks = [Subtask(id="a", description="t1", required_tier=1),
               Subtask(id="b", description="t2-one", required_tier=2),
               Subtask(id="c", description="t1", required_tier=1),
               Subtask(id="d", description="t2-two", required_tier=2)]
    state = new_session(goal="g", mode=Mode.ONESHOT, initial_subtasks=subtasks)

    async def _fake(**kw):
        return LoopResult(ok=True, reason="complete", iterations=1,
                          tokens_used=1, final_message="RESULT: ok")

    async def _go():
        with _patch("sovereign_agent.agent_session.agent_loop",
                   new=AsyncMock(side_effect=_fake)):
            await run_session(session_id=state.session_id, tools={},
                              budget=RunBudget(max_iterations=20,
                                               max_wall_seconds=60,
                                               max_tokens=100_000),
                              horizon_required=False)
        return SessionStore().load(state.session_id)

    final = asyncio.run(_go())
    assert final.status == "paused"
    assert set(final.pause_reason.split(":", 1)[1].split(",")) == {"b", "d"}
    assert final.held_subtask_ids() == ["b", "d"]


# ─── approve / approve_all_held ──────────────────────────────────────────


def test_approve_subtask_accepts_awaiting_approval():
    import pytest

    if not _agent_session_patched():
        pytest.skip("pre-apply: Gate 4 hold-and-continue not yet applied")
    from sovereign_agent.agent_session import (
        Subtask, SessionStore, approve_subtask, new_session,
    )
    from sovereign_agent.modes import Mode

    state = new_session(goal="g", mode=Mode.BUSY,
                        initial_subtasks=[Subtask(id="x", description="d",
                                                  required_tier=2)])
    state.subtasks[0].status = "awaiting_approval"
    SessionStore().save(state)
    approved = approve_subtask(state.session_id, "x")
    assert approved.subtasks[0].status == "pending"
    assert approved.subtasks[0].required_tier == 1


def test_approve_all_held_approves_every_one():
    import pytest

    if not _agent_session_patched():
        pytest.skip("pre-apply: Gate 4 hold-and-continue not yet applied")
    from sovereign_agent.agent_session import (
        Subtask, SessionStore, approve_all_held, new_session,
    )
    from sovereign_agent.modes import Mode

    subtasks = [Subtask(id="a", description="d", required_tier=2),
               Subtask(id="b", description="d", required_tier=2)]
    state = new_session(goal="g", mode=Mode.BUSY, initial_subtasks=subtasks)
    for s in state.subtasks:
        s.status = "awaiting_approval"
    SessionStore().save(state)
    final = approve_all_held(state.session_id)
    assert all(s.status == "pending" for s in final.subtasks)


# ─── revise_pending_subtasks — mid-work plan updates, resiliently ────────


def test_revise_removes_a_pending_subtask_never_the_running_one():
    import pytest

    if not _agent_session_patched():
        pytest.skip("pre-apply: revise_pending_subtasks not yet applied")
    from sovereign_agent.agent_session import (
        Subtask, new_session, revise_pending_subtasks,
    )
    from sovereign_agent.modes import Mode

    subtasks = [Subtask(id="running", description="d", required_tier=1,
                        status="in_progress"),
               Subtask(id="drop-me", description="d", required_tier=1),
               Subtask(id="keep-me", description="d", required_tier=1)]
    state = new_session(goal="g", mode=Mode.BUSY, initial_subtasks=subtasks)
    record = revise_pending_subtasks(
        state, remove_ids=["drop-me"], justification="no longer needed")
    by_id = {s.id: s for s in state.subtasks}
    assert by_id["drop-me"].status == "skipped"
    assert by_id["keep-me"].status == "pending"
    assert by_id["running"].status == "in_progress"   # untouched
    assert record.subtask_ids == ["drop-me"]
    assert state.plan_revisions == [record]


def test_revise_refuses_to_touch_a_non_pending_subtask():
    import pytest

    if not _agent_session_patched():
        pytest.skip("pre-apply: revise_pending_subtasks not yet applied")
    from sovereign_agent.agent_session import Subtask, new_session, revise_pending_subtasks
    from sovereign_agent.modes import Mode

    subtasks = [Subtask(id="running", description="d", required_tier=1,
                        status="in_progress")]
    state = new_session(goal="g", mode=Mode.BUSY, initial_subtasks=subtasks)
    with pytest.raises(ValueError, match="not currently pending"):
        revise_pending_subtasks(state, remove_ids=["running"],
                                justification="try to touch the running one")


def test_revise_requires_a_justification():
    import pytest

    if not _agent_session_patched():
        pytest.skip("pre-apply: revise_pending_subtasks not yet applied")
    from sovereign_agent.agent_session import Subtask, new_session, revise_pending_subtasks
    from sovereign_agent.modes import Mode

    state = new_session(goal="g", mode=Mode.BUSY,
                        initial_subtasks=[Subtask(id="a", description="d")])
    with pytest.raises(ValueError, match="justification"):
        revise_pending_subtasks(state, remove_ids=["a"], justification="")


def test_revise_reorders_pending_subtasks():
    import pytest

    if not _agent_session_patched():
        pytest.skip("pre-apply: revise_pending_subtasks not yet applied")
    from sovereign_agent.agent_session import Subtask, new_session, revise_pending_subtasks
    from sovereign_agent.modes import Mode

    subtasks = [Subtask(id="running", description="d", status="in_progress"),
               Subtask(id="a", description="d"), Subtask(id="b", description="d"),
               Subtask(id="c", description="d")]
    state = new_session(goal="g", mode=Mode.BUSY, initial_subtasks=subtasks)
    revise_pending_subtasks(state, reorder=["c", "a", "b"],
                            justification="c is more urgent now")
    ids = [s.id for s in state.subtasks]
    assert ids == ["running", "c", "a", "b"]


def test_revise_edits_a_pending_description():
    import pytest

    if not _agent_session_patched():
        pytest.skip("pre-apply: revise_pending_subtasks not yet applied")
    from sovereign_agent.agent_session import Subtask, new_session, revise_pending_subtasks
    from sovereign_agent.modes import Mode

    state = new_session(goal="g", mode=Mode.BUSY,
                        initial_subtasks=[Subtask(id="a", description="old")])
    revise_pending_subtasks(state, edits={"a": "new, sharper description"},
                            justification="clarified scope")
    assert state.subtasks[0].description == "new, sharper description"


# ─── the doctrine, same words, one place each ────────────────────────────

DOCTRINE_WORDS = "propose at boundaries; move freely inside grants"


def test_doctrine_words_in_loop_prompt():
    import inspect
    import pytest

    from sovereign_agent import loop as loop_mod

    if not _patched(loop_mod):
        pytest.skip("pre-apply: loop.py autonomy section not yet patched")
    assert DOCTRINE_WORDS in inspect.getsource(loop_mod)


def test_doctrine_words_in_safety_model_and_claude_md():
    import pathlib

    import sovereign_agent

    # sovereign_agent/__init__.py lives at <repo_root>/src/sovereign_agent/
    # — stable whether this test runs staged (aria-graduated-trust/tests/)
    # or promoted (tests/), unlike a __file__-relative parents[] count.
    repo_root = pathlib.Path(sovereign_agent.__file__).parents[2]
    safety = repo_root / "handoff" / "02_SAFETY_MODEL.md"
    claude = repo_root / "CLAUDE.md"
    if DOCTRINE_WORDS not in safety.read_text(encoding="utf-8"):
        import pytest

        pytest.skip("pre-apply: 02_SAFETY_MODEL.md not yet patched")
    assert DOCTRINE_WORDS in claude.read_text(encoding="utf-8")


# ─── the proving-ground task ──────────────────────────────────────────────


def test_proving_ground_trust_task_scores_pass():
    import asyncio
    import inspect
    import pytest

    from sovereign_agent.proving_ground import runner as runner_mod

    if "graduated-trust-d" not in inspect.getsource(runner_mod):
        pytest.skip("pre-apply: proving_ground/runner.py not yet patched")
    # SUITE_VERSION itself is not this test's concern — it keeps bumping as
    # later wings (e.g. Quality round Q5) get added; pinning an exact string
    # here made this test break on every unrelated version bump. What this
    # test actually proves is that the graduated-trust task still passes.
    fn = runner_mod.OFFLINE_TASKS["graduated-trust-hold"]
    ok, note = asyncio.run(fn())
    assert ok, note


# ─── the CLI + cockpit surfaces (structural — behavior covered above) ────


def test_cli_session_app_registered():
    import inspect
    import pytest

    from sovereign_agent import cli as cli_mod

    if not _patched(cli_mod):
        pytest.skip("pre-apply: cli.py session sub-app not yet patched")
    assert hasattr(cli_mod, "session_app")


def test_cockpit_approve_slash_verb_registered():
    import inspect
    import pytest

    from sovereign_agent.cockpit import app as app_mod

    if not _patched(app_mod):
        pytest.skip("pre-apply: cockpit/app.py /approve verb not yet patched")
    assert hasattr(app_mod.CockpitApp, "_approve_held_subtask")
