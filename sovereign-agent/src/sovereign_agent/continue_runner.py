"""
╔══════════════════════════════════════════════════════════════════════════╗
║  continue_runner.py — Re-trigger executor                                ║
║  Architecture §13 (new in v0.2.5)                                        ║
╚══════════════════════════════════════════════════════════════════════════╝

One ``sovereign continue <task_id>`` invocation does exactly this:

    1. Acquire exclusive lock on the continuation
    2. Read the continuation's next pending step
    3. Render it into a goal string via the planner
    4. Run agent_loop(goal, mode=ONESHOT, budget=<small>)
    5. Update the step's status from the LoopResult
    6. Recompute continuation.status
    7. Release lock and exit

The model only sees ONE step's worth of context per invocation. Memory
across invocations is durable: events.jsonl, atoms.db, lessons. The
continuation file remembers the cursor position.

This module does NOT loop. The driver (cron, systemd timer, or the
shipped ``sovereign-continue-loop.sh`` script) is responsible for repeated
invocation. That separation is intentional — it lets the OS manage the
process lifecycle, which is much more robust than a Python while-loop
trying to be its own scheduler.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

from .config import SETTINGS
from .continuation import (
    Continuation,
    ContinuationLocked,
    ContinuationNotFound,
    ContinuationStore,
    Step,
)
from .events import emit_event
from .modes import Mode, RunBudget
from .planners import get_planner
from .planners.base import Planner


@dataclass
class StepRunResult:
    """Outcome of running a single continuation step."""

    task_id: str
    step_id: int
    step_kind: str
    outcome: str                # "complete" | "budget" | "poison" | "halted" | "drained" | "locked" | "no_step" | "filtered" | "paused"
    iterations: int = 0
    tokens: int = 0
    elapsed_seconds: float = 0.0   # v0.2.7+
    final_message: str | None = None
    cont_status: str = ""       # status of the parent continuation after this step
    progress: tuple[int, int] = (0, 0)
    required_model: str = ""    # v0.2.7+ — surfaces in CLI output
    # v0.2.11+ — VRAM trace per step. None on systems without a GPU.
    vram_before_mb: int | None = None
    vram_peak_mb: int | None = None
    vram_after_mb: int | None = None


# Default per-step budget. Generous on iterations (a step might require
# 2-3 tool calls), tight on wall-time so a hung step doesn't block the
# driver loop forever. Override per-invocation via run_one_step(budget=…).
DEFAULT_STEP_BUDGET = RunBudget(
    max_iterations=5,
    max_wall_seconds=120,
    max_tokens=20_000,
    consecutive_fail_limit=2,
)


def _bind_step_to_loop_result(
    step: Step, loop_result, *, planner: Planner, planner_args: dict
) -> None:
    """Mutate ``step`` to reflect the loop's outcome.

    Maps loop reasons to step statuses:
      complete → done
      poison   → poisoned
      budget   → poisoned (we treat budget-exhaustion as poisoning the step;
                 the operator can replan a smaller version)
      halted   → leave as pending; the operator should disarm and retry
    """
    step.iterations = loop_result.iterations
    step.tokens = loop_result.tokens_used
    step.completed_at = _utc_now()

    if loop_result.reason == "complete":
        step.status = "done"
        step.result = (loop_result.final_message or "")[:500] or None
    elif loop_result.reason == "poison":
        step.status = "poisoned"
        step.error = (loop_result.final_message or "poison")[:500]
    elif loop_result.reason == "budget":
        step.status = "poisoned"
        step.error = "budget exhausted on step"
    elif loop_result.reason == "halted":
        # Roll back: the step did not get a fair shot.
        step.status = "pending"
        step.completed_at = None
    else:
        step.status = "poisoned"
        step.error = f"unknown loop outcome: {loop_result.reason!r}"


def _utc_now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _resolve_model_name(required_model: str) -> str:
    """Map a Step.required_model identifier to an actual configured model name.

    The identifier is an architectural label (orchestrator, coder, vision,
    fast). The resolved name is whatever's in SETTINGS — controllable via
    env vars at the operator level.

    Falls back to orchestrator if the identifier is unknown — keeps the
    runner from crashing on a typo'd planner. The mismatch is loud enough
    that the operator will see it in the doctor's diagnostic output.
    """
    mapping = {
        "orchestrator": SETTINGS.orchestrator_model,
        "coder": SETTINGS.coder_model,
        "fast": SETTINGS.fast_model,
        "reflector": SETTINGS.reflector_model,
        "vision": getattr(SETTINGS, "vision_model", None) or "llava:7b",
    }
    return mapping.get(required_model) or SETTINGS.orchestrator_model


class _PseudoLoopResult:
    """LoopResult-shaped object for the no-model execution path.

    The runner expects loop_result to have ``reason``, ``iterations``,
    ``tokens_used``, and ``final_message``. For pure-Python steps we
    fabricate these so the rest of the binding logic stays uniform.
    """

    def __init__(self, *, reason: str, final_message: str | None = None):
        self.reason = reason
        self.iterations = 1
        self.tokens_used = 0
        self.final_message = final_message
        self.ok = reason == "complete"
        self.lesson_id = None


def _execute_no_model_step(step) -> _PseudoLoopResult:
    """Execute a step with required_model='none' using its planner's
    no-model executor. Currently metadata-inventory and palace-mine ship
    such steps. To add another no-model planner: add its (kind, executor)
    pair to _NO_MODEL_DISPATCH below.
    """
    executor = _NO_MODEL_DISPATCH.get(step.kind)
    if executor is None:
        return _PseudoLoopResult(
            reason="poison",
            final_message=f"unknown no-model step kind: {step.kind!r}",
        )
    try:
        line = executor(step)
        return _PseudoLoopResult(reason="complete", final_message=line)
    except (OSError, ValueError) as e:
        return _PseudoLoopResult(reason="poison", final_message=str(e))
    except Exception as e:  # noqa: BLE001
        return _PseudoLoopResult(
            reason="poison",
            final_message=f"{type(e).__name__}: {e}",
        )


def _dispatch_metadata(step):
    from .planners.metadata_inventory import execute_metadata_step
    return execute_metadata_step(step)


def _dispatch_palace_mine(step):
    from .planners.palace_mine import execute_palace_mine_step
    return execute_palace_mine_step(step)


def _dispatch_palace_apply(step):
    from .planners.palace_apply import execute_palace_apply_step
    return execute_palace_apply_step(step)


def _dispatch_mos_canon_ingest(step):
    from .planners.mos_canon_ingest import execute_mos_canon_ingest_step
    return execute_mos_canon_ingest_step(step)


def _dispatch_palace_clean(step):
    from .planners.palace_clean import execute_palace_clean_step
    return execute_palace_clean_step(step)


def _dispatch_summaries_to_atoms(step):
    from .planners.summaries_to_atoms import execute_summaries_to_atoms_step
    return execute_summaries_to_atoms_step(step)


def _dispatch_dream_atomize(step):
    from .planners.trillion_dollar import execute_dream_atomize_step
    return execute_dream_atomize_step(step)


_NO_MODEL_DISPATCH: dict[str, callable] = {
    "metadata_inventory_file": _dispatch_metadata,
    "palace_mine_atom": _dispatch_palace_mine,
    "palace_apply_proposal": _dispatch_palace_apply,
    "mos_canon_ingest_clause": _dispatch_mos_canon_ingest,
    "palace_clean_propose": _dispatch_palace_clean,
    "summaries_to_atoms_line": _dispatch_summaries_to_atoms,  # v0.2.11
    "dream_atomize": _dispatch_dream_atomize,                  # v0.2.12
}


async def run_one_step(
    *,
    task_id: str,
    tools: dict,
    store: ContinuationStore | None = None,
    budget: RunBudget | None = None,
    mode: Mode = Mode.ONESHOT,
    model_filter: str | None = None,
) -> StepRunResult:
    """Execute exactly one pending step from a continuation.

    Acquires the lock non-blocking. If the lock is held by another runner,
    returns a ``locked`` result without invoking the model — the caller (a
    driver loop) should sleep and retry.

    If the continuation is drained (all steps terminal) or has no pending
    steps, returns a ``drained`` / ``no_step`` result without invoking the
    model.

    The model is invoked at most ONCE per call, even if more pending steps
    remain. The driver re-invokes us for the next step. This is the
    architectural property that bounds the model's per-invocation context.

    ``model_filter``: if set, only run a step whose ``required_model`` matches.
    Steps for other models are left pending. This is what enables phase-batched
    drains where each model loads exactly once. Use ``"orchestrator"``,
    ``"vision"``, ``"coder"``, etc. ``None`` (default) runs the next pending
    step regardless of model — v0.2.5 behavior, fully backward compatible.
    """
    from .loop import agent_loop  # local import — avoid loop-import cycle

    store = store or ContinuationStore(SETTINGS.paths.continuations_dir)
    budget = budget or DEFAULT_STEP_BUDGET

    try:
        # Non-blocking lock — drivers should expect contention and retry.
        with store.lock(task_id, blocking=False) as cont:
            return await _run_one_step_locked(
                cont=cont, tools=tools, budget=budget, mode=mode,
                model_filter=model_filter,
            )
    except ContinuationLocked:
        return StepRunResult(
            task_id=task_id,
            step_id=-1,
            step_kind="",
            outcome="locked",
        )
    except ContinuationNotFound:
        return StepRunResult(
            task_id=task_id,
            step_id=-1,
            step_kind="",
            outcome="no_step",
        )


async def _run_one_step_locked(
    *, cont: Continuation, tools: dict, budget: RunBudget, mode: Mode,
    model_filter: str | None = None,
) -> StepRunResult:
    """Execute one step. Caller holds the continuation lock."""
    from .loop import agent_loop

    if cont.is_drained():
        return StepRunResult(
            task_id=cont.task_id,
            step_id=-1,
            step_kind="",
            outcome="drained",
            cont_status=cont.status,
            progress=cont.progress,
        )

    # v0.2.12+ — Refuse to advance a paused continuation. The dream-runner
    # and sov-drive loop both check for this exit code and stop cleanly.
    # Operator runs `sov resume <id>` to restart.
    if cont.status == "paused":
        return StepRunResult(
            task_id=cont.task_id,
            step_id=-1,
            step_kind="",
            outcome="paused",
            cont_status="paused",
            progress=cont.progress,
        )

    # Find next pending step. If model_filter is set, only consider steps
    # whose required_model matches.
    if model_filter is not None:
        step = cont.next_pending_for_model(model_filter)
    else:
        step = cont.next_pending()

    if step is None:
        # Distinguish three cases:
        #   1. Continuation fully drained → "drained"
        #   2. model_filter set, no steps for this model, but OTHER models
        #      still have pending steps → "filtered" (drain-by-model needs
        #      to know to advance to the next phase)
        #   3. model_filter set or unset, no pending of any kind → "no_step"
        if model_filter is not None and cont.next_pending() is not None:
            outcome = "filtered"
        else:
            outcome = "no_step"
        return StepRunResult(
            task_id=cont.task_id,
            step_id=-1,
            step_kind="",
            outcome=outcome,
            cont_status=cont.status,
            progress=cont.progress,
        )

    planner = get_planner(cont.planner)
    rendered_goal = planner.render_step(step, cont.planner_args)

    emit_event(
        "continue-start-d",
        plane="control",
        trace_id=f"cont:{cont.task_id}",
        payload={
            "task_id": cont.task_id,
            "step_id": step.id,
            "step_kind": step.kind,
            "planner": cont.planner,
            "required_model": step.required_model,
        },
    )

    step.started_at = _utc_now()
    step.status = "pending"  # explicit; will be mutated by _bind_step_to_loop_result

    # v0.2.11+ — Per-step VRAM monitoring. Only sample around model-invoking
    # steps; pure-Python steps don't move VRAM, so sampling them is wasted
    # nvidia-smi calls.
    from .vram_monitor import VRAMSampler, VRAMTrace
    vram_sampler: VRAMSampler | None = None
    if step.required_model != "none":
        vram_sampler = VRAMSampler()
        vram_sampler.start()

    started_wall = time.monotonic()
    try:
        # ── Model-affinity dispatch ───────────────────────────────────────
        # required_model='none' → pure-Python execution path. No model.
        # Used by metadata-inventory and any future no-model planner.
        if step.required_model == "none":
            loop_result = _execute_no_model_step(step)
        else:
            # Map required_model to a configured model name.
            model_name = _resolve_model_name(step.required_model)
            loop_result = await agent_loop(
                goal=rendered_goal,
                mode=mode,
                budget=budget,
                tools=tools,
                model=model_name,
            )

        elapsed = time.monotonic() - started_wall
    finally:
        # Always stop the sampler, even if the step raised. Returns
        # a "VRAMTrace(None,None,None)" on no-GPU systems.
        if vram_sampler is not None:
            vram_trace = vram_sampler.stop()
        else:
            vram_trace = VRAMTrace()

    _bind_step_to_loop_result(
        step, loop_result, planner=planner, planner_args=cont.planner_args
    )
    step.elapsed_seconds = round(elapsed, 3)
    # Persist VRAM trace on the step itself so `sov continuations show`
    # surfaces it for retrospective analysis.
    step.vram_before_mb = vram_trace.before_mb
    step.vram_peak_mb = vram_trace.peak_mb
    step.vram_after_mb = vram_trace.after_mb
    cont.update_status_from_steps()

    emit_event(
        "continue-end-d",
        plane="control",
        trace_id=f"cont:{cont.task_id}",
        payload={
            "task_id": cont.task_id,
            "step_id": step.id,
            "outcome": loop_result.reason,
            "step_status": step.status,
            "iterations": loop_result.iterations,
            "tokens": loop_result.tokens_used,
            "elapsed_seconds": round(elapsed, 3),
            "required_model": step.required_model,
            "cont_status": cont.status,
            "progress": list(cont.progress),
            "vram_before_mb": vram_trace.before_mb,
            "vram_peak_mb": vram_trace.peak_mb,
            "vram_after_mb": vram_trace.after_mb,
        },
    )

    return StepRunResult(
        task_id=cont.task_id,
        step_id=step.id,
        step_kind=step.kind,
        outcome=loop_result.reason or "complete",
        iterations=loop_result.iterations,
        tokens=loop_result.tokens_used,
        elapsed_seconds=round(elapsed, 3),
        final_message=loop_result.final_message,
        cont_status=cont.status,
        progress=cont.progress,
        required_model=step.required_model,
        vram_before_mb=vram_trace.before_mb,
        vram_peak_mb=vram_trace.peak_mb,
        vram_after_mb=vram_trace.after_mb,
    )
