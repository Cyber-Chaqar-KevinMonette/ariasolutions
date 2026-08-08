"""Behavior tests for aria-tool-paging, promoted to live tests/ — the
REAL, already-patched modules. Plain imports, no shadow copy.
"""
from __future__ import annotations

import pytest


def test_request_tools_registered_at_tier_0_and_in_diet_core():
    import sovereign_agent.tools  # noqa: F401
    from sovereign_agent import prompt_diet
    from sovereign_agent.authority import _TIER_REGISTRY

    assert "request_tools" in _TIER_REGISTRY
    assert _TIER_REGISTRY["request_tools"].tier == 0
    assert "request_tools" in prompt_diet.CORE_TOOL_NAMES
    assert "list_available_tools" in prompt_diet.CORE_TOOL_NAMES  # the pair


@pytest.mark.asyncio
async def test_request_tools_grants_known_and_names_unknown():
    import sovereign_agent.tools  # noqa: F401
    from sovereign_agent.tools.tool_paging import RequestToolsTool

    tool = RequestToolsTool()
    result = await tool.execute(
        tool.Args(names=["read_lessons", "definitely_not_a_tool"]), trace_id="t",
    )
    assert result.ok
    assert result.metadata["granted"] == ["read_lessons"]
    assert result.metadata["unknown"] == ["definitely_not_a_tool"]


@pytest.mark.asyncio
async def test_request_tools_all_unknown_fails_honestly():
    from sovereign_agent.tools.tool_paging import RequestToolsTool

    tool = RequestToolsTool()
    result = await tool.execute(tool.Args(names=["nope_1", "nope_2"]), trace_id="t")
    assert not result.ok
    assert "none_granted" in result.error


@pytest.mark.asyncio
async def test_loop_attaches_granted_tools_mid_run():
    """The full paging chain through the REAL agent_loop with a scripted
    model: iteration 1 calls a NON-attached tool (helpful refusal), then
    request_tools; iteration 2 calls the newly-attached tool successfully."""
    from sovereign_agent.cli import _build_tools_for_mode
    from sovereign_agent.loop import agent_loop
    from sovereign_agent.modes import Mode, RunBudget

    tools = _build_tools_for_mode(Mode.ONESHOT)
    calls = {"n": 0}
    transcripts: list[list[dict]] = []

    # flaw_read: T0, NOT in the diet core, and deliberately NOT named in
    # the goal below — otherwise the diet's goal-mention rule would attach
    # it up-front and defeat the test's premise (which is exactly what a
    # first draft of this test did with aria_status).
    class _FakeClient:
        async def chat(self, *, model, messages, tools=None, call_kind=None, **kw):
            transcripts.append([dict(m) for m in messages])
            calls["n"] += 1
            if calls["n"] == 1:
                return {"message": {"role": "assistant", "content": "", "tool_calls": [
                    {"function": {"name": "flaw_read", "arguments": {}}},
                    {"function": {"name": "request_tools",
                                  "arguments": {"names": ["flaw_read"]}}},
                ]}}
            if calls["n"] == 2:
                return {"message": {"role": "assistant", "content": "", "tool_calls": [
                    {"function": {"name": "flaw_read", "arguments": {}}},
                ]}}
            return {"message": {"role": "assistant", "content": "all done, with the paged tool."}}

    result = await agent_loop(
        goal="review your open self-knowledge items",
        mode=Mode.ONESHOT,
        budget=RunBudget(max_iterations=6, max_wall_seconds=60, max_tokens=100_000),
        tools=tools,
        client=_FakeClient(),
        enable_reflector=False,
    )
    assert result.ok
    flat = [m for turn in transcripts for m in turn if m.get("role") == "tool"]
    contents = [m.get("content", "") for m in flat]
    # 1st aria_status call: helpfully refused with the request_tools pointer
    assert any("NOT ATTACHED" in c and "request_tools" in c for c in contents)
    # 2nd flaw_read call (post-paging): a real result, not a refusal
    assert any(c and "NOT ATTACHED" not in c and "REFUSED" not in c
               and "granted" not in c for c in contents)


@pytest.mark.asyncio
async def test_unknown_name_gets_close_matches():
    from sovereign_agent.cli import _build_tools_for_mode
    from sovereign_agent.loop import agent_loop
    from sovereign_agent.modes import Mode, RunBudget

    tools = _build_tools_for_mode(Mode.ONESHOT)
    seen: list[str] = []

    class _FakeClient:
        async def chat(self, *, model, messages, tools=None, call_kind=None, **kw):
            for m in messages:
                if m.get("role") == "tool":
                    seen.append(m.get("content", ""))
            if not seen:
                return {"message": {"role": "assistant", "content": "", "tool_calls": [
                    {"function": {"name": "read_lesson", "arguments": {}}},  # typo
                ]}}
            return {"message": {"role": "assistant", "content": "ok"}}

    await agent_loop(
        goal="g", mode=Mode.ONESHOT,
        budget=RunBudget(max_iterations=4, max_wall_seconds=60, max_tokens=50_000),
        tools=tools, client=_FakeClient(), enable_reflector=False,
    )
    # The authority gate intercepts unknown names (KeyError) — the
    # suggestion now rides on ITS refusal message.
    assert any("read_lessons" in c and "REFUSED" in c for c in seen), (
        "close match not suggested: " + " | ".join(seen)
    )


@pytest.mark.asyncio
async def test_paging_never_exceeds_the_authority_gate():
    """A Tier-2 tool requested in BUSY mode (ceiling 1) is granted by the
    registry check but NEVER attached by the loop."""
    from sovereign_agent.cli import _build_tools_for_mode
    from sovereign_agent.loop import agent_loop
    from sovereign_agent.modes import Mode, RunBudget

    tools = _build_tools_for_mode(Mode.BUSY)
    tool_results: list[str] = []

    class _FakeClient:
        async def chat(self, *, model, messages, tools=None, call_kind=None, **kw):
            for m in messages:
                if m.get("role") == "tool":
                    tool_results.append(m.get("content", ""))
            n = sum(1 for m in messages if m.get("role") == "assistant")
            if n == 0:
                return {"message": {"role": "assistant", "content": "", "tool_calls": [
                    {"function": {"name": "request_tools",
                                  "arguments": {"names": ["git_commit"]}}},  # Tier 2
                ]}}
            if n == 1:
                return {"message": {"role": "assistant", "content": "", "tool_calls": [
                    {"function": {"name": "git_commit",
                                  "arguments": {"message": "nope"}}},
                ]}}
            return {"message": {"role": "assistant", "content": "done"}}

    await agent_loop(
        goal="g", mode=Mode.BUSY,
        budget=RunBudget(max_iterations=6, max_wall_seconds=60, max_tokens=50_000),
        tools=tools, client=_FakeClient(), enable_reflector=False,
    )
    # git_commit (T2 > BUSY ceiling 1) must never have executed — its only
    # trace is a refusal, never a real result.
    joined = "\n".join(tool_results)
    assert not any("committed" in c.lower() for c in tool_results)
    assert any("REFUSED" in c or "NOT ATTACHED" in c or "unknown tool" in c
               for c in tool_results if c), joined
