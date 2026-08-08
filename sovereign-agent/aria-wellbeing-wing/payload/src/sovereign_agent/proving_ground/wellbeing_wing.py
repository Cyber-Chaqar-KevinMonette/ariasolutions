"""proving_ground/wellbeing_wing.py — the wellbeing wing of the proving ground.
(Wellbeing round · W5)

Five scored tasks for the W1-W4 machinery — the stick before any tuning,
same discipline as every other wing: real machinery, mechanical scorers,
no LLM judge; a task crash is a FAIL, never a run crash (the runner
guarantees that).

  wellbeing-pass-persists     a wellbeing pass round-trips through the ledger
  wellbeing-gate-blocks       the gate BLOCKs a zombie-IV fixture
  wellbeing-diagnosis-readable  the standing audit logs a real readable
                                WELL-* case
  wellbeing-angel-measured    the angel lens uses the measured composite
                                over a live-only check
  wellbeing-pass-gates        the reflecting stance gates then clears
"""
from __future__ import annotations

import tempfile
from pathlib import Path

HEALTHY_EVENTS = [
    {"flag": "commit-d", "payload": {"message": "fix the loader bug"}},
    {"flag": "presence-note-d", "payload": {}},
]


async def _task_wellbeing_pass_persists() -> tuple[bool, str]:
    """A wellbeing pass over real events round-trips through the ledger:
    the returned result and the freshly-read latest_wellbeing() agree."""
    from sovereign_agent.wellbeing import latest_wellbeing, record_wellbeing_pass

    with tempfile.TemporaryDirectory() as td:
        data_dir = Path(td) / "data"
        data_dir.mkdir()
        result = record_wellbeing_pass(HEALTHY_EVENTS, data_dir=data_dir)
        latest = latest_wellbeing(data_dir)
        ok = (latest is not None
             and latest.get("pass_id") == result.pass_id
             and latest.get("verdict") == result.verdict == "healthy")
    return ok, f"wellbeing pass {result.pass_id} persisted and round-tripped"


async def _task_wellbeing_gate_blocks() -> tuple[bool, str]:
    """An ImpactVector with a zombie signal (false certainty) must
    BLOCK — the calibration mismatch this gate exists to catch."""
    from sovereign_agent.stewardship.msims import Cell, Dimension, ImpactVector, Scale
    from sovereign_agent.wellbeing import gate

    iv = ImpactVector()
    iv.set(Dimension.MENTAL, Scale.MICRO, Cell(value=0.0, confidence=0.9))
    iv.set(Dimension.MENTAL, Scale.MESO, Cell(value=0.0, confidence=0.9))
    iv.set(Dimension.MENTAL, Scale.MACRO, Cell(value=-0.5, confidence=0.9))
    if not iv.is_zombie():
        return False, "fixture did not actually trigger is_zombie() — test itself is broken"

    verdict = gate(HEALTHY_EVENTS, iv=iv)
    ok = verdict.verdict == "BLOCK" and verdict.impact_is_zombie
    return ok, f"gate verdict {verdict.verdict} on a zombie-IV fixture"


async def _task_wellbeing_diagnosis_readable() -> tuple[bool, str]:
    """The standing sentinel's second phase logs a real, readable WELL-*
    case into the diagnosis catalog — proves W3's wiring stays live.

    `companion_tools._load_recent_events_for_report()` (which the
    sentinel's scan() calls internally) has no data_dir override — it
    always reads live SETTINGS.paths, never this task's own tempdir. A
    proving-ground task must never touch the real vessel's event log, so
    the reader is patched directly to hand back this fixture — real
    machinery throughout (the sentinel, the tribunal, the diagnosis
    catalog), a controlled input only for the one function with no
    override."""
    from unittest.mock import patch as _patch

    from sovereign_agent.diagnosis import ConflictCatalog
    from sovereign_agent.stewardship import wellbeing_sentinel as ws_mod

    with tempfile.TemporaryDirectory() as td:
        data_dir = Path(td)
        with _patch.object(ws_mod, "_recent_events", lambda since_iso: HEALTHY_EVENTS):
            sentinel = ws_mod.WellbeingSentinel(data_dir)
            sentinel.scan()
        standing = sentinel.load_catalog(name="standing-audit")
        ok = False
        if standing and str(standing.get("case_id", "")).startswith("WELL"):
            cat = ConflictCatalog(data_dir / "diagnosis")
            conflict = cat.get_conflict(standing["case_id"])
            ok = conflict is not None and conflict.type == "ambiguity"
    return ok, f"standing audit case_id={standing.get('case_id') if standing else None!r}"


async def _task_wellbeing_angel_measured() -> tuple[bool, str]:
    """The angel lens overrides its live-only tribunal.angel.advocate()
    call with W1's measured composite when the proposal carries it."""
    from sovereign_agent.spectrum.lenses import angel

    high = angel({"love_grade": "A"})
    low = angel({"love_grade": "D", "flourishing_verdict": "reject-for-the-future"})
    ok = (high.score > 0.5 and low.score <= -0.6
         and any("measured" in g for g in high.gifts)
         and any("reject-for-the-future" in c for c in low.concerns))
    return ok, f"angel measured-data scores: high={high.score:.2f} low={low.score:.2f}"


async def _task_wellbeing_pass_gates() -> tuple[bool, str]:
    """The reflecting stance gates dispatch until a clean pass lands,
    then clears it — real machinery throughout, controlled input only
    (the stance's own entry side effect scores whatever the on-disk
    events happen to be at the moment this task runs, which a proving-
    ground task can't pin a fixed outcome against, so the side effect is
    disabled just for the "starts unclear" half)."""
    from unittest.mock import patch as _patch

    from sovereign_agent.modes_crown import stances as stances_mod
    from sovereign_agent.wellbeing import record_wellbeing_pass

    with tempfile.TemporaryDirectory() as td:
        data_dir = Path(td) / "data"
        data_dir.mkdir()
        with _patch.object(stances_mod, "_run_wellbeing_pass_for_stance", lambda d: None):
            stances_mod.set_stance("reflecting", data_dir=data_dir)
        unclear = not stances_mod.wellbeing_gate_clear(data_dir)

        record_wellbeing_pass(HEALTHY_EVENTS, data_dir=data_dir)
        cleared = stances_mod.wellbeing_gate_clear(data_dir)

        ok = unclear and cleared
    return ok, f"gated before a pass (unclear={unclear}), cleared after (cleared={cleared})"


WELLBEING_TASKS = {
    "wellbeing-pass-persists": _task_wellbeing_pass_persists,
    "wellbeing-gate-blocks": _task_wellbeing_gate_blocks,
    "wellbeing-diagnosis-readable": _task_wellbeing_diagnosis_readable,
    "wellbeing-angel-measured": _task_wellbeing_angel_measured,
    "wellbeing-pass-gates": _task_wellbeing_pass_gates,
}
