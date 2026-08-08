"""
test_workflow_wire.py — Tests for workflow agent tools (M28, aria-workflow-wire).
"""
from __future__ import annotations

import asyncio
import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch


# ── helpers ───────────────────────────────────────────────────────────────


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _make_fake_loop(outcome=None, check_data=None, plan_steps=None, root_task=None):
    """Build a minimal fake AgenticLoop for tool tests."""
    from sovereign_agent.workflow.agentic_loop import StepOutcome, PlanStep
    from sovereign_agent.persistence.projects import Task

    fake_loop = MagicMock()
    fake_loop.intake.return_value = "wf-test-01"
    fake_loop.write_plan.return_value = ["step-01", "step-02"]
    fake_loop.step.return_value = outcome or StepOutcome(
        succeeded=True, summary="step done", extra={}
    )
    fake_loop.check.return_value = check_data or {
        "workflow_id": "wf-test-01",
        "total_steps": 2,
        "by_status": {"planned": 1, "done": 1},
        "complete": False,
        "next_step": MagicMock(title="step 2", description=json.dumps({"action_kind": "note"})),
        "next_step_id": "step-02",
    }
    fake_loop.plan_steps.return_value = plan_steps or []
    return fake_loop


def _make_fake_projects(task=None):
    fake_projects = MagicMock()
    fake_projects.get_project_by_name.return_value = None
    fake_projects.create_project.return_value = "proj-01"
    fake_projects.get_task.return_value = task
    return fake_projects


# ── WorkflowCreateTool ────────────────────────────────────────────────────


def test_workflow_create_registered():
    from sovereign_agent.tools.workflow_tools import WorkflowCreateTool
    assert WorkflowCreateTool.name == "workflow_create"
    assert WorkflowCreateTool.tier == 1
    assert WorkflowCreateTool.failure_modes


def test_workflow_create_success(tmp_path):
    from sovereign_agent.tools.workflow_tools import WorkflowCreateTool

    fake_loop = _make_fake_loop()
    fake_projects = _make_fake_projects()

    with patch("sovereign_agent.tools.workflow_tools._open_loop", return_value=(fake_loop, fake_projects)):
        tool = WorkflowCreateTool()
        result = _run(tool.execute(
            tool.Args(
                goal="test goal",
                project_name="test-proj",
                steps=[
                    {"title": "step 1", "action_kind": "note", "action_input": {"text": "hello"}},
                    {"title": "step 2", "action_kind": "shell", "action_input": {"argv": ["ls"]}},
                ],
            ),
            trace_id="t1",
        ))

    assert result.ok
    assert result.output["workflow_id"] == "wf-test-01"
    assert result.output["step_count"] == 2
    fake_loop.intake.assert_called_once()
    fake_loop.write_plan.assert_called_once()


def test_workflow_create_rejects_unknown_action_kind(tmp_path):
    from sovereign_agent.tools.workflow_tools import WorkflowCreateTool

    tool = WorkflowCreateTool()
    result = _run(tool.execute(
        tool.Args(
            goal="test",
            steps=[{"title": "bad", "action_kind": "rm_rf", "action_input": {}}],
        ),
        trace_id="t1",
    ))

    assert not result.ok
    assert "rm_rf" in result.error


def test_workflow_create_uses_existing_project():
    from sovereign_agent.tools.workflow_tools import WorkflowCreateTool
    from unittest.mock import MagicMock

    fake_loop = _make_fake_loop()
    fake_projects = _make_fake_projects()
    existing_proj = MagicMock()
    existing_proj.project_id = "existing-proj-id"
    fake_projects.get_project_by_name.return_value = existing_proj

    with patch("sovereign_agent.tools.workflow_tools._open_loop", return_value=(fake_loop, fake_projects)):
        tool = WorkflowCreateTool()
        result = _run(tool.execute(
            tool.Args(
                goal="test goal",
                project_name="my-project",
                steps=[{"title": "step 1", "action_kind": "note", "action_input": {}}],
            ),
            trace_id="t1",
        ))

    assert result.ok
    assert result.output["project_id"] == "existing-proj-id"
    fake_projects.create_project.assert_not_called()


# ── WorkflowStepTool ──────────────────────────────────────────────────────


def test_workflow_step_registered():
    from sovereign_agent.tools.workflow_tools import WorkflowStepTool
    assert WorkflowStepTool.name == "workflow_step"
    assert WorkflowStepTool.tier == 1
    assert WorkflowStepTool.failure_modes


def test_workflow_step_success():
    from sovereign_agent.tools.workflow_tools import WorkflowStepTool
    from sovereign_agent.workflow.agentic_loop import StepOutcome
    from unittest.mock import MagicMock

    root_task = MagicMock()
    root_task.title = "workflow: test goal"
    fake_loop = _make_fake_loop(
        outcome=StepOutcome(
            succeeded=True,
            summary="ran ls",
            artifacts=["output.txt"],
            extra={"stdout": "file.py\n", "stderr": "", "exit_code": 0},
        )
    )
    fake_projects = _make_fake_projects(task=root_task)

    with patch("sovereign_agent.tools.workflow_tools._open_loop", return_value=(fake_loop, fake_projects)):
        tool = WorkflowStepTool()
        result = _run(tool.execute(
            tool.Args(workflow_id="wf-test-01"),
            trace_id="t1",
        ))

    assert result.ok
    assert result.output["succeeded"] is True
    assert result.output["summary"] == "ran ls"
    assert result.output["stdout"] == "file.py\n"
    assert "output.txt" in result.output["artifacts"]


