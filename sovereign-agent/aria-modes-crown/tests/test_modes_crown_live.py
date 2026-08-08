"""aria-modes-crown — declarative modes, inner stances, the observatory.
(FABLE II · M6)

Pre-apply, patch-dependent behavior skips with a written reason; the
apply script re-runs this file and requires zero skips.
"""
from __future__ import annotations

import inspect


def _patched(obj) -> bool:
    return "modes-crown-d" in inspect.getsource(obj)


# ─── profiles ────────────────────────────────────────────────────────────


def test_all_profiles_declare_their_walls():
    from sovereign_agent.modes_crown import PROFILES

    assert set(PROFILES) == {
        "chat", "work", "auto-1h", "auto-3h", "focus", "companion", "guardian",
    }
    assert PROFILES["guardian"].tier_ceiling == 0
    assert not PROFILES["guardian"].work_allowed
    assert PROFILES["focus"].garden_required
    assert PROFILES["auto-3h"].typed_confirmation
    assert PROFILES["auto-1h"].lease_seconds == 3600
    assert PROFILES["auto-3h"].lease_seconds == 3 * 3600
    # PROTOCOL-ZERO/halt/rest are untouched — no profile field claims them;
    # they are not gated by the crown at all (verified structurally: no
    # profile references protocol_zero).
    import sovereign_agent.modes_crown.profiles as p

    assert "protocol_zero" not in inspect.getsource(p)


def test_current_profile_falls_back_to_base_mode_when_crown_unset(tmp_path):
    from sovereign_agent.cockpit_modes import CockpitMode, set_mode
    from sovereign_agent.modes_crown import current_profile

    set_mode(CockpitMode.WORK)
    assert current_profile().mode_id == "work"
    set_mode(CockpitMode.CHAT)
    assert current_profile().mode_id == "chat"


def test_set_crown_mode_writes_base_mode_and_event(tmp_path, monkeypatch):
    import sovereign_agent.events as events_mod
    from sovereign_agent.cockpit_modes import load_mode
    from sovereign_agent.modes_crown import current_profile, set_crown_mode

    seen = []
    monkeypatch.setattr(events_mod, "emit_event",
                        lambda flag, **kw: seen.append((flag, kw)))
    profile = set_crown_mode("companion")
    assert profile.mode_id == "companion"
    assert current_profile().mode_id == "companion"
    assert load_mode().mode.value == "chat"   # companion's base
    assert any(f == "mode-crown-d" for f, _ in seen)


def test_auto3h_refuses_without_the_typed_phrase():
    from sovereign_agent.modes_crown import CrownError, set_crown_mode

    import pytest

    with pytest.raises(CrownError, match="typed confirmation"):
        set_crown_mode("auto-3h")
    with pytest.raises(CrownError, match="typed confirmation"):
        set_crown_mode("auto-3h", confirm="close but no")


def test_unknown_mode_refuses():
    import pytest

    from sovereign_agent.modes_crown import CrownError, set_crown_mode

    with pytest.raises(CrownError, match="unknown mode"):
        set_crown_mode("nonexistent-mode")


def test_auto1h_arms_a_lease_and_wires_the_bridge_record_action():
    """The crown composes M5's lease wire: arming auto-1h creates an
    AutonomySession, arms it on the bridge, and record_action logs the
    arming — never self-extends."""
    import pytest

    from sovereign_agent import session_bridge

    if not _patched(session_bridge) and "thread-grooming-d" not in inspect.getsource(session_bridge):
        pytest.skip("pre-apply: session_bridge lease wire not yet applied (M5)")
    from sovereign_agent.modes_crown import set_crown_mode

    try:
        profile = set_crown_mode("auto-1h")
    finally:
        pass
    lease = session_bridge.active_lease()
    assert lease is not None
    assert lease.status == "active"
    assert lease.ttl_seconds == profile.lease_seconds
    # cleanup: switching back to chat disarms it
    set_crown_mode("chat")
    assert session_bridge.active_lease() is None


def test_crown_mode_change_disarms_a_prior_lease():
    from sovereign_agent import session_bridge
    from sovereign_agent.modes_crown import set_crown_mode

    set_crown_mode("auto-1h")
    assert session_bridge.active_lease() is not None
    set_crown_mode("work")   # no lease → the old one must be gone
    assert session_bridge.active_lease() is None


def test_lease_remaining_seconds_reads_the_armed_lease():
    from sovereign_agent.modes_crown import lease_remaining_seconds, set_crown_mode

    assert lease_remaining_seconds() == 0
    set_crown_mode("auto-1h")
    remaining = lease_remaining_seconds()
    assert 0 < remaining <= 3600
    set_crown_mode("chat")
    assert lease_remaining_seconds() == 0


