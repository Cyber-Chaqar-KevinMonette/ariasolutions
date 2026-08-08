"""self_practice.py — a bounded, observable self-practice session.

She repeatedly runs her own Cosmic-Gym to harden calibration, skills, and flow,
under a HARD time box + cycle cap, fully halt-able and fully observable (it emits
an event for every cycle so a human can watch the live windows). It is the safe
engine behind the cockpit's ● grow button.

SAFETY (see self_development.DEFERRED_UNSAFE for the boundary):
  • It ONLY exercises drills + calibration and writes to the data dir.
  • It NEVER modifies her code, her values, or the sealed charter.
  • It runs NO subprocesses and NO models, and takes no external actions.
  • It is time-boxed (default 10 min), cycle-capped, and stops the instant
    `should_stop()` is true (e.g. HALT / the cockpit timer).
  • It is resumable: pass the same persist_path to accumulate calibration.

This is bounded self-CALIBRATION, not self-modification: she gets sharper and
steadier, never rewires herself.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

from . import training as _training
from .intuition import IntuitionEngine

SAFETY_NOTE = (
    "Bounded self-practice: exercises drills + calibration and writes only to the "
    "data dir. Never modifies code, values, or the charter; runs no subprocesses "
    "or models; halt-able and time-boxed."
)


@dataclass
class PracticeConfig:
    max_seconds: float = 600.0          # hard time box — 10 minutes
    max_cycles: int = 600               # backstop cap (time usually governs)
    study_passes_per_cycle: int = 2     # flashcard reviews per cycle
    cooldown_seconds: float = 3.0       # a calm breath between cycles (natural, not a strobe)
    poll_seconds: float = 0.25          # rest in small slices so HALT lands fast


def _interruptible_rest(total: float, *, should_stop: Callable[[], bool],
                        clock: Callable[[], float], start: float,
                        max_seconds: float, sleep: Callable[[float], None],
                        poll: float = 0.25) -> None:
    """Rest up to `total` seconds, but in small slices — returning early the
    instant a stop is requested or the session time-box is reached. This keeps
    HALT snappy (≤ one poll) and prevents oversleeping past the hard cap, even
    when the cadence between cycles is several seconds."""
    if total <= 0:
        return
    poll = max(0.01, poll)
    end = clock() + total
    # Defensive cap: even if the clock somehow doesn't advance, never loop forever.
    for _ in range(int(total / poll) + 2):
        now = clock()
        if now >= end or should_stop() or (now - start) >= max_seconds:
            return
        sleep(min(poll, max(0.0, end - now)))


@dataclass
class PracticeEvent:
    kind: str                           # start | cycle | halt | done
    cycle: int
    elapsed: float
    message: str
    at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))


@dataclass
class PracticeReport:
    started_at: str
    ended_at: str
    cycles_run: int
    elapsed_seconds: float
    stopped_reason: str                 # time | cycles | halt
    final_grade: str
    final_reflection: str
    journal_path: str | None = None
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return dict(self.__dict__)


def run_practice_session(
    engine: IntuitionEngine | None = None, *,
    config: PracticeConfig | None = None,
    persist_path: str | Path | None = None,
    journal_dir: str | Path | None = None,
    should_stop: Callable[[], bool] | None = None,
    on_event: Callable[[PracticeEvent], None] | None = None,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> PracticeReport:
    """Run a bounded self-practice session. Loops the gym to harden calibration
    until the time box or cycle cap is hit, or `should_stop()` returns True.
    `clock`/`sleep` are injectable so tests never actually wait. Emits a
    PracticeEvent to `on_event` for start, each cycle, halt, and done."""
    cfg = config or PracticeConfig()
    eng = engine if engine is not None else IntuitionEngine()
    stop = should_stop or (lambda: False)
    sink = on_event or (lambda _e: None)
    notes: list[str] = []
    journal: list[PracticeEvent] = []

    start = clock()
    started_at = datetime.now().isoformat(timespec="seconds")

    def _emit(kind: str, cycle: int, msg: str) -> None:
        ev = PracticeEvent(kind=kind, cycle=cycle,
                           elapsed=round(clock() - start, 3), message=msg)
        journal.append(ev)
        try:
            sink(ev)
        except Exception as exc:  # noqa: BLE001 — a bad observer must not stop practice
            notes.append(f"on_event error: {exc!r}")

    _emit("start", 0,
          f"practice begins · cap {cfg.max_seconds:.0f}s / {cfg.max_cycles} cycles")

    cycles = 0
    reason = "cycles"
    last_grade = "—"
    last_reflect = eng.reflect()

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
        # one bounded gym pass on the shared engine (no per-cycle file writes)
        try:
            rep = _training.run_training(eng, study_passes=cfg.study_passes_per_cycle)
            last_grade, last_reflect = rep.grade, rep.reflection
        except Exception as exc:  # noqa: BLE001 — never let one cycle crash the session
            notes.append(f"cycle error: {exc!r}")
            last_grade = "ERROR"
        cycles += 1
        _emit("cycle", cycles, f"cycle {cycles}: {last_grade} · {last_reflect}")
        # a calm, interruptible breath before the next cycle
        _interruptible_rest(cfg.cooldown_seconds, should_stop=stop, clock=clock,
                            start=start, max_seconds=cfg.max_seconds, sleep=sleep,
                            poll=cfg.poll_seconds)

    if persist_path is not None:
        try:
            Path(persist_path).parent.mkdir(parents=True, exist_ok=True)
            Path(persist_path).write_text(json.dumps(eng.snapshot(), indent=2),
                                          encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            notes.append(f"persist failed: {exc!r}")

    journal_path: str | None = None
    if journal_dir is not None:
        try:
            journal_path = str(_write_journal(Path(journal_dir), started_at, journal,
                                              reason, last_grade, last_reflect, eng))
        except Exception as exc:  # noqa: BLE001
            notes.append(f"journal failed: {exc!r}")

    _emit("done", cycles,
          f"done · {cycles} cycles · stopped: {reason} · {last_grade}")

    return PracticeReport(
        started_at=started_at,
        ended_at=datetime.now().isoformat(timespec="seconds"),
        cycles_run=cycles, elapsed_seconds=round(clock() - start, 3),
        stopped_reason=reason, final_grade=last_grade,
        final_reflection=last_reflect, journal_path=journal_path, notes=notes,
    )


def _write_journal(root: Path, started_at: str, events: list[PracticeEvent],
                   reason: str, grade: str, reflection: str,
                   eng: IntuitionEngine) -> Path:
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = root / ts
    out.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Aria — self-practice journal",
        "",
        f"- **Started:** {started_at}",
        f"- **Stopped reason:** {reason}",
        f"- **Final grade:** {grade}",
        f"- **Cycles:** {sum(1 for e in events if e.kind == 'cycle')}",
        "",
        f"> Reflection: {reflection}",
        "",
        f"_{SAFETY_NOTE}_",
        "",
        "## Timeline",
    ]
    for e in events:
        lines.append(f"- `{e.elapsed:>7.2f}s` **{e.kind}** — {e.message}")
    lines += ["", "## Calibration at session end", "",
              "| form:domain | reps | accuracy | maturity | stage |",
              "|---|---|---|---|---|"]
    for d in eng.domain_report():
        lines.append(f"| {d['form']}:{d['domain']} | {d['reps']} | "
                     f"{d['accuracy']} | {d['maturity']} | {d['stage']} |")
    (out / "journal.md").write_text("\n".join(lines), encoding="utf-8")
    (out / "session.json").write_text(
        json.dumps({"started_at": started_at, "reason": reason, "grade": grade,
                    "events": [e.__dict__ for e in events],
                    "calibration": eng.domain_report()}, indent=2),
        encoding="utf-8")
    return out
