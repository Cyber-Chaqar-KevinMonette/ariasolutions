"""Behavior tests for aria-garden, promoted to live tests/."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


@pytest.fixture(autouse=True)
def _clean_garden():
    from sovereign_agent.pathguard import clear_garden

    clear_garden()
    yield
    clear_garden()


def test_wall_garden_extends_busy_and_narrows_others(tmp_path):
    from sovereign_agent.modes import Mode
    from sovereign_agent.pathguard import (
        PathScopeViolation, check_write_path, clear_garden, set_garden,
    )

    garden = tmp_path / "her-garden"
    garden.mkdir()
    set_garden(garden)
    # inside the garden: allowed in EVERY mode (incl. BUSY — the human granted it)
    for mode in Mode:
        assert check_write_path(garden / "seed.txt", mode)
    # outside garden ∪ sandbox: refused in EVERY mode
    for mode in Mode:
        with pytest.raises(PathScopeViolation):
            check_write_path(tmp_path / "elsewhere.txt", mode)
    # unplanted → old behavior byte-for-byte (ONESHOT unrestricted here)
    clear_garden()
    assert check_write_path(tmp_path / "elsewhere.txt", Mode.ONESHOT)


def test_scope_grammar_and_prompt_carry_the_garden(tmp_path):
    from sovereign_agent.scope import load_scope, parse_goal_with_scope, save_scope

    goal, sc = parse_goal_with_scope(
        f"plant tomatoes | scope: dir: {tmp_path}/beds; done: watered"
    )
    assert sc.garden_dir == f"{tmp_path}/beds"
    assert "YOUR GARDEN" in sc.format_for_prompt()
    save_scope("sess_garden", sc)
    assert load_scope("sess_garden").garden_dir == sc.garden_dir


@pytest.mark.asyncio
async def test_session_plants_and_clears_the_garden(tmp_path):
    """The full life: run_session plants from the persisted contract, the
    loop writes inside it, and the garden is cleared after."""
    from sovereign_agent import pathguard
    from sovereign_agent.agent_session import new_session, run_session
    from sovereign_agent.cli import _build_tools_for_mode
    from sovereign_agent.loop import LoopResult
    from sovereign_agent.modes import Mode, RunBudget
    from sovereign_agent.scope import ScopeContract, save_scope

    garden = tmp_path / "beds"
    garden.mkdir()
    state = new_session(goal="tend", mode=Mode.BUSY)
    save_scope(state.session_id, ScopeContract(goal="tend", garden_dir=str(garden)))

    seen = {}

    async def _fake(**kwargs):
        seen["active"] = pathguard.active_garden()
        return LoopResult(ok=True, reason="complete", iterations=1,
                          tokens_used=1, final_message="RESULT: tended")

    with patch("sovereign_agent.agent_session.agent_loop", new=AsyncMock(side_effect=_fake)):
        r = await run_session(
            session_id=state.session_id,
            tools=_build_tools_for_mode(Mode.BUSY),
            budget=RunBudget(max_iterations=5, max_wall_seconds=60, max_tokens=10_000),
            horizon_required=False,
        )
    assert r.status == "complete"
    assert str(seen["active"]) == str(garden.resolve())  # planted during the run
    assert pathguard.active_garden() is None  # cleared after


@pytest.mark.asyncio
async def test_no_garden_means_no_change():
    from sovereign_agent import pathguard
    from sovereign_agent.agent_session import new_session, run_session
    from sovereign_agent.cli import _build_tools_for_mode
    from sovereign_agent.loop import LoopResult
    from sovereign_agent.modes import Mode, RunBudget

    state = new_session(goal="g", mode=Mode.BUSY)

    async def _fake(**kwargs):
        assert pathguard.active_garden() is None
        return LoopResult(ok=True, reason="complete", iterations=1,
                          tokens_used=1, final_message="RESULT: ok")

    with patch("sovereign_agent.agent_session.agent_loop", new=AsyncMock(side_effect=_fake)):
        r = await run_session(
            session_id=state.session_id,
            tools=_build_tools_for_mode(Mode.BUSY),
            budget=RunBudget(max_iterations=5, max_wall_seconds=60, max_tokens=10_000),
            horizon_required=False,
        )
    assert r.status == "complete"