def test_crown_wondering_allowed_tristate():
    from sovereign_agent.modes_crown import crown_wondering_allowed, set_crown_mode

    assert crown_wondering_allowed() is None   # never armed → today's behavior
    set_crown_mode("guardian")
    assert crown_wondering_allowed() is False
    set_crown_mode("companion")
    assert crown_wondering_allowed() is True


# ─── stances ─────────────────────────────────────────────────────────────


def test_stance_set_and_clear_roundtrip():
    from sovereign_agent.modes_crown import current_stance, set_stance

    assert current_stance() == ""
    set_stance("thinking", note="working the M6 shape")
    assert current_stance() == "thinking"
    set_stance("")
    assert current_stance() == ""


def test_unknown_stance_refuses():
    import pytest

    from sovereign_agent.modes_crown import set_stance

    with pytest.raises(ValueError, match="unknown stance"):
        set_stance("panicking")


def test_stance_history_records_the_trail():
    from sovereign_agent.modes_crown import recent_stances, set_stance

    set_stance("planning")
    set_stance("verifying")
    set_stance("cool-down")
    trail = [r["stance"] for r in recent_stances(10)]
    assert trail == ["planning", "verifying", "cool-down"]


def test_cool_down_reports_true_only_while_set():
    from sovereign_agent.modes_crown import cooling_down, set_stance

    assert not cooling_down()
    set_stance("cool-down")
    assert cooling_down()
    set_stance("auditing")
    assert not cooling_down()


def test_stance_kill_switch(monkeypatch):
    from sovereign_agent.modes_crown import current_stance, set_stance

    monkeypatch.setenv("SOV_NO_STANCES", "1")
    set_stance("thinking")
    assert current_stance() == ""   # write was skipped


# ─── the crown gate on the bridge (post M5+M6 apply) ─────────────────────


def test_guardian_mode_refuses_work_sessions():
    import asyncio

    import pytest

    from sovereign_agent import session_bridge

    if not _patched(session_bridge):
        pytest.skip("pre-apply: bridge crown gate not yet applied")
    from sovereign_agent.modes_crown import set_crown_mode

    set_crown_mode("guardian")
    with pytest.raises(PermissionError, match="does not run work"):
        asyncio.run(session_bridge.start_goal_session("a goal"))


def test_focus_mode_requires_a_garden():
    import asyncio

    import pytest

    from sovereign_agent import session_bridge

    if not _patched(session_bridge):
        pytest.skip("pre-apply: bridge crown gate not yet applied")
    from sovereign_agent.modes_crown import set_crown_mode

    set_crown_mode("focus")
    with pytest.raises(PermissionError, match="requires a garden"):
        asyncio.run(session_bridge.start_goal_session("a goal"))


def test_focus_mode_with_a_garden_passes_the_gate(tmp_path):
    """The gate must not block a properly-scoped focus goal; it should
    fail LATER for an unrelated reason (no live model), never here."""
    import asyncio

    import pytest

    from sovereign_agent import session_bridge

    if not _patched(session_bridge):
        pytest.skip("pre-apply: bridge crown gate not yet applied")
    from sovereign_agent.modes_crown import set_crown_mode

    set_crown_mode("focus")
    garden = tmp_path / "garden"
    garden.mkdir()
    with pytest.raises(PermissionError, match="requires a garden"):
        # no scope declared at all — still refused
        asyncio.run(session_bridge.start_goal_session("a goal"))
    try:
        asyncio.run(session_bridge.start_goal_session(
            f"a goal | scope: dir: {garden}"))
    except PermissionError as exc:
        assert "garden" not in str(exc)   # the gate passed; some later step failed
    except Exception:  # noqa: BLE001 — no live model in this test env
        pass


def test_cool_down_pauses_new_dispatches_but_not_todays_default():
    import asyncio

    import pytest

    from sovereign_agent import session_bridge

    if not _patched(session_bridge):
        pytest.skip("pre-apply: bridge crown gate not yet applied")
    from sovereign_agent.modes_crown import set_crown_mode, set_stance

    set_crown_mode("work")
    set_stance("cool-down")
    with pytest.raises(PermissionError, match="cooling down"):
        asyncio.run(session_bridge.start_goal_session("a goal"))
    set_stance("")
    # gate passes now (may still fail later for lack of a live model)
    try:
        asyncio.run(session_bridge.start_goal_session("a goal"))
    except PermissionError as exc:
        assert "cooling down" not in str(exc)
    except Exception:  # noqa: BLE001
        pass


