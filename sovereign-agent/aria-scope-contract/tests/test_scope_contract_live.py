"""Behavior tests for aria-scope-contract, promoted to live tests/ — the
REAL, already-patched modules. Plain imports, no shadow copy.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


# ── the contract itself ───────────────────────────────────────────────────


def test_parse_goal_with_scope_full_grammar():
    from sovereign_agent.scope import parse_goal_with_scope

    goal, sc = parse_goal_with_scope(
        "fix the parser | scope: only src/parser, error messages; "
        "out: tests, docs, ci; done: parse errors gone; max: 8"
    )
    assert goal == "fix the parser"
    assert sc.in_scope == ["only src/parser", "error messages"]
    assert sc.out_of_scope == ["tests", "docs", "ci"]
    assert sc.done_when == "parse errors gone"
    assert sc.max_subtasks == 8


def test_parse_goal_without_scope_is_backward_compatible():
    from sovereign_agent.scope import parse_goal_with_scope

    goal, sc = parse_goal_with_scope("just do the thing")
    assert goal == "just do the thing"
    assert sc is None


def test_is_out_of_scope_keyword_heuristic():
    from sovereign_agent.scope import ScopeContract

    sc = ScopeContract(goal="g", out_of_scope=["docs", "the CI pipeline"])
    assert sc.is_out_of_scope("update the docs for the parser")
    assert sc.is_out_of_scope("tweak THE CI PIPELINE config")
    assert not sc.is_out_of_scope("refactor the tokenizer")


def test_scope_round_trips_beside_the_session(tmp_path):
    from sovereign_agent.scope import ScopeContract, load_scope, save_scope

    sc = ScopeContract(goal="g", in_scope=["a"], out_of_scope=["b"],
                       done_when="done", max_subtasks=5)
    save_scope("sess_test123", sc, tmp_path)
    back = load_scope("sess_test123", tmp_path)
    assert back is not None
    assert back.as_dict() == sc.as_dict()
    assert load_scope("sess_never_saved", tmp_path) is None


# ── the engine with teeth ─────────────────────────────────────────────────


def _loop_result(final_message):
    from sovereign_agent.loop import LoopResult

    return LoopResult(ok=True, reason="complete", iterations=1,
                      tokens_used=10, final_message=final_message)


@pytest.mark.asyncio
async def test_out_of_scope_proposal_held_in_scope_one_appended():
    """THE teeth: a NEXT_SUBTASK inside scope joins the queue; one tripping
    the out list is held blocked for review — never silently appended."""
    from sovereign_agent.agent_session import SessionStore, new_session, run_session
    from sovereign_agent.cli import _build_tools_for_mode
    from sovereign_agent.modes import Mode, RunBudget
    from sovereign_agent.scope import ScopeContract, save_scope

    state = new_session(goal="fix the parser", mode=Mode.BUSY)
    save_scope(state.session_id,
               ScopeContract(goal="fix the parser", out_of_scope=["documentation"]))

    calls = {"n": 0}

    async def _fake(**kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return _loop_result(
                "RESULT: analyzed\n"
                "NEXT_SUBTASK[tier=1]: refactor the tokenizer edge cases\n"
                "NEXT_SUBTASK[tier=1]: rewrite the documentation site\n"
            )
        return _loop_result("RESULT: done")

    with patch("sovereign_agent.agent_session.agent_loop",
               new=AsyncMock(side_effect=_fake)):
        await run_session(
            session_id=state.session_id,
            tools=_build_tools_for_mode(Mode.BUSY),
            budget=RunBudget(max_iterations=20, max_wall_seconds=120,
                             max_tokens=100_000),
            horizon_required=False,
        )

    final = SessionStore().load(state.session_id)
    by_desc = {s.description: s for s in final.subtasks}
    assert by_desc["refactor the tokenizer edge cases"].status == "done"
    held = by_desc["rewrite the documentation site"]
    assert held.status == "blocked"
    assert "scope-review" in (held.error or "")


@pytest.mark.asyncio
async def test_guidance_carries_the_contract():
    from sovereign_agent.agent_session import new_session, run_session
    from sovereign_agent.cli import _build_tools_for_mode
    from sovereign_agent.modes import Mode, RunBudget
    from sovereign_agent.scope import ScopeContract, save_scope

    state = new_session(goal="g", mode=Mode.BUSY)
    save_scope(state.session_id,
               ScopeContract(goal="g", out_of_scope=["the moon"],
                             done_when="the tests pass"))
    seen = []

    async def _fake(**kwargs):
        seen.append(kwargs["goal"])
        return _loop_result("RESULT: ok")

    with patch("sovereign_agent.agent_session.agent_loop",
               new=AsyncMock(side_effect=_fake)):
        await run_session(
            session_id=state.session_id,
            tools=_build_tools_for_mode(Mode.BUSY),
            budget=RunBudget(max_iterations=10, max_wall_seconds=60,
                             max_tokens=50_000),
            horizon_required=False,
        )
    assert seen
    assert "SCOPE CONTRACT" in seen[0]
    assert "the moon" in seen[0]
    assert "the tests pass" in seen[0]


@pytest.mark.asyncio
async def test_no_contract_means_exactly_todays_behavior():
    from sovereign_agent.agent_session import new_session, run_session
    from sovereign_agent.cli import _build_tools_for_mode
    from sovereign_agent.modes import Mode, RunBudget

    state = new_session(goal="g", mode=Mode.BUSY)
    seen = []

    async def _fake(**kwargs):
        seen.append(kwargs["goal"])
        return _loop_result("RESULT: ok")

    with patch("sovereign_agent.agent_session.agent_loop",
               new=AsyncMock(side_effect=_fake)):
        result = await run_session(
            session_id=state.session_id,
            tools=_build_tools_for_mode(Mode.BUSY),
            budget=RunBudget(max_iterations=10, max_wall_seconds=60,
                             max_tokens=50_000),
            horizon_required=False,
        )
    assert result.status == "complete"
    assert "SCOPE CONTRACT" not in seen[0]


@pytest.mark.asyncio
async def test_bridge_parses_and_persists_the_scope():
    import sovereign_agent.session_bridge as sb
    from sovereign_agent.scope import load_scope

    captured = {}

    async def _capture(**kwargs):
        captured["session_id"] = kwargs["session_id"]
        from sovereign_agent.agent_session import SessionResult

        return SessionResult(session_id=kwargs["session_id"], status="complete",
                             completed_subtasks=1, total_subtasks=1,
                             total_iterations=1, total_tokens=1,
                             elapsed_seconds=0.1)

    with patch("sovereign_agent.agent_session.run_session",
               new=AsyncMock(side_effect=_capture)):
        await sb.start_goal_session(
            "tidy the garden | scope: out: the greenhouse; max: 4"
        )
    sc = load_scope(captured["session_id"])
    assert sc is not None
    assert sc.out_of_scope == ["the greenhouse"]
    assert sc.max_subtasks == 4


def test_scope_events_render_richly():
    from sovereign_agent.cockpit.run_surface import render_rich_event

    held = render_rich_event({"flag": "scope-review-d",
                              "payload": {"description": "rewrite the docs"}})
    assert held is not None and "scope review" in held
    drift = render_rich_event({"flag": "scope-drift-d",
                               "payload": {"subtasks": 10, "max": 12}})
    assert drift is not None and "10" in drift and "12" in drift


def test_observation_and_security_scoping():
    """Kevin (mid-round): scope her OBSERVATION and SECURITY too — the
    same grammar carries watch: and security: parts, both persisted and
    both in her self-policing prompt."""
    from sovereign_agent.scope import load_scope, parse_goal_with_scope, save_scope

    goal, sc = parse_goal_with_scope(
        "harden the parser | scope: only src/parser; out: docs; "
        "watch: test pass rate, memory usage; "
        "security: no network, read-only outside the sandbox; max: 6"
    )
    assert sc.observe == ["test pass rate", "memory usage"]
    assert sc.security == ["no network", "read-only outside the sandbox"]

    prompt = sc.format_for_prompt()
    assert "WATCH while working" in prompt
    assert "test pass rate" in prompt
    assert "SECURITY bounds" in prompt
    assert "no network" in prompt
    # honesty: the prompt names these as self-policing BEYOND the gates
    assert "always-on gates" in prompt

    save_scope("sess_obs_sec", sc)
    back = load_scope("sess_obs_sec")
    assert back.observe == sc.observe
    assert back.security == sc.security


def test_old_scope_files_without_new_fields_still_load():
    """Persistence compatibility: contracts saved before observe/security
    existed load with empty lists."""
    import json

    from sovereign_agent.config import SETTINGS
    from sovereign_agent.scope import load_scope

    path = SETTINGS.paths.data_dir / "sessions" / "sess_oldstyle.scope.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "goal": "g", "in_scope": [], "out_of_scope": ["x"],
        "done_when": "", "max_subtasks": 12,
    }))
    sc = load_scope("sess_oldstyle")
    assert sc is not None
    assert sc.observe == [] and sc.security == []
