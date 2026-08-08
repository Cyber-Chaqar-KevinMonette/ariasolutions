"""proving_ground/quality_wing.py — the quality wing of the proving ground.
(Quality round · Q5 · quality-tribunal-d)

Five scored tasks for the Q1-Q4 machinery — the stick before any tuning,
same discipline as every other wing: real machinery, mechanical scorers,
no LLM judge; a task crash is a FAIL, never a run crash (the runner
guarantees that).

  hardening-persists    a quality pass round-trips through the ledger
  gate-blocks-bad        the gate BLOCKs a known-bad fixture
  diagnosis-readable     log_to_diagnosis returns a real, readable case
                          (proves the Q3 bug fix stayed fixed)
  artisan-measured        the artisan lens uses the measured score over prose
  quality-pass-gates      the quality-pass stance gates then clears dispatch
"""
from __future__ import annotations

import tempfile
from pathlib import Path


async def _task_hardening_persists() -> tuple[bool, str]:
    """A quality pass over a real file round-trips through the ledger:
    the returned result and the freshly-read latest_quality() agree."""
    from sovereign_agent.quality import latest_quality, record_quality_pass

    with tempfile.TemporaryDirectory() as td:
        data_dir = Path(td) / "data"
        data_dir.mkdir()
        import sovereign_agent.qa.hardening as hardening_mod

        target = Path(hardening_mod.__file__)
        result = record_quality_pass([target], data_dir=data_dir)
        latest = latest_quality(data_dir)
        ok = (latest is not None
             and latest.get("pass_id") == result.pass_id
             and abs(latest.get("value", -1.0) - result.value) < 0.01
             and len(latest.get("files", [])) == 1)
    return ok, f"quality pass {result.pass_id} persisted and round-tripped"


async def _task_gate_blocks_bad() -> tuple[bool, str]:
    """A file with no type hints, no docstring, and a referencing test
    missing fails a real weight-≥8 hardening check — the gate must BLOCK,
    never silently PASS a known-bad fixture."""
    from sovereign_agent.quality import gate

    with tempfile.TemporaryDirectory() as td:
        bad = Path(td) / "bad_module.py"
        bad.write_text("def f(a):\n    return a\n", encoding="utf-8")
        verdict = gate([bad])
        ok = verdict.verdict == "BLOCK" and not verdict.critical_ok
    return ok, f"gate verdict {verdict.verdict} on a known-bad fixture"


async def _task_diagnosis_readable() -> tuple[bool, str]:
    """The Q3 bug fix stays fixed: log_to_diagnosis() returns a real,
    readable case (not None, not swallowed by an invalid CONFLICT_TYPES
    entry) and the catalog actually holds it."""
    from sovereign_agent.diagnosis import ConflictCatalog
    from sovereign_agent.tribunal import convene
    from sovereign_agent.tribunal.tribunal import log_to_diagnosis

    with tempfile.TemporaryDirectory() as td:
        data_dir = Path(td)
        verdict = convene({"text": "a small, reversible, well-tested change"},
                          include_kernel=False)
        case_id = log_to_diagnosis({"change": "proving-ground check"}, verdict,
                                   data_dir)
        cat = ConflictCatalog(data_dir / "diagnosis")
        conflict = cat.get_conflict(case_id) if case_id else None
        ok = (case_id is not None and case_id.startswith("TRIB")
             and conflict is not None and conflict.type == "ambiguity")
    return ok, f"log_to_diagnosis returned {case_id!r}, a real readable case"


async def _task_artisan_measured() -> tuple[bool, str]:
    """The artisan lens overrides its prose heuristic with a measured
    quality score when one is present in the proposal."""
    from sovereign_agent.spectrum.lenses import artisan

    high = artisan({"quality_score": 95.0, "hardening_critical_ok": True})
    low = artisan({"quality_score": 15.0, "hardening_critical_ok": False})
    ok = (high.score > 0.5 and high.stance in ("support", "champion")
         and low.score <= -0.6 and any("critical" in c for c in low.concerns))
    return ok, f"artisan measured-data scores: high={high.score:.2f} low={low.score:.2f}"


async def _task_quality_pass_gates() -> tuple[bool, str]:
    """The quality-pass stance gates dispatch until a clean pass lands,
    then clears it — end to end, through set_stance/quality_gate_clear.

    The stance's own entry side effect scores whatever the LIVE repo's
    git diff happens to be at the moment this task runs — real, but not
    something a proving-ground task can assert a fixed outcome against
    (the diff varies run to run). So the side effect is disabled here
    only to make the "starts unclear" half deterministic; the "clears
    once a real pass lands" half then runs an actual `record_quality_pass`
    — real machinery throughout, just with a controlled input instead of
    whatever's un-committed in the working tree right now."""
    from unittest.mock import patch as _patch

    from sovereign_agent.modes_crown import stances as stances_mod
    from sovereign_agent.quality import latest_quality, record_quality_pass

    with tempfile.TemporaryDirectory() as td:
        data_dir = Path(td) / "data"
        data_dir.mkdir()
        with _patch.object(stances_mod, "_run_quality_pass_for_stance",
                           lambda data_dir: None):
            stances_mod.set_stance("quality-pass", data_dir=data_dir)
        unclear = not stances_mod.quality_gate_clear(data_dir)

        record_quality_pass([], data_dir=data_dir)
        cleared = stances_mod.quality_gate_clear(data_dir)
        latest = latest_quality(data_dir)
        ok = unclear and cleared and latest is not None
    return ok, f"gated before a pass (unclear={unclear}), cleared after (cleared={cleared})"


QUALITY_TASKS = {
    "quality-hardening-persists": _task_hardening_persists,
    "quality-gate-blocks-bad": _task_gate_blocks_bad,
    "quality-diagnosis-readable": _task_diagnosis_readable,
    "quality-artisan-measured": _task_artisan_measured,
    "quality-pass-gates": _task_quality_pass_gates,
}