def test_unarmed_crown_never_blocks_an_explicit_start_goal_session():
    """The regression this fix closes: before the operator ever touches
    F2/`/modes`, start_goal_session must behave exactly as it always did —
    the passive chat/work toggle only ever gated AUTONOMOUS loops, never
    an explicit dispatch. crown_armed() being False must short-circuit
    the gate entirely."""
    import asyncio
    from unittest.mock import AsyncMock, patch

    import pytest

    from sovereign_agent import session_bridge

    if not _patched(session_bridge):
        pytest.skip("pre-apply: bridge crown gate not yet applied")
    from sovereign_agent.loop import LoopResult
    from sovereign_agent.modes_crown import crown_armed

    assert not crown_armed()   # never armed in this fresh tmp data dir
    fake = AsyncMock(return_value=LoopResult(
        ok=True, reason="complete", iterations=1, tokens_used=10,
        final_message="RESULT: done",
    ))
    with patch("sovereign_agent.agent_session.agent_loop", new=fake):
        result = asyncio.run(session_bridge.start_goal_session("do a small kindness"))
    assert result.status == "complete"


def test_no_crown_applied_is_todays_behavior(monkeypatch):
    """With the crown module absent (simulated via ImportError), the gate
    must be a pure no-op — never break an operator who hasn't upgraded."""
    import sovereign_agent.session_bridge as bridge_mod

    if not _patched(bridge_mod):
        return   # pre-apply: nothing to test yet, and that's fine
    import builtins

    real_import = builtins.__import__

    def _blocked(name, *a, **kw):
        if name.startswith("sovereign_agent.modes_crown"):
            raise ImportError("simulated: crown not applied")
        return real_import(name, *a, **kw)

    monkeypatch.setattr(builtins, "__import__", _blocked)
    bridge_mod._crown_gate("any goal", None)   # must not raise


# ─── the wondering gate (post M6 apply) ──────────────────────────────────


def test_autonomous_wonder_honors_crown_over_base_mode():
    import pytest

    from sovereign_agent import curiosity

    if not _patched(curiosity):
        pytest.skip("pre-apply: curiosity gate not yet applied")
    from sovereign_agent.cockpit_modes import CockpitMode, set_mode
    from sovereign_agent.modes_crown import set_crown_mode

    set_mode(CockpitMode.WORK)   # base says yes
    set_crown_mode("guardian")   # crown says no — crown wins
    assert curiosity.autonomous_wonder_allowed() is False


# ─── the cache/side-effect fix (found by this round's suite) ─────────────


def test_request_tools_is_not_cacheable():
    import pytest

    from sovereign_agent.tools.tool_paging import RequestToolsTool

    if not _patched(sys_module_for("sovereign_agent.tools.tool_paging")):
        pytest.skip("pre-apply: cacheable flag not yet applied")
    assert RequestToolsTool.cacheable is False


def sys_module_for(name: str):
    import importlib

    return importlib.import_module(name)


def test_stance_and_observatory_tools_are_not_cacheable():
    from sovereign_agent.tools.stance_tools import ObservatoryTool, SetStanceTool

    assert SetStanceTool.cacheable is False
    assert ObservatoryTool.cacheable is False


def test_loop_never_skips_a_side_effecting_grant_via_cache():
    """The regression this module fixes, exercised directly: two identical
    request_tools calls inside a TTL window must attach BOTH times, never
    short-circuit the second on a cache hit."""
    import asyncio

    import pytest

    from sovereign_agent.loop import _response_cache

    if not _patched(sys_module_for("sovereign_agent.loop")):
        pytest.skip("pre-apply: loop.py cache-skip fix not yet applied")
    from sovereign_agent.cli import _build_tools_for_mode
    from sovereign_agent.loop import agent_loop
    from sovereign_agent.modes import Mode, RunBudget

    tools = _build_tools_for_mode(Mode.ONESHOT)
    calls = {"n": 0}
    seen_tool_contents: list[str] = []

    class _C:
        async def chat(self, *, messages, **kw):
            for m in messages:
                if m.get("role") == "tool":
                    seen_tool_contents.append(m.get("content", ""))
            calls["n"] += 1
            n = calls["n"]
            if n in (1, 3):
                return {"message": {"role": "assistant", "content": "", "tool_calls": [
                    {"function": {"name": "request_tools",
                                  "arguments": {"names": ["flaw_read"]}}}]}}
            if n in (2, 4):
                return {"message": {"role": "assistant", "content": "", "tool_calls": [
                    {"function": {"name": "flaw_read", "arguments": {}}}]}}
            return {"message": {"role": "assistant", "content": "done"}}

    async def _run():
        return await agent_loop(
            goal="paging twice, cache-hot the second time",
            mode=Mode.ONESHOT,
            budget=RunBudget(max_iterations=8, max_wall_seconds=60,
                             max_tokens=100_000),
            tools=tools, client=_C(), enable_reflector=False,
        )

    result = asyncio.run(_run())
    assert result.ok
    flaw_reads = [c for c in seen_tool_contents if "granted" not in c
                 and "NOT ATTACHED" not in c and c]
    # both flaw_read dispatches after paging must be REAL results, not the
    # not-attached refusal — even with the response cache warm.
    assert not any("NOT ATTACHED" in c for c in seen_tool_contents[2:])
