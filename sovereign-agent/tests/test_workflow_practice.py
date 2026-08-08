"""Tests for the external workflow-practice harness — rubric correctness,
sandbox confinement, boundedness/halt, and honest dry-run behavior."""
from __future__ import annotations

from pathlib import Path

from sovereign_agent import workflow_practice as wp
from sovereign_agent.workflow_practice import (
    ExecutorResult,
    TaskTier,
    WorkflowConfig,
    WorkflowTask,
)


class _Clock:
    def __init__(self, step: float = 0.0):
        self.t = 0.0
        self.step = step

    def __call__(self) -> float:
        v = self.t
        self.t += self.step
        return v


# ─── tiers ───────────────────────────────────────────────────────────────────


def test_each_tier_has_tasks():
    for tier in (TaskTier.BEGINNER, TaskTier.MEDIUM, TaskTier.LARGE):
        assert wp.tasks_for(tier), f"{tier} should have at least one task"
    big = [t for t in wp.tasks_for(TaskTier.LARGE) if "five_projects" in t.expects]
    assert big, "large tier should include the manage-five-projects task"


# ─── the rubric (deterministic) ───────────────────────────────────────────────


def test_rubric_rewards_clean_and_punishes_messy(tmp_path):
    task = WorkflowTask("t", TaskTier.MEDIUM, "x", "x",
                        ("has_readme", "has_python", "has_tests_dir", "no_clutter"))
    clean = tmp_path / "clean"
    (clean / "tests").mkdir(parents=True)
    (clean / "README.md").write_text("# hi", encoding="utf-8")
    (clean / "app.py").write_text("def f(): return 1\n", encoding="utf-8")
    (clean / "tests" / "test_app.py").write_text("def test_f(): assert True\n", encoding="utf-8")
    good = wp.score_workspace(clean, task)
    assert good["score"] == 1.0
    assert all(good["checks"].values())

    messy = tmp_path / "messy"
    messy.mkdir()
    (messy / "scratch.tmp").write_text("junk", encoding="utf-8")    # clutter, no readme/py/tests
    bad = wp.score_workspace(messy, task)
    assert bad["score"] < 0.5
    assert bad["checks"]["no_clutter"] is False


def test_rubric_five_projects_check(tmp_path):
    task = WorkflowTask("t", TaskTier.LARGE, "x", "x", ("five_projects",))
    for name in ("calculator", "todo_cli", "temperature", "string_utils", "timer"):
        d = tmp_path / name
        d.mkdir()
        (d / "main.py").write_text("x=1\n", encoding="utf-8")
    assert wp.score_workspace(tmp_path, task)["checks"]["five_projects"] is True


# ─── the loop: bounded, halt-able, observable ─────────────────────────────────


def test_loop_bounded_by_cycles(tmp_path):
    cfg = WorkflowConfig(max_seconds=10_000, max_cycles=3, cooldown_seconds=0.0)
    rep = wp.run_workflow_practice(config=cfg, sandbox_dir=tmp_path,
                                   clock=_Clock(step=0.0))
    assert rep.cycles_run == 3
    assert rep.stopped_reason == "cycles"


def test_loop_halts_when_asked(tmp_path):
    calls = {"n": 0}

    def stop():
        calls["n"] += 1
        return calls["n"] > 2

    cfg = WorkflowConfig(max_seconds=10_000, max_cycles=999, cooldown_seconds=0.0)
    rep = wp.run_workflow_practice(config=cfg, sandbox_dir=tmp_path,
                                   should_stop=stop, clock=_Clock())
    assert rep.stopped_reason == "halt"
    assert rep.cycles_run <= 3


def test_loop_emits_events(tmp_path):
    events: list[wp.WorkflowEvent] = []
    cfg = WorkflowConfig(max_seconds=10_000, max_cycles=2, cooldown_seconds=0.0)
    wp.run_workflow_practice(config=cfg, sandbox_dir=tmp_path,
                             on_event=events.append, clock=_Clock())
    kinds = [e.kind for e in events]
    assert kinds[0] == "start" and kinds[-1] == "done"
    assert kinds.count("task") == 2


# ─── honesty: dry run does no work and says so ────────────────────────────────