def test_workflow_step_no_planned_steps():
    from sovereign_agent.tools.workflow_tools import WorkflowStepTool
    from unittest.mock import MagicMock

    root_task = MagicMock()
    fake_loop = _make_fake_loop()
    fake_loop.step.return_value = None  # no more steps
    fake_projects = _make_fake_projects(task=root_task)

    with patch("sovereign_agent.tools.workflow_tools._open_loop", return_value=(fake_loop, fake_projects)):
        tool = WorkflowStepTool()
        result = _run(tool.execute(
            tool.Args(workflow_id="wf-test-01"),
            trace_id="t1",
        ))

    assert result.ok
    assert result.output.get("no_planned_steps") is True


def test_workflow_step_workflow_not_found():
    from sovereign_agent.tools.workflow_tools import WorkflowStepTool

    fake_loop = _make_fake_loop()
    fake_projects = _make_fake_projects(task=None)  # task not found

    with patch("sovereign_agent.tools.workflow_tools._open_loop", return_value=(fake_loop, fake_projects)):
        tool = WorkflowStepTool()
        result = _run(tool.execute(
            tool.Args(workflow_id="nonexistent"),
            trace_id="t1",
        ))

    assert not result.ok
    assert "not found" in result.error


def test_workflow_step_handler_failure():
    from sovereign_agent.tools.workflow_tools import WorkflowStepTool
    from sovereign_agent.workflow.agentic_loop import StepOutcome
    from unittest.mock import MagicMock

    root_task = MagicMock()
    fake_loop = _make_fake_loop(
        outcome=StepOutcome(
            succeeded=False,
            summary="command not in allowlist",
            error="allowlist-rejection",
        )
    )
    fake_projects = _make_fake_projects(task=root_task)

    with patch("sovereign_agent.tools.workflow_tools._open_loop", return_value=(fake_loop, fake_projects)):
        tool = WorkflowStepTool()
        result = _run(tool.execute(
            tool.Args(workflow_id="wf-test-01"),
            trace_id="t1",
        ))

    # The tool returns ok=True even if the step failed — failure is in output.succeeded
    assert result.ok
    assert result.output["succeeded"] is False
    assert result.output["error"] == "allowlist-rejection"


# ── WorkflowStatusTool ────────────────────────────────────────────────────


def test_workflow_status_registered():
    from sovereign_agent.tools.workflow_tools import WorkflowStatusTool
    assert WorkflowStatusTool.name == "workflow_status"
    assert WorkflowStatusTool.tier == 0
    assert WorkflowStatusTool.failure_modes


def test_workflow_status_success():
    from sovereign_agent.tools.workflow_tools import WorkflowStatusTool
    from unittest.mock import MagicMock

    root_task = MagicMock()
    root_task.title = "workflow: do something important"
    fake_loop = _make_fake_loop()
    fake_projects = _make_fake_projects(task=root_task)

    with patch("sovereign_agent.tools.workflow_tools._open_loop", return_value=(fake_loop, fake_projects)):
        tool = WorkflowStatusTool()
        result = _run(tool.execute(
            tool.Args(workflow_id="wf-test-01"),
            trace_id="t1",
        ))

    assert result.ok
    assert result.output["workflow_id"] == "wf-test-01"
    assert result.output["total_steps"] == 2
    assert "by_status" in result.output
    assert "complete" in result.output


def test_workflow_status_not_found():
    from sovereign_agent.tools.workflow_tools import WorkflowStatusTool

    fake_loop = _make_fake_loop()
    fake_projects = _make_fake_projects(task=None)

    with patch("sovereign_agent.tools.workflow_tools._open_loop", return_value=(fake_loop, fake_projects)):
        tool = WorkflowStatusTool()
        result = _run(tool.execute(
            tool.Args(workflow_id="nonexistent"),
            trace_id="t1",
        ))

    assert not result.ok
    assert "not found" in result.error


# ── Integration: full mini-workflow ──────────────────────────────────────


def test_workflow_create_then_status(tmp_path):
    """End-to-end: create a workflow, then check its status via the real DB."""
    import sys
    sov = str(Path(__file__).resolve().parents[4] / "src")
    if sov not in sys.path:
        sys.path.insert(0, sov)

    from sovereign_agent.persistence.store import ErebloStore
    from sovereign_agent.persistence.projects import ProjectsManager
    from sovereign_agent.workflow.agentic_loop import AgenticLoop

    db_path = tmp_path / "atoms.db"
    store = ErebloStore(db_path)
    projects = ProjectsManager(store)
    loop = AgenticLoop(projects)

    # Create a project + workflow manually (the way the tool would)
    project_id = projects.create_project("e2e-test", description="end to end")
    from sovereign_agent.workflow.agentic_loop import PlanStep
    workflow_id = loop.intake(project_id, "run two note steps")
    loop.write_plan(workflow_id, [
        PlanStep(title="step 1", description="note", action_kind="note", action_input={"text": "hi"}),
        PlanStep(title="step 2", description="note", action_kind="note", action_input={"text": "bye"}),
    ])

    status = loop.check(workflow_id)
    assert status["total_steps"] == 2
    assert status["by_status"].get("planned") == 2
    assert not status["complete"]

    # Step through both
    outcome1 = loop.step(workflow_id)
    assert outcome1 is not None
    assert outcome1.succeeded

    outcome2 = loop.step(workflow_id)
    assert outcome2 is not None
    assert outcome2.succeeded

    # No more steps
    outcome3 = loop.step(workflow_id)
    assert outcome3 is None

    final = loop.check(workflow_id)
    assert final["complete"]
    assert final["by_status"].get("done") == 2
