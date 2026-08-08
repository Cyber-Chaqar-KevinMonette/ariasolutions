"""Tests for the capability-awareness layer and the evolving run orchestrator.

All hermetic: a real (temp-file) ErebloStore/loop, fake scorer + planner, and a
recording fake handler. No Ollama, no network.
"""
from pathlib import Path

import pytest

from sovereign_agent.persistence.store import ErebloStore
from sovereign_agent.persistence.projects import ProjectsManager
from sovereign_agent.workflow.agentic_loop import AgenticLoop, PlanStep, StepOutcome
from sovereign_agent.workflow.capabilities import (
    Capability, CapabilityRegistry, VariantRouter, analyze_gaps, ScaffoldSpec,
    AuthorityPolicy, looks_self_modifying,
)
from sovereign_agent.workflow.evolving_run import EvolvingAgenticRun, _task_to_step


# ── fakes ────────────────────────────────────────────────────────────────


class _Assessment:
    def __init__(self, band, questions=None, dims=None):
        self.band = band
        self.suggested_clarifications = questions or []
        self.concerning_dimensions = dims or []


class _Scorer:
    def __init__(self, band="M2"):
        self._band = band
    def assess(self, goal, *, context_hint=None, prior_attempts=0):
        return _Assessment(self._band)


class _Planner:
    def __init__(self, steps):
        self._steps = steps
    def plan(self, goal):
        return list(self._steps)


class _RecordingHandler:
    def __init__(self):
        self.calls = []
    def __call__(self, task):
        self.calls.append(task.title)
        return StepOutcome(succeeded=True, summary=f"ran {task.title}")


@pytest.fixture
def loop(tmp_path):
    store = ErebloStore(tmp_path / "atoms.db")
    projects = ProjectsManager(store)
    lp = AgenticLoop(projects)
    return lp


@pytest.fixture
def project_id(loop):
    return loop._projects.create_project("t", description="test")


# ── registry ───────────────────────────────────────────────────────────────


def test_registry_marks_available_and_missing(loop):
    loop.register_tool_handler("shell", _RecordingHandler())
    reg = CapabilityRegistry.from_loop(loop)
    assert "shell" in reg.available_kinds()
    assert "note" in reg.available_kinds()          # baseline kind
    assert "timer_schedule" in reg.missing_kinds()  # catalogued, not wired


def test_registry_records_uncatalogued_registered_kind(loop):
    loop.register_tool_handler("custom_kind", _RecordingHandler())
    reg = CapabilityRegistry.from_loop(loop)
    assert "custom_kind" in reg.available_kinds()


# ── gap analysis ─────────────────────────────────────────────────────────


def test_gap_analysis_partitions_and_proposes(loop):
    reg = CapabilityRegistry.from_loop(loop)  # only note wired
    steps = [PlanStep("a", "", "note", {}),
             PlanStep("b", "", "timer_schedule", {"delay_sec": 5, "message": "x"})]
    gap = analyze_gaps(steps, reg, goal="demo")
    assert gap.needed == ["note", "timer_schedule"]
    assert "note" in gap.available
    assert gap.missing == ["timer_schedule"]
    assert [p.action_kind for p in gap.proposals] == ["timer_schedule"]


def test_scaffold_render_is_safe_and_named():
    spec = ScaffoldSpec.for_missing_kind("timer_schedule", goal="g")
    src = spec.render()
    assert "PROPOSED SUBSYSTEM — NOT ACTIVE" in src
    assert "class TimerScheduleHandler" in src
    assert "succeeded=False" in src          # no-op until implemented
    assert spec.filename == "timer_schedule__proposed.py"


def test_scaffold_write_proposal(tmp_path):
    spec = ScaffoldSpec.for_missing_kind("timer_schedule")
    p = spec.write_proposal(tmp_path / "proposals")
    assert p.exists() and p.name == "timer_schedule__proposed.py"
    assert "TimerScheduleHandler" in p.read_text()


# ── variant routing ────────────────────────────────────────────────────────


def test_variant_router_prefers_flow_specific_variant(loop):
    reg = CapabilityRegistry.from_loop(loop)
    reg.register(Capability("shell.git", "shell", "git shell",
                            frozenset({"git", "commit", "branch"}),
                            variant_of="shell.default"))
    ranked = VariantRouter().rank("shell.default", "init a git repo and commit", reg)
    assert ranked[0].capability.name == "shell.git"
    assert ranked[0].score > ranked[-1].score


def test_variant_router_defaults_when_no_overlap(loop):
    reg = CapabilityRegistry.from_loop(loop)
    reg.register(Capability("shell.git", "shell", "git shell",
                            frozenset({"git"}), variant_of="shell.default"))
    ranked = VariantRouter().rank("shell.default", "bake a cake", reg)
    # default wins on the tie-break when nothing matches the flow
    assert ranked[0].capability.name == "shell.default"


def test_catalog_ships_flow_variants(loop):
    """The shipped catalog routes common flows to the right shell variant
    with no manual registration."""
    reg = CapabilityRegistry.from_loop(loop)
    router = VariantRouter()
    assert router.best("shell.default", "commit and push to git", reg).capability.name == "shell.git"
    assert router.best("shell.default", "compile and build the package", reg).capability.name == "shell.build"