def test_dry_run_is_honest_and_makes_no_artifacts(tmp_path):
    cfg = WorkflowConfig(max_seconds=10_000, max_cycles=2, cooldown_seconds=0.0)
    rep = wp.run_workflow_practice(config=cfg, sandbox_dir=tmp_path, clock=_Clock())
    assert rep.real_work is False
    assert any("wire her agent" in n for n in rep.notes)
    # the dry-run executor must not fabricate any files
    created = [p for p in tmp_path.rglob("*") if p.is_file()]
    assert created == [], "dry run must not create fake artifacts"


def test_real_executor_marks_real_work(tmp_path):
    def fake_agent(task, workspace: Path) -> ExecutorResult:
        # stand-in for her agent: actually produce a clean artifact
        (workspace / "README.md").write_text("# done", encoding="utf-8")
        (workspace / "greeter.py").write_text("def hi(): return 'hi'\n", encoding="utf-8")
        return ExecutorResult(ok=True, summary="created greeter.py + README")

    cfg = WorkflowConfig(max_seconds=10_000, max_cycles=2, cooldown_seconds=0.0)
    rep = wp.run_workflow_practice(fake_agent, tier=TaskTier.BEGINNER,
                                   config=cfg, sandbox_dir=tmp_path, clock=_Clock())
    assert rep.real_work is True
    assert rep.avg_score is not None and rep.avg_score > 0.0


# ─── safety: never mutates doctrine ───────────────────────────────────────────


def test_practice_never_mutates_doctrine(tmp_path):
    from sovereign_agent import mos_canon as mc
    before = len(mc.ALL_CLAUSES)
    cfg = WorkflowConfig(max_seconds=10_000, max_cycles=3, cooldown_seconds=0.0)
    wp.run_workflow_practice(config=cfg, sandbox_dir=tmp_path, clock=_Clock())
    assert len(mc.ALL_CLAUSES) == before


def test_journal_written(tmp_path):
    cfg = WorkflowConfig(max_seconds=10_000, max_cycles=2, cooldown_seconds=0.0)
    rep = wp.run_workflow_practice(config=cfg, sandbox_dir=tmp_path / "sb",
                                   journal_dir=tmp_path / "journal", clock=_Clock())
    assert rep.journal_path is not None
    assert (Path(rep.journal_path) / "journal.md").exists()


# ─── hybrid tier: internal calibration + external work, together ──────────────


def test_hybrid_tier_blends_tasks():
    blend = wp.tasks_for(TaskTier.HYBRID)
    tiers = {t.tier for t in blend}
    assert TaskTier.BEGINNER in tiers and TaskTier.MEDIUM in tiers


def test_hybrid_grows_internal_and_runs_external(tmp_path):
    from sovereign_agent.intuition import IntuitionEngine

    def fake_agent(task, workspace: Path) -> ExecutorResult:
        (workspace / "README.md").write_text("# x", encoding="utf-8")
        (workspace / "main.py").write_text("x=1\n", encoding="utf-8")
        return ExecutorResult(ok=True, summary="built it")

    eng = IntuitionEngine()
    cfg = WorkflowConfig(max_seconds=10_000, max_cycles=4, cooldown_seconds=0.0)
    rep = wp.run_hybrid_practice(fake_agent, engine=eng, config=cfg,
                                 sandbox_dir=tmp_path, clock=_Clock())
    # internal half hardened calibration
    assert any(d["reps"] >= 4 for d in eng.domain_report())
    assert "domains tracked" in rep.internal_reflection
    # external half did real work and was scored
    assert rep.real_work is True
    assert rep.avg_score is not None and rep.avg_score > 0.0


def test_hybrid_dry_run_still_calibrates_but_flags_no_model(tmp_path):
    rep = wp.run_hybrid_practice(config=WorkflowConfig(max_seconds=10_000, max_cycles=3, cooldown_seconds=0.0),
                                 sandbox_dir=tmp_path, clock=_Clock())
    assert rep.real_work is False                       # external honestly dry
    assert "domains tracked" in rep.internal_reflection  # internal still ran for real
    assert any("ollama" in n for n in rep.notes)


def test_hybrid_halts_and_is_bounded(tmp_path):
    calls = {"n": 0}

    def stop():
        calls["n"] += 1
        return calls["n"] > 2

    rep = wp.run_hybrid_practice(config=WorkflowConfig(max_seconds=10_000, max_cycles=999, cooldown_seconds=0.0),
                                 sandbox_dir=tmp_path, should_stop=stop, clock=_Clock())
    assert rep.stopped_reason == "halt"
    assert rep.cycles_run <= 3
