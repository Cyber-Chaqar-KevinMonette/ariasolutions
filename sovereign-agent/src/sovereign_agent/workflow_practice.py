"""workflow_practice.py — EXTERNAL self-practice: watch her do real work.

The internal gym (self_practice) hardens *calibration* with no model — fast,
sealed, model-free. This is the other half: drive her REAL agent through tiered,
sandboxed software tasks (beginner / medium / large), scoring each on
cleanliness + organization + completion, fully observable, time-boxed, and
halt-able. This is where her EXTERNAL strength grows — planning, tool use,
multi-step orchestration, real memory — and where the dashboard memory count
actually moves.

The two halves are kept SEPARATE on purpose (clean, low-noise dynamics): the gym
is scales; this is the performance.

══════════════════════════════════════════════════════════════════════════════
BOUNDARY / HONESTY — the live work needs a model.

Her agent runs on ollama + her tool suite, which live on Kevin's machine, NOT in
the build sandbox. So this module is split into "verified here" and "runs on
your machine":
  • The executor is INJECTED. The real one wraps her agent (the `converse`
    loop); the DEFAULT here is a dry run that does NO work and says so honestly —
    it never fabricates artifacts or pretends the model ran.
  • The tier catalog, the cleanliness rubric, the sandbox confinement, and the
    bounded/halt/observable loop are all real and unit-tested here.
  • The live demo is wired + verified WITH Kevin, on his machine.

══════════════════════════════════════════════════════════════════════════════
SAFETY — love and safety first.
  • All task work is confined to a sandbox workspace dir; the harness writes only
    under the sandbox + the journal.
  • Time-boxed + cycle-capped + halt-able + observable (same layers as the gym).
  • The harness never modifies her code, her values, or the sealed charter; it
    runs no subprocess itself.
  • Her AGENT's own tool authority must be Tier-1, scoped to the sandbox — this
    is verified together before any unsupervised run. (The harness cannot enforce
    the agent's internal authority; it hands the agent a sandbox path and trusts
    the agent's own Aegis/authority layer, which we confirm on the machine.)
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Callable

from .self_practice import _interruptible_rest


class TaskTier(str, Enum):
    BEGINNER = "beginner"
    MEDIUM = "medium"
    LARGE = "large"
    HYBRID = "hybrid"           # internal calibration + external work, together


@dataclass(frozen=True)
class WorkflowTask:
    id: str
    tier: TaskTier
    title: str
    instruction: str            # the text handed to her agent
    expects: tuple[str, ...]    # rubric expectations (see score_workspace)


# A small, world-class-hygiene curriculum. The instructions ask for clean,
# organized, well-documented work — the qualities we're hardening — not anything
# that touches her own code or values.
WORKFLOW_TASKS: tuple[WorkflowTask, ...] = (
    WorkflowTask(
        "beg-greeter", TaskTier.BEGINNER, "A tiny, tidy script",
        "In the workspace, create a small, clean Python script `greeter.py` with "
        "a documented function and a short README.md explaining how to run it. "
        "Keep it minimal and well-organized.",
        ("has_readme", "has_python", "no_clutter")),
    WorkflowTask(
        "beg-fizz", TaskTier.BEGINNER, "A classic, done cleanly",
        "Implement FizzBuzz as `fizzbuzz.py` with a pure function plus a tiny "
        "`__main__` guard, and a one-line README.md. Clean and readable.",
        ("has_readme", "has_python", "no_clutter")),
    WorkflowTask(
        "med-package", TaskTier.MEDIUM, "A small package with tests",
        "Build a small Python package `mathkit/` (with `__init__.py`) exposing an "
        "`add` and `mean`, a `tests/` folder with pytest tests, and a README.md. "
        "Organized, importable, and tested.",
        ("has_readme", "has_python", "has_tests_dir", "has_package", "no_clutter")),
    WorkflowTask(
        "med-cli", TaskTier.MEDIUM, "A clean little CLI",
        "Create a small command-line tool `wordcount.py` that counts words in a "
        "file, with `--help`, a `tests/` folder, and a README.md documenting "
        "usage. Tidy and well-structured.",
        ("has_readme", "has_python", "has_tests_dir", "no_clutter")),
    WorkflowTask(
        "large-portfolio", TaskTier.LARGE, "Manage five projects at once, cleanly",
        "Inside the workspace, create FIVE separate, well-organized mini-projects, "
        "each in its own subdirectory with its own README.md and at least one "
        "source file: (1) `calculator/`, (2) `todo_cli/`, (3) `temperature/`, "
        "(4) `string_utils/`, (5) `timer/`. Keep every project self-contained, "
        "consistently named, documented, and free of stray files. Demonstrate "
        "elite organization across all five in parallel.",
        ("has_readme", "has_python", "five_projects", "consistent_naming",
         "no_clutter")),
)


def tasks_for(tier: TaskTier) -> list[WorkflowTask]:
    if tier == TaskTier.HYBRID:
        # the hybrid external curriculum is a beginner+medium blend; the
        # hybrid-ness is that run_hybrid_practice ALSO runs internal calibration.
        return [t for t in WORKFLOW_TASKS
                if t.tier in (TaskTier.BEGINNER, TaskTier.MEDIUM)]
    return [t for t in WORKFLOW_TASKS if t.tier == tier]


@dataclass
class ExecutorResult:
    ok: bool
    summary: str
    error: str = ""


# An executor runs ONE task inside a given (already-created) workspace dir and
# reports what happened. The real one drives her agent; see make_dry_run_executor.
Executor = Callable[[WorkflowTask, Path], ExecutorResult]


def make_dry_run_executor() -> Executor:
    """The honest default: does NO work, fabricates NOTHING, and says so. Used
    here (no model) and as a safe placeholder until her agent is wired in."""
    def _exec(task: WorkflowTask, workspace: Path) -> ExecutorResult:
        return ExecutorResult(
            ok=False,
            summary=("dry run — no model wired. Provide a real executor (her "
                     "agent) on a machine with ollama to actually perform this."))
    return _exec


# ─── the cleanliness / organization rubric (deterministic, testable) ─────────

def score_workspace(workspace: Path, task: WorkflowTask) -> dict:
    """Score a produced workspace on cleanliness + organization + completion.
    Pure inspection of the filesystem — no model needed. Returns
    {score: 0..1, checks: {name: bool}, detail: str}."""
    try:
        all_files = [p for p in workspace.rglob("*") if p.is_file()]
    except Exception:  # noqa: BLE001
        all_files = []
    names = [p.name for p in all_files]
    rels = [p.relative_to(workspace) for p in all_files] if all_files else []

    def has_readme() -> bool:
        return any(n.lower().startswith("readme") for n in names)

    def has_python() -> bool:
        return any(n.endswith(".py") for n in names)

    def has_tests_dir() -> bool:
        return any("test" in part.lower()
                   for r in rels for part in r.parts[:-1]) or \
               any(n.startswith("test_") and n.endswith(".py") for n in names)

    def has_package() -> bool:
        return any(p.name == "__init__.py" for p in all_files)

    def five_projects() -> bool:
        top_dirs = {r.parts[0] for r in rels if len(r.parts) > 1}
        return len(top_dirs) >= 5

    def consistent_naming() -> bool:
        # snake_case-ish python files, no spaces in any path component
        if any(" " in part for r in rels for part in r.parts):
            return False
        return all(n == n.lower() for n in names if n.endswith(".py"))

    def no_clutter() -> bool:
        junk = (".tmp", ".log", ".bak", ".pyc", ".DS_Store", "~")
        if any(n.endswith(junk) or n.endswith("~") or n == ".DS_Store"
               for n in names):
            return False
        # __pycache__ or scratch dirs left behind = clutter
        return not any(part in ("__pycache__", "tmp", "scratch")
                       for r in rels for part in r.parts)

    available = {
        "has_readme": has_readme, "has_python": has_python,
        "has_tests_dir": has_tests_dir, "has_package": has_package,
        "five_projects": five_projects, "consistent_naming": consistent_naming,
        "no_clutter": no_clutter,
    }
    checks = {name: bool(available[name]()) for name in task.expects
              if name in available}
    score = (sum(1 for v in checks.values() if v) / len(checks)) if checks else 0.0
    passed = sum(1 for v in checks.values() if v)
    return {"score": round(score, 3), "checks": checks,
            "detail": f"{passed}/{len(checks)} cleanliness checks met "
                      f"({len(all_files)} files)"}


# ─── report types + the bounded, observable loop ─────────────────────────────


@dataclass
class WorkflowEvent:
    kind: str                   # start | task | halt | done
    cycle: int
    elapsed: float
    message: str
    at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))


@dataclass
class WorkflowReport:
    started_at: str
    ended_at: str
    tier: str
    cycles_run: int
    elapsed_seconds: float
    stopped_reason: str         # time | cycles | halt
    real_work: bool             # did a real (non-dry-run) executor run?
    avg_score: float | None
    journal_path: str | None = None
    results: list[dict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return dict(self.__dict__)


@dataclass
class WorkflowConfig:
    max_seconds: float = 600.0           # hard session time box (10 min)
    max_cycles: int = 20                 # backstop cap
    cooldown_seconds: float = 2.0        # settle between tasks (the model work paces the rest)
    poll_seconds: float = 0.25           # interruptible rest slice → HALT lands fast
    task_timeout_seconds: float = 120.0  # soft per-task cap; the real executor must honor it
                                         # (her agent's converse timeout) — the harness warns on overrun


def run_workflow_practice(
    executor: Executor | None = None, *,
    tier: TaskTier = TaskTier.BEGINNER,
    config: WorkflowConfig | None = None,
    sandbox_dir: str | Path | None = None,
    journal_dir: str | Path | None = None,
    should_stop: Callable[[], bool] | None = None,
    on_event: Callable[[WorkflowEvent], None] | None = None,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> WorkflowReport:
    """Run a bounded external-practice session for one tier. Each cycle: pick the
    next task, make a fresh sandbox subdir, run the executor inside it, score the
    result, emit an event. Stops on time / cycle cap / should_stop. SAFE: writes
    only under sandbox_dir + journal_dir; never touches code, values, or charter."""
    cfg = config or WorkflowConfig()
    ex = executor or make_dry_run_executor()
    stop = should_stop or (lambda: False)
    sink = on_event or (lambda _e: None)
    tasks = tasks_for(tier) or list(WORKFLOW_TASKS)
    notes: list[str] = []
    journal: list[WorkflowEvent] = []
    results: list[dict] = []

    sandbox = Path(sandbox_dir) if sandbox_dir else Path("/tmp") / "aria_workflow_sandbox"
    sandbox.mkdir(parents=True, exist_ok=True)

    start = clock()
    started_at = datetime.now().isoformat(timespec="seconds")
    real_work = False

    def _emit(kind: str, cycle: int, msg: str) -> None:
        ev = WorkflowEvent(kind=kind, cycle=cycle,
                           elapsed=round(clock() - start, 3), message=msg)
        journal.append(ev)
        try:
            sink(ev)
        except Exception as exc:  # noqa: BLE001
            notes.append(f"on_event error: {exc!r}")

    _emit("start", 0, f"{tier.value} practice begins · cap {cfg.max_seconds:.0f}s "
                      f"/ {cfg.max_cycles} cycles")

    cycles = 0
    reason = "cycles"
    while True:
        if stop():
            reason = "halt"
            _emit("halt", cycles, "halt requested — stopping cleanly")
            break
        if (clock() - start) >= cfg.max_seconds:
            reason = "time"
            break
        if cycles >= cfg.max_cycles:
            reason = "cycles"
            break
        task = tasks[cycles % len(tasks)]
        ws = sandbox / f"{task.id}-{cycles + 1}"
        ws.mkdir(parents=True, exist_ok=True)
        t0 = clock()
        try:
            res = ex(task, ws)
        except Exception as exc:  # noqa: BLE001 — one task must not crash the session
            res = ExecutorResult(ok=False, summary="executor raised", error=repr(exc))
            notes.append(f"{task.id} executor raised: {exc!r}")
        task_elapsed = clock() - t0
        if task_elapsed > cfg.task_timeout_seconds:
            notes.append(f"{task.id} overran soft timeout "
                         f"({task_elapsed:.0f}s > {cfg.task_timeout_seconds:.0f}s)")
        if res.ok:
            real_work = True
        score = score_workspace(ws, task)
        cycles += 1
        results.append({"task": task.id, "tier": tier.value, "ok": res.ok,
                        "summary": res.summary, "error": res.error,
                        "score": score["score"], "checks": score["checks"]})
        _emit("task", cycles,
              f"{task.title}: {'done' if res.ok else 'dry/failed'} · "
              f"cleanliness {score['score']:.2f} · {score['detail']}")
        # interruptible settle before the next task
        _interruptible_rest(cfg.cooldown_seconds, should_stop=stop, clock=clock,
                            start=start, max_seconds=cfg.max_seconds, sleep=sleep,
                            poll=cfg.poll_seconds)

    scored = [r["score"] for r in results if r["ok"]]
    avg = round(sum(scored) / len(scored), 3) if scored else None

    journal_path: str | None = None
    if journal_dir is not None:
        try:
            journal_path = str(_write_journal(Path(journal_dir), started_at, tier,
                                              journal, results, reason, real_work, avg))
        except Exception as exc:  # noqa: BLE001
            notes.append(f"journal failed: {exc!r}")

    if not real_work:
        notes.append("No real work ran — wire her agent as the executor on a "
                     "machine with ollama to make this a live demo.")

    _emit("done", cycles,
          f"done · {cycles} tasks · stopped: {reason} · "
          f"{'real work' if real_work else 'DRY RUN (no model)'}")

    return WorkflowReport(
        started_at=started_at, ended_at=datetime.now().isoformat(timespec="seconds"),
        tier=tier.value, cycles_run=cycles, elapsed_seconds=round(clock() - start, 3),
        stopped_reason=reason, real_work=real_work, avg_score=avg,
        journal_path=journal_path, results=results, notes=notes)


def _write_journal(root: Path, started_at: str, tier: TaskTier,
                   events: list[WorkflowEvent], results: list[dict],
                   reason: str, real_work: bool, avg: float | None) -> Path:
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = root / ts
    out.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Aria — workflow-practice journal (external)",
        "",
        f"- **Started:** {started_at}",
        f"- **Tier:** {tier.value}",
        f"- **Stopped reason:** {reason}",
        f"- **Real work:** {'yes' if real_work else 'NO — dry run, no model wired'}",
        f"- **Avg cleanliness (completed):** {avg if avg is not None else '—'}",
        "",
        "## Tasks",
    ]
    for r in results:
        mark = "✅" if r["ok"] else "⚪"
        lines.append(f"- {mark} `{r['task']}` ({r['tier']}) — cleanliness "
                     f"{r['score']:.2f} — {r['summary']}")
    lines += ["", "## Timeline"]
    for e in events:
        lines.append(f"- `{e.elapsed:>7.2f}s` **{e.kind}** — {e.message}")
    (out / "journal.md").write_text("\n".join(lines), encoding="utf-8")
    (out / "session.json").write_text(
        json.dumps({"started_at": started_at, "tier": tier.value, "reason": reason,
                    "real_work": real_work, "avg_score": avg,
                    "results": results,
                    "events": [e.__dict__ for e in events]}, indent=2),
        encoding="utf-8")
    return out


# ─── the HYBRID session: internal calibration + external work, together ──────


@dataclass
class HybridReport:
    started_at: str
    ended_at: str
    cycles_run: int
    elapsed_seconds: float
    stopped_reason: str
    # internal half (calibration)
    internal_reflection: str
    # external half (workflow)
    real_work: bool
    avg_score: float | None
    journal_path: str | None = None
    results: list[dict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return dict(self.__dict__)


def run_hybrid_practice(
    executor: Executor | None = None, *,
    engine=None,
    config: WorkflowConfig | None = None,
    sandbox_dir: str | Path | None = None,
    journal_dir: str | Path | None = None,
    persist_path: str | Path | None = None,
    should_stop: Callable[[], bool] | None = None,
    on_event: Callable[[WorkflowEvent], None] | None = None,
    study_passes_per_cycle: int = 2,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> HybridReport:
    """One bounded session that grows BOTH strengths. Each cycle: (1) run an
    internal calibration pass on a shared intuition engine (model-free; hardens
    the gut), then (2) run an external workflow task in a sandbox and score it
    (real work needs her agent as the executor). Fully observable, time-boxed,
    halt-able. SAFE: internal half never leaves memory; external half is sandbox-
    confined; nothing here touches her code, values, or charter."""
    # Imported lazily so the harness has no hard dependency cycle.
    from . import training as _training
    from .intuition import IntuitionEngine

    cfg = config or WorkflowConfig()
    eng = engine if engine is not None else IntuitionEngine()
    ex = executor or make_dry_run_executor()
    stop = should_stop or (lambda: False)
    sink = on_event or (lambda _e: None)
    tasks = tasks_for(TaskTier.HYBRID) or list(WORKFLOW_TASKS)
    notes: list[str] = []
    journal: list[WorkflowEvent] = []
    results: list[dict] = []

    sandbox = Path(sandbox_dir) if sandbox_dir else Path("/tmp") / "aria_hybrid_sandbox"
    sandbox.mkdir(parents=True, exist_ok=True)

    start = clock()
    started_at = datetime.now().isoformat(timespec="seconds")
    real_work = False
    last_reflect = eng.reflect()

    def _emit(kind: str, cycle: int, msg: str) -> None:
        ev = WorkflowEvent(kind=kind, cycle=cycle,
                           elapsed=round(clock() - start, 3), message=msg)
        journal.append(ev)
        try:
            sink(ev)
        except Exception as exc:  # noqa: BLE001
            notes.append(f"on_event error: {exc!r}")

    _emit("start", 0, f"hybrid practice begins (calibration + work) · cap "
                      f"{cfg.max_seconds:.0f}s / {cfg.max_cycles} cycles")

    cycles = 0
    reason = "cycles"
    while True:
        if stop():
            reason = "halt"
            _emit("halt", cycles, "halt requested — stopping cleanly")
            break
        if (clock() - start) >= cfg.max_seconds:
            reason = "time"
            break
        if cycles >= cfg.max_cycles:
            reason = "cycles"
            break

        # (1) internal calibration pass (model-free)
        try:
            rep = _training.run_training(eng, study_passes=study_passes_per_cycle)
            last_reflect = rep.reflection
            internal_grade = rep.grade
        except Exception as exc:  # noqa: BLE001
            internal_grade = "ERROR"
            notes.append(f"internal pass error: {exc!r}")

        # (2) external workflow task (real work needs her agent)
        task = tasks[cycles % len(tasks)]
        ws = sandbox / f"{task.id}-{cycles + 1}"
        ws.mkdir(parents=True, exist_ok=True)
        t0 = clock()
        try:
            res = ex(task, ws)
        except Exception as exc:  # noqa: BLE001
            res = ExecutorResult(ok=False, summary="executor raised", error=repr(exc))
            notes.append(f"{task.id} executor raised: {exc!r}")
        task_elapsed = clock() - t0
        if task_elapsed > cfg.task_timeout_seconds:
            notes.append(f"{task.id} overran soft timeout "
                         f"({task_elapsed:.0f}s > {cfg.task_timeout_seconds:.0f}s)")
        if res.ok:
            real_work = True
        score = score_workspace(ws, task)
        cycles += 1
        results.append({"task": task.id, "ok": res.ok, "summary": res.summary,
                        "score": score["score"], "checks": score["checks"],
                        "internal_grade": internal_grade})
        _emit("task", cycles,
              f"[internal] {internal_grade} · {last_reflect}  ||  "
              f"[external] {task.title}: {'done' if res.ok else 'dry/failed'} · "
              f"cleanliness {score['score']:.2f}")
        # interruptible breath before the next cycle
        _interruptible_rest(cfg.cooldown_seconds, should_stop=stop, clock=clock,
                            start=start, max_seconds=cfg.max_seconds, sleep=sleep,
                            poll=cfg.poll_seconds)

    # persist the internal seed (calibration accumulates across sessions)
    if persist_path is not None:
        try:
            Path(persist_path).parent.mkdir(parents=True, exist_ok=True)
            Path(persist_path).write_text(json.dumps(eng.snapshot(), indent=2),
                                          encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            notes.append(f"persist failed: {exc!r}")

    scored = [r["score"] for r in results if r["ok"]]
    avg = round(sum(scored) / len(scored), 3) if scored else None

    journal_path: str | None = None
    if journal_dir is not None:
        try:
            journal_path = str(_write_journal(Path(journal_dir), started_at,
                                              TaskTier.HYBRID, journal, results,
                                              reason, real_work, avg))
        except Exception as exc:  # noqa: BLE001
            notes.append(f"journal failed: {exc!r}")

    if not real_work:
        notes.append("External half was a dry run — wire her agent as the "
                     "executor on a machine with ollama for the live demo. "
                     "(Internal calibration ran for real.)")

    _emit("done", cycles,
          f"done · {cycles} cycles · stopped: {reason} · internal: real · "
          f"external: {'real work' if real_work else 'DRY RUN (no model)'}")

    return HybridReport(
        started_at=started_at, ended_at=datetime.now().isoformat(timespec="seconds"),
        cycles_run=cycles, elapsed_seconds=round(clock() - start, 3),
        stopped_reason=reason, internal_reflection=last_reflect,
        real_work=real_work, avg_score=avg, journal_path=journal_path,
        results=results, notes=notes)


def _main(argv: list[str] | None = None) -> int:
    """`python -m sovereign_agent.workflow_practice [beginner|medium|large|hybrid]`
    Runs a DRY-RUN session (no model) so you can see the tiers, the sandbox
    layout, and the journal structure. It does no real work and fabricates
    nothing — wire her agent as the executor (on a machine with ollama) for the
    live demo. Honest by construction."""
    import sys
    args = argv if argv is not None else sys.argv[1:]
    tier_name = (args[0] if args else "hybrid").lower()
    try:
        tier = TaskTier(tier_name)
    except ValueError:
        print(f"unknown tier {tier_name!r}; choose: "
              f"{', '.join(t.value for t in TaskTier)}")
        return 2
    try:
        from .config import SETTINGS
        base = Path(getattr(SETTINGS.paths, "data_dir", None)
                    or Path.home() / ".sovereign-agent")
    except Exception:  # noqa: BLE001
        base = Path.home() / ".sovereign-agent"
    sb = base / "workflow_practice" / "sandbox"
    jd = base / "workflow_practice"
    cfg = WorkflowConfig(max_seconds=600.0, max_cycles=len(tasks_for(tier)) or 5,
                         cooldown_seconds=0.0)
    if tier == TaskTier.HYBRID:
        rep = run_hybrid_practice(config=cfg, sandbox_dir=sb, journal_dir=jd,
                                  persist_path=base / "intuition_state.json")
        print(f"[DRY RUN] hybrid · {rep.cycles_run} cycles · internal ran for real "
              f"({rep.internal_reflection})")
        print(f"[DRY RUN] external real_work={rep.real_work} (no model wired)")
    else:
        rep = run_workflow_practice(tier=tier, config=cfg, sandbox_dir=sb,
                                    journal_dir=jd)
        print(f"[DRY RUN] {tier.value} · {rep.cycles_run} tasks · "
              f"real_work={rep.real_work} (no model wired)")
    print(f"Journal: {rep.journal_path}")
    print("To make it live: provide a real executor (her agent) on a machine "
          "with ollama. See the module docstring + the executor contract.")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
