"""
test_god_workflow.py — Tests for M30 god-tier workflow tools.
"""
from __future__ import annotations

import json
import pytest
from unittest.mock import MagicMock, patch


# ── GodTierEngine unit tests ──────────────────────────────────────────────


def _make_engine(steps=None, step_outcome=None):
    """Build a GodTierEngine with a fake AgenticLoop."""
    from sovereign_agent.workflow.god_engine import GodTierEngine
    from sovereign_agent.workflow.agentic_loop import StepOutcome, PlanStep
    from sovereign_agent.persistence.projects import Task

    fake_step = MagicMock(spec=Task)
    fake_step.task_id = "step-001"
    fake_step.title = "test step"
    fake_step.status = "planned"
    fake_step.ordinal = 1
    fake_step.description = json.dumps({
        "action_kind": "note",
        "action_input": {"text": "hello"},
    })

    fake_loop = MagicMock()
    fake_loop.next_planned_step.return_value = fake_step
    fake_loop.plan_steps.return_value = [fake_step]
    fake_loop.step.return_value = step_outcome or StepOutcome(
        succeeded=True, summary="done", artifacts=[], extra={}
    )

    fake_projects = MagicMock()
    fake_projects.get_task.return_value = fake_step

    return GodTierEngine(loop=fake_loop, projects=fake_projects), fake_loop, fake_projects


def test_god_engine_imports():
    from sovereign_agent.workflow.god_engine import GodTierEngine, GodStepOutcome, VerifyOutcome, DepsReport
    assert GodTierEngine
    assert GodStepOutcome
    assert VerifyOutcome
    assert DepsReport


def test_step_with_recovery_success_first_try():
    """step_with_recovery returns immediately when primary step succeeds."""
    from sovereign_agent.workflow.agentic_loop import StepOutcome

    engine, loop, projects = _make_engine(
        step_outcome=StepOutcome(succeeded=True, summary="all good", artifacts=["out.txt"])
    )
    result = engine.step_with_recovery("wf-001", max_attempts=3)

    assert result is not None
    assert result.succeeded
    assert result.attempts == 1
    assert not result.alternative_used
    assert result.summary == "all good"


def test_step_with_recovery_uses_alternative():
    """step_with_recovery tries an alternative when primary fails."""
    from sovereign_agent.workflow.agentic_loop import StepOutcome
    from sovereign_agent.persistence.projects import Task

    fail_outcome = StepOutcome(succeeded=False, summary="fail", error="timeout")
    ok_outcome = StepOutcome(succeeded=True, summary="alt worked", artifacts=[])

    fake_step = MagicMock(spec=Task)
    fake_step.task_id = "step-001"
    fake_step.title = "test"
    fake_step.status = "planned"
    fake_step.ordinal = 1
    fake_step.description = json.dumps({
        "action_kind": "shell",
        "action_input": {
            "argv": ["pytest"],
            "alternatives": [
                {"action_kind": "shell", "action_input": {"argv": ["python", "-m", "pytest"]}}
            ],
        },
    })

    from sovereign_agent.workflow.god_engine import GodTierEngine
    fake_loop = MagicMock()
    fake_loop.next_planned_step.return_value = fake_step
    fake_loop.step.side_effect = [fail_outcome, ok_outcome]

    fake_projects = MagicMock()
    engine = GodTierEngine(loop=fake_loop, projects=fake_projects)

    result = engine.step_with_recovery("wf-001", max_attempts=3)
    assert result is not None
    assert result.succeeded
    assert result.alternative_used
    assert result.attempts == 2


def test_step_with_recovery_exhausted():
    """step_with_recovery returns failed GodStepOutcome after all alternatives."""
    from sovereign_agent.workflow.agentic_loop import StepOutcome

    fail = StepOutcome(succeeded=False, summary="fail", error="blocked")
    engine, loop, _ = _make_engine(step_outcome=fail)
    loop.step.return_value = fail  # always fails

    result = engine.step_with_recovery("wf-001", max_attempts=2)
    assert result is not None
    assert not result.succeeded
    assert "attempt_log" in result.extra


def test_verify_step_verified():
    """verify_step returns 'verified' when criteria evaluates truthy."""
    from sovereign_agent.persistence.projects import Task

    fake_step = MagicMock(spec=Task)
    fake_step.task_id = "step-001"
    fake_step.status = "done"
    fake_step.description = json.dumps({"extra": {"exit_code": 0}, "artifacts": ["out.txt"]})

    from sovereign_agent.workflow.god_engine import GodTierEngine
    fake_loop = MagicMock()
    fake_loop.plan_steps.return_value = []
    fake_projects = MagicMock()
    fake_projects.get_task.return_value = fake_step
    engine = GodTierEngine(loop=fake_loop, projects=fake_projects)

    result = engine.verify_step("wf-001", "step-001", "exit_code == 0")
    assert result.verdict == "verified"


def test_verify_step_unverified():
    """verify_step returns 'unverified' when criteria evaluates falsy."""
    from sovereign_agent.persistence.projects import Task

    fake_step = MagicMock(spec=Task)
    fake_step.task_id = "step-001"
    fake_step.status = "done"
    fake_step.description = json.dumps({"extra": {"exit_code": 1}, "artifacts": []})

    from sovereign_agent.workflow.god_engine import GodTierEngine
    fake_loop = MagicMock()
    fake_loop.plan_steps.return_value = []
    fake_projects = MagicMock()
    fake_projects.get_task.return_value = fake_step
    engine = GodTierEngine(loop=fake_loop, projects=fake_projects)

    result = engine.verify_step("wf-001", "step-001", "exit_code == 0")
    assert result.verdict == "unverified"


