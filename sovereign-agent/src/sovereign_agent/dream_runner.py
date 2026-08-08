"""
╔══════════════════════════════════════════════════════════════════════════╗
║  dream_runner.py — Outer driver for a dream-session                       ║
║  v0.2.12                                                                  ║
║                                                                           ║
║  One ``sov dream advance <dream_id>`` invocation does this:               ║
║                                                                           ║
║    1. Load the dream session                                              ║
║    2. Refuse if status != active                                          ║
║    3. Refuse if any cap is already exceeded (mark exhausted)              ║
║    4. If a current_cycle exists and is not yet drained → drive ONE step    ║
║       of it (delegating to continue_runner.run_one_step)                  ║
║    5. Else (no current cycle, or current cycle drained):                  ║
║         a. If the previous cycle drained: finalize its CycleEntry         ║
║         b. Re-check caps (the cycle just-finished might have pushed us    ║
##           past max_files); mark exhausted if so                          ║
║         c. Plan a fresh trillion-dollar cycle, link it on the dream       ║
║         d. Advance ONE step of the new cycle                              ║
║    6. Persist dream state                                                 ║
║                                                                           ║
║  This is the same ratchet pattern as the per-step re-trigger, just one    ║
║  level up: ONE invocation moves the dream forward by ONE step. The shell  ║
║  driver (``scripts/sovereign-dream-loop.sh``) re-invokes us until the     ║
║  dream is exhausted, paused, or halted.                                   ║
║                                                                           ║
║  Why one step at a time?                                                  ║
║    Same reason as continue_runner: bounded model context per invocation,  ║
║    crash-resumable mid-cycle, every restart is a fresh Python process,    ║
║    OS-managed lifecycle. The dream runner is just a thin shim that knows  ║
║    how to spawn the next cycle when the current one ends.                 ║
║                                                                           ║
║  Concurrency:                                                             ║
║    No fcntl on the dream YAML — a dream is single-operator by design.     ║
║    The cycle-level fcntl in continue_runner protects against races on     ║
║    the underlying continuation. So two ``advance`` calls might both read  ║
║    the same dream, but only one can advance the cycle, and the other     ║
║    sees the same cursor on its next read.                                 ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from .config import SETTINGS
from .continuation import ContinuationStore
from .continue_runner import StepRunResult, run_one_step
from .dream import (
    CycleEntry,
    DreamSession,
    DreamStore,
    HARD_CAP_CYCLES,
    count_files_under,
    cycle_task_id_for,
)
from .events import emit_event
from .modes import Mode, RunBudget
from .planners import get_planner


@dataclass
class DreamAdvanceResult:
    """Outcome of one ``advance`` call.

    Mirrors the shape of StepRunResult so callers (and the CLI) can render
    consistently. ``dream_status`` is the post-advance status, useful for
    drivers deciding whether to keep looping.
    """

    dream_id: str
    dream_status: str
    cycle_number: int
    step_outcome: str            # one of: complete | poison | drained | locked | paused | filtered | no_step | halted | budget | dream_exhausted | dream_paused | dream_halted | new_cycle
    step_id: int = -1
    step_kind: str = ""
    iterations: int = 0
    tokens: int = 0
    elapsed_seconds: float = 0.0
    files_written_total: int = 0
    cycles_completed: int = 0
    reason: str = ""
    final_message: str | None = None


def advance_dream(
    *,
    dream_id: str,
    tools: dict,
    store: DreamStore | None = None,
    cont_store: ContinuationStore | None = None,
    budget: RunBudget | None = None,
    mode: Mode = Mode.ONESHOT,
) -> DreamAdvanceResult:
    """Move a dream-session forward by exactly ONE step.

    Synchronous wrapper around the async continue_runner — runs an event
    loop internally only when a model-invoking step is dispatched. Pure-
    Python steps (the atomize step) skip the loop overhead.

    Returns a result with a step_outcome the caller can switch on.
    """
    import asyncio

    store = store or DreamStore(
        SETTINGS.paths.dream_sessions_dir,
        SETTINGS.paths.dreams_work_dir,
    )
    cont_store = cont_store or ContinuationStore(SETTINGS.paths.continuations_dir)

    dream = store.get(dream_id)

    # ── Terminal checks ──────────────────────────────────────────────────
    if dream.status == "paused":
        return DreamAdvanceResult(
            dream_id=dream_id, dream_status="paused",
            cycle_number=len(dream.cycles), step_outcome="dream_paused",
            files_written_total=dream.files_written,
            cycles_completed=dream.cycles_completed,
            reason="dream is paused; run `sov dream resume` first",
        )
    if dream.status in ("completed", "exhausted", "halted"):
        return DreamAdvanceResult(
            dream_id=dream_id, dream_status=dream.status,
            cycle_number=len(dream.cycles), step_outcome=f"dream_{dream.status}",
            files_written_total=dream.files_written,
            cycles_completed=dream.cycles_completed,
            reason=f"dream is {dream.status}",
        )

    # ── Cap pre-check (might already be exhausted from prior advance) ───
    exhausted, reason = dream.caps_check()
    if exhausted:
        dream.status = "exhausted"
        dream.notes = (dream.notes + "\n" if dream.notes else "") + f"EXHAUSTED: {reason}"
        store.save(dream)
        emit_event(
            "dream-exhausted-d", plane="control",
            trace_id=f"dream:{dream_id}",
            payload={"dream_id": dream_id, "reason": reason,
                     "files_written": dream.files_written,
                     "cycles_completed": dream.cycles_completed},
        )
        return DreamAdvanceResult(
            dream_id=dream_id, dream_status="exhausted",
            cycle_number=len(dream.cycles), step_outcome="dream_exhausted",
            files_written_total=dream.files_written,
            cycles_completed=dream.cycles_completed, reason=reason,
        )

    # ── Pick or start a cycle ────────────────────────────────────────────
    current_task = dream.current_cycle_task_id
    new_cycle_started = False

    if current_task is not None:
        # See if the existing cycle is still alive (not drained).
        try:
            current_cont = cont_store.get(current_task)
        except Exception:  # noqa: BLE001
            # Continuation file was deleted out from under us. Treat the
            # cycle as ended; we'll plan a new one below.
            current_cont = None
            current_task = None

        # ── EC-DREAM-005: cycle paused but dream active ─────────────────
        # If someone paused the cycle continuation directly (e.g. via
        # `sov pause cycle-...`), the inline driver would otherwise spin
        # forever on outcome="paused". Auto-pause the dream as well so
        # the loop driver sees exit-code-8 and stops cleanly.
        if (current_cont is not None
                and current_cont.status == "paused"
                and not current_cont.is_drained()):
            from .edge_cases import track as _track_ec
            dream.status = "paused"
            dream.notes = (
                (dream.notes + "\n" if dream.notes else "")
                + f"AUTO-PAUSED: underlying cycle {current_task} is paused "
                  f"(EC-DREAM-005)"
            )
            store.save(dream)
            _track_ec("EC-DREAM-005", payload={
                "dream_id": dream_id, "cycle_task_id": current_task,
            })
            return DreamAdvanceResult(
                dream_id=dream_id, dream_status="paused",
                cycle_number=len(dream.cycles), step_outcome="dream_paused",
                files_written_total=dream.files_written,
                cycles_completed=dream.cycles_completed,
                reason=(
                    f"underlying cycle {current_task} was paused; auto-paused "
                    f"the dream too. Resume both with "
                    f"`sov dream resume {dream_id}`."
                ),
            )

        if current_cont is not None and current_cont.is_drained():
            # Finalize the just-finished cycle on the dream record.
            _finalize_cycle(dream, current_cont, store)
            current_task = None
            # Caps re-check after the cycle's files land.
            exhausted, reason = dream.caps_check()
            if exhausted:
                dream.status = "exhausted"
                dream.notes = (dream.notes + "\n" if dream.notes else "") + f"EXHAUSTED: {reason}"
                store.save(dream)
                emit_event(
                    "dream-exhausted-d", plane="control",
                    trace_id=f"dream:{dream_id}",
                    payload={"dream_id": dream_id, "reason": reason,
                             "files_written": dream.files_written,
                             "cycles_completed": dream.cycles_completed},
                )
                return DreamAdvanceResult(
                    dream_id=dream_id, dream_status="exhausted",
                    cycle_number=len(dream.cycles), step_outcome="dream_exhausted",
                    files_written_total=dream.files_written,
                    cycles_completed=dream.cycles_completed, reason=reason,
                )

            # ── EC-DREAM-006: idle-cycle detection ─────────────────────
            # If the last 3 cycles each produced ≤ IDLE_ATOM_THRESHOLD
            # atoms, the dream has likely saturated its idea space. Auto-
            # pause to stop burning tokens; operator can nudge with a
            # steering prompt or accept the pause.
            from .health import IDLE_ATOM_THRESHOLD, IDLE_CYCLE_WINDOW
            from .edge_cases import track as _track_ec
            recent = dream.cycles[-IDLE_CYCLE_WINDOW:]
            if (len(recent) >= IDLE_CYCLE_WINDOW
                    and all(getattr(c, "atoms_written", 0) <= IDLE_ATOM_THRESHOLD
                            for c in recent)):
                dream.status = "paused"
                dream.notes = (
                    (dream.notes + "\n" if dream.notes else "")
                    + f"AUTO-PAUSED: last {IDLE_CYCLE_WINDOW} cycles produced "
                      f"≤ {IDLE_ATOM_THRESHOLD} atoms each (EC-DREAM-006)"
                )
                store.save(dream)
                _track_ec("EC-DREAM-006", payload={
                    "dream_id": dream_id,
                    "recent_atoms": [getattr(c, "atoms_written", 0)
                                     for c in recent],
                })
                return DreamAdvanceResult(
                    dream_id=dream_id, dream_status="paused",
                    cycle_number=len(dream.cycles), step_outcome="dream_paused",
                    files_written_total=dream.files_written,
                    cycles_completed=dream.cycles_completed,
                    reason=(
                        f"last {IDLE_CYCLE_WINDOW} cycles each produced ≤ "
                        f"{IDLE_ATOM_THRESHOLD} atoms (idea space saturated). "
                        f"Resume with --steering or accept the pause."
                    ),
                )

    if current_task is None:
        # Plan a fresh cycle. We use the trillion-dollar planner directly
        # because we know its shape: 5 deterministic steps. Cycle number
        # is 1-indexed and uses len(dream.cycles)+1 so resume after a
        # crashed cycle still numbers monotonically.
        if dream.cycles_completed >= HARD_CAP_CYCLES:
            dream.status = "exhausted"
            dream.notes = (
                (dream.notes + "\n" if dream.notes else "")
                + f"EXHAUSTED: hard cycle cap ({HARD_CAP_CYCLES}) reached"
            )
            store.save(dream)
            return DreamAdvanceResult(
                dream_id=dream_id, dream_status="exhausted",
                cycle_number=len(dream.cycles), step_outcome="dream_exhausted",
                files_written_total=dream.files_written,
                cycles_completed=dream.cycles_completed,
                reason="hard cycle cap",
            )

        cycle_number = dream.cycles_completed + 1
        new_task_id = cycle_task_id_for(dream_id, cycle_number)
        cycle_dir = Path(dream.work_dir) / f"cycle-{cycle_number:03d}"
        cycle_dir.mkdir(parents=True, exist_ok=True)

        planner = get_planner("trillion-dollar")
        # v0.2.13: if the dream is tied to a project, pass its name so
        # atomize can tag every atom with the project namespace. Pick the
        # first project — multi-project dreams are rare; multi-project
        # tagging would need richer plumbing.
        project_name = ""
        if dream.projects:
            project_name = dream.projects[0].name

        plan_kwargs = {
            "cycle_dir": str(cycle_dir),
            "dream_id": dream_id,
            "cycle_number": cycle_number,
            "project_name": project_name,
        }
        plan_result = planner.plan(**plan_kwargs)

        # Idempotent create: if the continuation already exists (resume
        # after crash mid-cycle-creation), reuse it.
        try:
            cont_store.create(
                goal=plan_result.goal, planner="trillion-dollar",
                planner_args=plan_kwargs, steps=plan_result.steps,
                output_path=plan_result.output_path,
                task_id=new_task_id, notes=plan_result.notes,
            )
        except FileExistsError:
            pass  # cycle continuation already on disk

        dream.cycles.append(CycleEntry(
            cycle_number=cycle_number,
            task_id=new_task_id,
            started_at=_utc_now(),
            status="in_progress",
            cycle_dir=str(cycle_dir),
            title="(pending ideate)",
        ))
        dream.current_cycle_task_id = new_task_id
        store.save(dream)
        new_cycle_started = True
        current_task = new_task_id

        emit_event(
            "dream-cycle-started-d", plane="control",
            trace_id=f"dream:{dream_id}",
            payload={"dream_id": dream_id, "cycle_number": cycle_number,
                     "task_id": new_task_id, "cycle_dir": str(cycle_dir)},
        )

    # ── Drive ONE step of the (now non-None) current cycle ──────────────
    started = time.monotonic()
    step_result: StepRunResult = asyncio.run(run_one_step(
        task_id=current_task, tools=tools, store=cont_store,
        budget=budget, mode=mode,
    ))
    elapsed = time.monotonic() - started

    # If a cycle just drained as a result of THIS step, finalize it.
    if step_result.outcome == "drained":
        try:
            done_cont = cont_store.get(current_task)
            _finalize_cycle(dream, done_cont, store)
        except Exception:  # noqa: BLE001
            pass

    dream.elapsed_seconds += elapsed
    store.save(dream)

    return DreamAdvanceResult(
        dream_id=dream_id,
        dream_status=dream.status,
        cycle_number=dream.cycles_completed + (1 if step_result.outcome != "drained" else 0),
        step_outcome=("new_cycle" if new_cycle_started and step_result.outcome == "complete"
                      else step_result.outcome),
        step_id=step_result.step_id,
        step_kind=step_result.step_kind,
        iterations=step_result.iterations,
        tokens=step_result.tokens,
        elapsed_seconds=step_result.elapsed_seconds,
        files_written_total=dream.files_written,
        cycles_completed=dream.cycles_completed,
        final_message=step_result.final_message,
    )


def _finalize_cycle(
    dream: DreamSession, cont, store: DreamStore,
) -> None:
    """Mark the just-drained continuation's CycleEntry as done; update totals.

    Counts files under the cycle's cycle_dir directly — same files-on-disk
    metric the cap check uses, so the two never drift. Recomputes the dream's
    cumulative ``files_written`` from the work_dir, NOT by summing per-cycle
    deltas — sturdier against partial writes / mid-cycle crashes.
    """
    if not dream.cycles:
        return
    cycle = dream.cycles[-1]
    if cycle.task_id != cont.task_id:
        # Resume from a non-tail cycle. Find the right entry.
        match = next((c for c in dream.cycles if c.task_id == cont.task_id), None)
        if match is None:
            return
        cycle = match

    if cycle.ended_at is not None:
        return  # already finalized

    cycle.ended_at = _utc_now()
    cycle.status = (
        "done" if cont.status == "done"
        else "poisoned" if cont.status == "poisoned"
        else "in_progress"
    )

    cycle_dir = Path(cycle.cycle_dir) if cycle.cycle_dir else None
    if cycle_dir and cycle_dir.exists():
        cycle.files_written = count_files_under(cycle_dir)
    cycle.elapsed_seconds = cont.total_elapsed_seconds

    # v0.2.13: extract atoms_written and quarantined_count from the
    # atomize step's output. The atomize executor returns a string of
    # the form "cycle N: atomized A files (S already present, Q
    # quarantined)". Parse it lightly — failures mean we record 0,
    # which is the conservative default for idle detection.
    cycle.atoms_written = 0
    cycle.quarantined_count = 0
    try:
        atomize_step = next(
            (s for s in cont.steps if s.kind == "dream_atomize"), None,
        )
        if atomize_step is not None and atomize_step.result:
            import re as _re
            m = _re.search(
                r"atomized\s+(\d+)\s+files.*?(\d+)\s+quarantined",
                str(atomize_step.result),
            )
            if m:
                cycle.atoms_written = int(m.group(1))
                cycle.quarantined_count = int(m.group(2))
            else:
                # Fallback: parse just "atomized N files"
                m2 = _re.search(r"atomized\s+(\d+)\s+files", str(atomize_step.result))
                if m2:
                    cycle.atoms_written = int(m2.group(1))
    except Exception:  # noqa: BLE001
        pass

    # Also pull the title out of idea.md for nicer listings, if it exists.
    if cycle_dir is not None:
        idea_md = cycle_dir / "idea.md"
        if idea_md.is_file():
            try:
                with idea_md.open("r", encoding="utf-8", errors="replace") as f:
                    for line in f:
                        s = line.strip()
                        if s:
                            # Strip leading '#'s — likely a markdown h1.
                            cycle.title = s.lstrip("#").strip()[:200]
                            break
            except OSError:
                pass

    if cycle.status == "done":
        dream.cycles_completed += 1
    dream.current_cycle_task_id = None
    # Recompute aggregate file count from disk — single source of truth.
    if dream.work_dir:
        dream.files_written = count_files_under(Path(dream.work_dir))
    store.save(dream)

    emit_event(
        "dream-cycle-ended-d", plane="control",
        trace_id=f"dream:{dream.dream_id}",
        payload={"dream_id": dream.dream_id, "cycle_number": cycle.cycle_number,
                 "task_id": cycle.task_id, "status": cycle.status,
                 "files_written": cycle.files_written,
                 "files_written_total": dream.files_written,
                 "cycles_completed": dream.cycles_completed},
    )


def _utc_now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


__all__ = ["DreamAdvanceResult", "advance_dream"]