def test_catalog_file_write_variants(loop):
    reg = CapabilityRegistry.from_loop(loop)
    router = VariantRouter()
    assert router.best("file_write.default", "write the readme documentation",
                       reg).capability.name == "file_write.docs"


# ── authority policy ───────────────────────────────────────────────────────


def test_authority_policy_lines():
    pol = AuthorityPolicy()
    assert pol.assess("shell").requires_human is True
    assert pol.assess("file_write").requires_human is True
    assert pol.assess("file_read").self_answerable is True
    assert pol.assess("note").self_answerable is True
    # self-modification always needs a human, regardless of kind
    assert pol.assess("file_read", modifies_self=True).requires_human is True


def test_looks_self_modifying():
    assert looks_self_modifying(
        PlanStep("x", "", "file_write", {"path": "src/sovereign_agent/y.py"}),
        self_roots=[]) is True
    assert looks_self_modifying(
        PlanStep("x", "", "file_write", {"path": "/tmp/notes.txt"}),
        self_roots=[]) is False


# ── evolving run: planning ───────────────────────────────────────────────


def test_plan_only_reports_gaps_and_writes_proposals(loop, tmp_path):
    run = EvolvingAgenticRun(
        loop, planner=_Planner([PlanStep("t", "", "timer_schedule",
                                         {"delay_sec": 5, "message": "x"})]),
        scorer=_Scorer("M2"), proposals_root=tmp_path / "prop")
    plan = run.plan_only("remind me later", flow="reminder")
    assert plan.band == "M2"
    assert plan.gap_report.missing == ["timer_schedule"]
    assert plan.proposals_written and Path(plan.proposals_written[0]).exists()
    # variant routing recorded for the needed kind
    assert "timer_schedule" in plan.variant_choices


def test_plan_only_m0_asks_for_clarification(loop):
    run = EvolvingAgenticRun(loop, planner=_Planner([]), scorer=_Scorer("M0"))
    plan = run.plan_only("do the thing")
    assert plan.band == "M0"
    # no steps planned at M0
    assert plan.steps == []


# ── evolving run: gated execution ─────────────────────────────────────────


def test_execute_holds_on_missing_capability(loop, project_id, tmp_path):
    run = EvolvingAgenticRun(
        loop, planner=_Planner([PlanStep("t", "", "timer_schedule",
                                         {"delay_sec": 5, "message": "x"})]),
        scorer=_Scorer("M2"), proposals_root=tmp_path / "prop")
    res = run.execute("remind me", project_id)
    assert res.decision == "needs_capability"
    assert res.workflow_id is None          # nothing was run


def test_execute_runs_when_approved(loop, project_id):
    handler = _RecordingHandler()
    loop.register_tool_handler("shell", handler)
    run = EvolvingAgenticRun(
        loop, planner=_Planner([PlanStep("do ls", "", "shell", {"argv": ["ls"]})]),
        scorer=_Scorer("M2"))
    res = run.execute("run ls", project_id, approve=lambda step, dec: True)
    assert res.decision == "executed"
    assert handler.calls == ["do ls"]
    assert res.final_status["complete"] is True


def test_execute_pauses_when_not_approved(loop, project_id):
    loop.register_tool_handler("shell", _RecordingHandler())
    run = EvolvingAgenticRun(
        loop, planner=_Planner([PlanStep("do ls", "", "shell", {"argv": ["ls"]})]),
        scorer=_Scorer("M2"))
    # default approve=None → consequential steps are held
    res = run.execute("run ls", project_id)
    assert res.decision == "paused_for_review"


def test_execute_self_mod_step_is_held_even_when_approve_says_yes(loop, project_id):
    """A self-modifying step must reach the human; here approve() would say yes
    for normal steps, but the policy flags modifies_self so the command layer is
    expected to still prompt. We assert the policy decision carries the self-mod
    reason so the CLI can refuse to batch-approve it."""
    loop.register_tool_handler("file_write", _RecordingHandler())
    seen = {}

    def approve(step, dec):
        seen["reason"] = dec.reason
        seen["requires_human"] = dec.requires_human
        return False  # human declines the self-mod

    run = EvolvingAgenticRun(
        loop,
        planner=_Planner([PlanStep("edit core", "", "file_write",
                                   {"path": "src/sovereign_agent/core/x.py",
                                    "content": "x"})]),
        scorer=_Scorer("M2"))
    res = run.execute("change yourself", project_id, approve=approve)
    assert res.decision == "paused_for_review"
    assert "code or configuration" in seen["reason"]
    assert seen["requires_human"] is True


def test_m1_writes_plan_without_executing(loop, project_id):
    handler = _RecordingHandler()
    loop.register_tool_handler("shell", handler)
    run = EvolvingAgenticRun(
        loop, planner=_Planner([PlanStep("do ls", "", "shell", {"argv": ["ls"]})]),
        scorer=_Scorer("M1"))
    res = run.execute("vague thing", project_id, approve=lambda s, d: True)
    assert res.decision == "paused_for_review"
    assert handler.calls == []              # M1 never executes


def test_task_to_step_roundtrip(loop, project_id):
    wid = loop.intake(project_id, "g")
    loop.write_plan(wid, [PlanStep("s1", "desc", "shell", {"argv": ["ls"]}, 3)])
    task = loop.next_planned_step(wid)
    step = _task_to_step(task)
    assert step.action_kind == "shell"
    assert step.action_input == {"argv": ["ls"]}
