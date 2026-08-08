"""Tests for the bounded self-practice session: it must be genuinely bounded,
halt the instant asked, stay observable, and never touch code or values."""
from __future__ import annotations

from sovereign_agent import self_practice as sp
from sovereign_agent.intuition import IntuitionEngine


class _Clock:
    """Deterministic clock: advances by `step` each call (0 = time frozen)."""
    def __init__(self, step: float = 0.0):
        self.t = 0.0
        self.step = step

    def __call__(self) -> float:
        v = self.t
        self.t += self.step
        return v


def test_bounded_by_cycle_cap():
    cfg = sp.PracticeConfig(max_seconds=10_000, max_cycles=3, study_passes_per_cycle=1, cooldown_seconds=0.0)
    rep = sp.run_practice_session(config=cfg, clock=_Clock(step=0.0))  # time frozen
    assert rep.cycles_run == 3
    assert rep.stopped_reason == "cycles"


def test_bounded_by_time_box():
    cfg = sp.PracticeConfig(max_seconds=3.0, max_cycles=10_000, study_passes_per_cycle=1, cooldown_seconds=0.0)
    rep = sp.run_practice_session(config=cfg, clock=_Clock(step=1.0))   # ~1s/tick
    assert rep.stopped_reason == "time"
    assert 1 <= rep.cycles_run < 10_000


def test_should_stop_halts_cleanly():
    calls = {"n": 0}

    def stop():
        calls["n"] += 1
        return calls["n"] > 2          # allow ~2 cycles, then halt

    cfg = sp.PracticeConfig(max_seconds=10_000, max_cycles=10_000, cooldown_seconds=0.0)
    rep = sp.run_practice_session(config=cfg, should_stop=stop, clock=_Clock())
    assert rep.stopped_reason == "halt"
    assert rep.cycles_run <= 3


def test_emits_observable_events():
    events: list[sp.PracticeEvent] = []
    cfg = sp.PracticeConfig(max_seconds=10_000, max_cycles=2, study_passes_per_cycle=1, cooldown_seconds=0.0)
    sp.run_practice_session(config=cfg, on_event=events.append, clock=_Clock())
    kinds = [e.kind for e in events]
    assert kinds[0] == "start"
    assert kinds[-1] == "done"
    assert kinds.count("cycle") == 2


def test_practice_accumulates_calibration():
    eng = IntuitionEngine()
    cfg = sp.PracticeConfig(max_seconds=10_000, max_cycles=4, study_passes_per_cycle=2, cooldown_seconds=0.0)
    sp.run_practice_session(eng, config=cfg, clock=_Clock())
    rep = eng.domain_report()
    assert rep and any(d["reps"] >= 4 for d in rep)   # reps grew across cycles


def test_practice_writes_journal(tmp_path):
    cfg = sp.PracticeConfig(max_seconds=10_000, max_cycles=2, cooldown_seconds=0.0)
    rep = sp.run_practice_session(config=cfg, journal_dir=tmp_path, clock=_Clock())
    assert rep.journal_path is not None
    from pathlib import Path
    assert (Path(rep.journal_path) / "journal.md").exists()


def test_practice_never_mutates_doctrine_or_priorities():
    from sovereign_agent import mos_canon as mc
    before = len(mc.ALL_CLAUSES)
    cfg = sp.PracticeConfig(max_seconds=10_000, max_cycles=5, cooldown_seconds=0.0)
    sp.run_practice_session(config=cfg, clock=_Clock())
    # the canon is untouched by a practice session
    assert len(mc.ALL_CLAUSES) == before
    # and the read-only priorities are still immutable afterward
    P = mc.read_only_priorities()
    raised = False
    try:
        P[0].name = "Convenience"  # type: ignore[misc]
    except Exception:
        raised = True
    assert raised


# ─── timing/cadence safety: the breath is interruptible ───────────────────────


def _virtual_time():
    """A clock whose injected sleep advances it — like real time, but instant."""
    t = {"v": 0.0}
    return (lambda: t["v"]), (lambda s: t.__setitem__("v", t["v"] + s))


def test_rest_is_fully_honored_when_uninterrupted():
    clock, sleep = _virtual_time()
    sp._interruptible_rest(3.0, should_stop=lambda: False, clock=clock, start=0.0,
                           max_seconds=10_000, sleep=sleep, poll=0.25)
    assert abs(clock() - 3.0) < 0.3            # rested ~the full breath


def test_rest_stops_within_a_slice_on_halt():
    clock, sleep = _virtual_time()
    calls = {"n": 0}

    def stop():
        calls["n"] += 1
        return calls["n"] > 2                   # halt after ~2 slices

    sp._interruptible_rest(600.0, should_stop=stop, clock=clock, start=0.0,
                           max_seconds=10_000, sleep=sleep, poll=0.25)
    assert clock() < 1.0                        # bailed out fast, not 600s


def test_rest_respects_the_session_time_box():
    clock, sleep = _virtual_time()
    # already near the 5s cap → rest should stop almost immediately
    sleep(4.9)
    sp._interruptible_rest(60.0, should_stop=lambda: False, clock=clock, start=0.0,
                           max_seconds=5.0, sleep=sleep, poll=0.25)
    assert clock() < 6.0
