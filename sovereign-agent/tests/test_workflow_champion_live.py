"""Behavior tests for aria-workflow-champion, promoted to live tests/ —
the REAL modules; the model is faked."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

_GOOD_DESIGN = {
    "title": "Parser hardening",
    "steps": [
        {"description": "map the failure cases", "tool": "read_file",
         "verify": "a written list of failing inputs exists",
         "risk": "missing edge cases — mitigate by fuzzing"},
        {"description": "fix the tokenizer", "tool": "edit_file",
         "verify": "run_tests passes the new cases",
         "risk": "regression — full suite after"},
    ],
    "scope": {"in_scope": ["src/parser"], "out_of_scope": ["docs"],
              "done_when": "all mapped cases pass", "observe": ["test pass rate"],
              "security": ["read-only outside src/parser"]},
    "platform_notes": "n/a",
}


class _FakeClient:
    def __init__(self, payload=None, raw=None):
        self._payload, self._raw = payload, raw

    async def chat(self, **kwargs):
        content = self._raw if self._raw is not None else json.dumps(self._payload)
        return {"message": {"role": "assistant", "content": content}}


def test_registered_t1_propose_only():
    import sovereign_agent.tools  # noqa: F401
    from sovereign_agent.authority import _TIER_REGISTRY

    assert "design_workflow" in _TIER_REGISTRY
    assert _TIER_REGISTRY["design_workflow"].tier == 1


@pytest.mark.asyncio
async def test_design_saves_draft_and_builds_the_handoff():
    from sovereign_agent.tools.design_workflow import DesignWorkflowTool, list_drafts

    tool = DesignWorkflowTool()
    with patch("sovereign_agent.ollama_client.OllamaClient",
               return_value=_FakeClient(_GOOD_DESIGN)):
        r = await tool.execute(tool.Args(goal="harden the parser"), trace_id="t")
    assert r.ok
    assert r.output["handoff"].startswith("/work harden the parser | scope: ")
    assert "out: docs" in r.output["handoff"]
    assert "watch: test pass rate" in r.output["handoff"]
    assert "security: read-only outside src/parser" in r.output["handoff"]
    drafts = list_drafts()
    assert any(d["draft_id"] == r.output["draft_id"] for d in drafts)


@pytest.mark.asyncio
async def test_handoff_parses_back_into_a_scope_contract():
    """The championship loop closes: her designed scope round-trips through
    K10's parser — design → /work → contract, losslessly."""
    from sovereign_agent.scope import parse_goal_with_scope
    from sovereign_agent.tools.design_workflow import handoff_line

    draft = dict(_GOOD_DESIGN, goal="harden the parser")
    line = handoff_line(draft)
    goal, sc = parse_goal_with_scope(line.removeprefix("/work "))
    assert goal == "harden the parser"
    assert sc.out_of_scope == ["docs"]
    assert sc.observe == ["test pass rate"]
    assert sc.security == ["read-only outside src/parser"]
    assert sc.done_when == "all mapped cases pass"


@pytest.mark.asyncio
async def test_never_executes_anything():
    """Propose-only: designing must never touch run_session/agent_loop."""
    from sovereign_agent.tools.design_workflow import DesignWorkflowTool

    tool = DesignWorkflowTool()
    with patch("sovereign_agent.ollama_client.OllamaClient",
               return_value=_FakeClient(_GOOD_DESIGN)), \
         patch("sovereign_agent.agent_session.run_session",
               new=AsyncMock(side_effect=AssertionError("design must never run"))), \
         patch("sovereign_agent.agent_session.agent_loop",
               new=AsyncMock(side_effect=AssertionError("design must never run"))):
        r = await tool.execute(tool.Args(goal="anything at all"), trace_id="t")
    assert r.ok


@pytest.mark.asyncio
async def test_malformed_design_fails_honestly():
    from sovereign_agent.tools.design_workflow import DesignWorkflowTool

    tool = DesignWorkflowTool()
    with patch("sovereign_agent.ollama_client.OllamaClient",
               return_value=_FakeClient(raw="not json")):
        r = await tool.execute(tool.Args(goal="something"), trace_id="t")
    assert not r.ok and "malformed_design" in r.error


def test_designed_event_renders_richly():
    from sovereign_agent.cockpit.run_surface import render_rich_event

    out = render_rich_event({"flag": "workflow-designed-d",
                             "payload": {"title": "Parser hardening", "steps": 2}})
    assert out is not None and "designed" in out and "Parser hardening" in out
