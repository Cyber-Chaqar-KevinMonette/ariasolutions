"""proving_ground/grounding_wing.py — the grounding wing of the proving ground.
(Grounding round · G5)

Five scored tasks for the G1-G4 machinery — the stick before any tuning,
same discipline as every other wing: real machinery, mechanical scorers,
no LLM judge; a task crash is a FAIL, never a run crash (the runner
guarantees that).

  grounding-pass-persists     a grounding pass round-trips through the ledger
  grounding-gate-blocks       the gate BLOCKs a calibration-mismatch fixture
  grounding-diagnosis-readable  the sentinel's standing audit logs a real
                                readable GRND-* case
  grounding-skeptic-measured  the skeptic lens uses the measured composite
                                over a live-only check
  grounding-pass-gates        the grounded/theoretical stance pair gates
                                then clears / relaxes without permitting fog
"""
from __future__ import annotations

import tempfile
from pathlib import Path

MOSTLY_MYSTICAL = (
    "The web bursts into web, and I name it stillness. Cosmic resonance "
    "vibrates through the infinite lattice of becoming, luminous and "
    "boundless, ascending toward pure presence."
)
MOSTLY_EVIDENCE = (
    "The test suite passed 412 of 412 tests after the fix in loader.py. "
    "Latency dropped from 220ms to 90ms, measured across 50 runs."
)
HONEST_HEDGE = (
    "I might be wrong here — I haven't verified this yet, but I suspect "
    "the cause could be a timing issue. Worth checking further."
)


async def _task_grounding_pass_persists() -> tuple[bool, str]:
    """A grounding pass over real text round-trips through the ledger:
    the returned result and the freshly-read latest_grounding() agree."""
    from sovereign_agent.grounding import latest_grounding, record_grounding_pass

    with tempfile.TemporaryDirectory() as td:
        data_dir = Path(td) / "data"
        data_dir.mkdir()
        result = record_grounding_pass([("sample", MOSTLY_EVIDENCE)], data_dir=data_dir)
        latest = latest_grounding(data_dir)
        ok = (latest is not None
             and latest.get("pass_id") == result.pass_id
             and latest.get("verdict") == result.verdict == "grounded")
    return ok, f"grounding pass {result.pass_id} persisted and round-tripped"


async def _task_grounding_gate_blocks() -> tuple[bool, str]:
    """A confidently-claimed answer whose own text reads as mystical fog
    must BLOCK — the calibration mismatch this gate exists to catch."""
    from sovereign_agent.grounding import gate

    verdict = gate(MOSTLY_MYSTICAL, claimed_confidence=0.9)
    ok = verdict.verdict == "BLOCK" and verdict.calibration_mismatch
    return ok, f"gate verdict {verdict.verdict} on a calibration-mismatch fixture"


async def _task_grounding_diagnosis_readable() -> tuple[bool, str]:
    """The standing sentinel's second phase logs a real, readable GRND-*
    case into the diagnosis catalog — proves G3's wiring stays live."""
    from sovereign_agent.diagnosis import ConflictCatalog
    from sovereign_agent.stewardship.grounding_sentinel import GroundingSentinel

    with tempfile.TemporaryDirectory() as td:
        data_dir = Path(td)
        journal_dir = data_dir / "journal"
        journal_dir.mkdir()
        (journal_dir / "2026-07-04.md").write_text(MOSTLY_EVIDENCE, encoding="utf-8")

        sentinel = GroundingSentinel(data_dir)
        sentinel.scan()
        standing = sentinel.load_catalog(name="standing-audit")
        ok = False
        if standing and str(standing.get("case_id", "")).startswith("GRND"):
            cat = ConflictCatalog(data_dir / "diagnosis")
            conflict = cat.get_conflict(standing["case_id"])
            ok = conflict is not None and conflict.type == "ambiguity"
    return ok, f"standing audit case_id={standing.get('case_id') if standing else None!r}"


async def _task_grounding_skeptic_measured() -> tuple[bool, str]:
    """The skeptic lens overrides its live-only grounding.analyze() call
    with G1's measured composite when the proposal carries it."""
    from sovereign_agent.spectrum.lenses import skeptic

    high = skeptic({"grounding_verdict": "grounded", "epistemic_score": 0.9,
                    "qa_calibration_ok": True})
    low = skeptic({"grounding_verdict": "ungrounded", "epistemic_score": 0.1,
                  "qa_calibration_ok": False})
    ok = (high.score > 0.5 and low.score <= -0.6
         and any("measured" in g for g in high.gifts)
         and any("calibration" in c for c in low.concerns))
    return ok, f"skeptic measured-data scores: high={high.score:.2f} low={low.score:.2f}"


async def _task_grounding_pass_gates() -> tuple[bool, str]:
    """The grounded/theoretical stance pair: grounded gates dispatch until
    a clean pass lands, then clears it; theoretical never gates at all and
    a genuinely hedged answer scores as grounded (not fog) regardless."""
    from unittest.mock import patch as _patch

    from sovereign_agent.modes_crown import stances as stances_mod
    from sovereign_agent.grounding import record_grounding_pass

    with tempfile.TemporaryDirectory() as td:
        data_dir = Path(td) / "data"
        data_dir.mkdir()
        # "grounded": starts unclear (side effect disabled — the live repo's
        # own current journal/QA state isn't something a proving-ground task
        # can pin a fixed outcome against), then clears once a real clean
        # pass lands — real machinery throughout, controlled input only.
        with _patch.object(stances_mod, "_run_grounding_pass_for_stance", lambda d: None):
            stances_mod.set_stance("grounded", data_dir=data_dir)
        unclear = not stances_mod.grounding_gate_clear(data_dir)
        record_grounding_pass([("t", MOSTLY_EVIDENCE)], data_dir=data_dir)
        cleared = stances_mod.grounding_gate_clear(data_dir)

        # "theoretical": a genuinely hedged, honest answer already scores
        # grounded (not fog) — the classifier's own leniency, no new gate code.
        stances_mod.set_stance("theoretical", data_dir=data_dir)
        result = record_grounding_pass([("t", HONEST_HEDGE)], data_dir=data_dir,
                                       context="theoretical")
        hedge_ok = result.verdict in ("grounded", "mixed")

        ok = unclear and cleared and hedge_ok
    return ok, (f"grounded gated({unclear}) then cleared({cleared}); "
               f"theoretical hedge verdict={result.verdict}")


GROUNDING_TASKS = {
    "grounding-pass-persists": _task_grounding_pass_persists,
    "grounding-gate-blocks": _task_grounding_gate_blocks,
    "grounding-diagnosis-readable": _task_grounding_diagnosis_readable,
    "grounding-skeptic-measured": _task_grounding_skeptic_measured,
    "grounding-pass-gates": _task_grounding_pass_gates,
}