def test_validate_deps_valid():
    """validate_deps returns ok=True when all consumes are produced prior."""
    from sovereign_agent.persistence.projects import Task

    step_a = MagicMock(spec=Task)
    step_a.task_id = "s1"; step_a.title = "build"
    step_a.description = json.dumps({"action_input": {"produces": ["binary"], "consumes": []}})

    step_b = MagicMock(spec=Task)
    step_b.task_id = "s2"; step_b.title = "test"
    step_b.description = json.dumps({"action_input": {"consumes": ["binary"], "produces": ["test_results"]}})

    from sovereign_agent.workflow.god_engine import GodTierEngine
    fake_loop = MagicMock()
    fake_loop.plan_steps.return_value = [step_a, step_b]
    engine = GodTierEngine(loop=fake_loop, projects=MagicMock())

    report = engine.validate_deps("wf-001")
    assert report.ok
    assert len(report.broken) == 0


def test_validate_deps_broken():
    """validate_deps flags a step that consumes something not yet produced."""
    from sovereign_agent.persistence.projects import Task

    step_a = MagicMock(spec=Task)
    step_a.task_id = "s1"; step_a.title = "test"
    step_a.description = json.dumps({"action_input": {"consumes": ["binary"], "produces": []}})

    from sovereign_agent.workflow.god_engine import GodTierEngine
    fake_loop = MagicMock()
    fake_loop.plan_steps.return_value = [step_a]
    engine = GodTierEngine(loop=fake_loop, projects=MagicMock())

    report = engine.validate_deps("wf-001")
    assert not report.ok
    assert len(report.broken) == 1
    assert report.broken[0]["missing"] == "binary"


# ── Tool registration tests ───────────────────────────────────────────────


def test_god_workflow_tools_registered():
    import sovereign_agent.tools  # noqa: F401
    from sovereign_agent.authority import _TIER_REGISTRY
    assert "workflow_mutate" in _TIER_REGISTRY, "workflow_mutate not registered"
    assert "workflow_retry" in _TIER_REGISTRY, "workflow_retry not registered"
    assert "workflow_checkpoint" in _TIER_REGISTRY, "workflow_checkpoint not registered"
    assert "workflow_deps" in _TIER_REGISTRY, "workflow_deps not registered"
    assert _TIER_REGISTRY["workflow_mutate"].tier == 1
    assert _TIER_REGISTRY["workflow_retry"].tier == 1
    assert _TIER_REGISTRY["workflow_checkpoint"].tier == 0
    assert _TIER_REGISTRY["workflow_deps"].tier == 0


def test_loop_has_engineering_doctrine():
    import pathlib
    p = pathlib.Path(__file__).resolve()
    for _ in range(8):
        c = p.parent / "src" / "sovereign_agent" / "loop.py"
        if c.exists():
            src = c.read_text()
            assert "engineering-doctrine-d" in src, \
                "ENGINEERING DOCTRINE section missing — run apply_god_workflow.sh"
            assert "workflow-master-d" in src
            return
        p = p.parent
    pytest.skip("loop.py not found")


# ── WorkflowCheckpointTool execute test ───────────────────────────────────


@pytest.mark.asyncio
async def test_workflow_checkpoint_verified():
    from sovereign_agent.tools.god_workflow_tools import WorkflowCheckpointTool
    from sovereign_agent.workflow.god_engine import VerifyOutcome

    mock_engine = MagicMock()
    mock_engine.verify_step.return_value = VerifyOutcome(
        step_id="s1", criteria="exit_code == 0", verdict="verified", reasoning="ok"
    )

    with patch("sovereign_agent.tools.god_workflow_tools._open_god_engine",
               return_value=(mock_engine, MagicMock(), MagicMock())):
        tool = WorkflowCheckpointTool()
        result = await tool.execute(
            tool.Args(workflow_id="wf-1", step_id="s1", criteria="exit_code == 0"),
            trace_id="t1",
        )

    assert result.ok
    assert result.output["verdict"] == "verified"


@pytest.mark.asyncio
async def test_workflow_deps_ok():
    from sovereign_agent.tools.god_workflow_tools import WorkflowDepsTool
    from sovereign_agent.workflow.god_engine import DepsReport

    mock_engine = MagicMock()
    mock_engine.validate_deps.return_value = DepsReport(
        workflow_id="wf-1", ok=True, summary="DAG is valid.", broken=[]
    )
    mock_loop = MagicMock()
    mock_loop.plan_steps.return_value = []

    with patch("sovereign_agent.tools.god_workflow_tools._open_god_engine",
               return_value=(mock_engine, mock_loop, MagicMock())):
        tool = WorkflowDepsTool()
        result = await tool.execute(tool.Args(workflow_id="wf-1"), trace_id="t1")

    assert result.ok
    assert result.output["deps_ok"] is True


@pytest.mark.asyncio
async def test_workflow_mutate_rejects_unknown_kind():
    from sovereign_agent.tools.god_workflow_tools import WorkflowMutateTool
    tool = WorkflowMutateTool()
    result = await tool.execute(
        tool.Args(
            workflow_id="wf-1",
            from_ordinal=2,
            new_steps=[{"title": "bad", "action_kind": "rm_rf", "action_input": {}}],
        ),
        trace_id="t1",
    )
    assert not result.ok
    assert "rm_rf" in result.error
