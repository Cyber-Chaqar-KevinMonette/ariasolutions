"""aria-wellbeing-gate — persistence at the source, real teeth.
(Wellbeing round · W2)

`wellbeing/gate.py` is a brand-new submodule inside the already-live
`wellbeing/` package (W1 applied) — reachable pre-apply via path
extension. `wellbeing/__init__.py`'s export and `companion_tools.py`'s
`ValueReportTool.execute()` persistence hook are IN-PLACE patches —
patch-dependent, skip honestly pre-apply; the apply script re-runs this
file and requires zero skips.
"""
from __future__ import annotations

import inspect

import pytest

HEALTHY_EVENTS = [
    {"flag": "commit-d", "payload": {"message": "fix the loader bug"}},
    {"flag": "presence-note-d", "payload": {}},
]
EMPTY_SESSION_EVENTS = [{"flag": "unrecognized-flag-d", "payload": {}}]


def _patched(obj) -> bool:
    return "wellbeing-gate-d" in inspect.getsource(obj)


# ─── wellbeing/gate.py core ───────────────────────────────────────────────


def test_healthy_session_passes():
    from sovereign_agent.wellbeing.gate import gate

    verdict = gate(HEALTHY_EVENTS)
    assert verdict.verdict == "PASS"


def test_zero_signal_session_blocks():
    from sovereign_agent.wellbeing.gate import gate

    verdict = gate(EMPTY_SESSION_EVENTS)
    assert verdict.verdict == "BLOCK"
    assert verdict.love_grade == "D"


def test_zombie_iv_blocks_even_with_a_good_grade():
    from sovereign_agent.stewardship.msims import Cell, Dimension, ImpactVector, Scale
    from sovereign_agent.wellbeing.gate import gate

    iv = ImpactVector()
    iv.set(Dimension.MENTAL, Scale.MICRO, Cell(value=0.0, confidence=0.9))
    iv.set(Dimension.MENTAL, Scale.MESO, Cell(value=0.0, confidence=0.9))
    iv.set(Dimension.MENTAL, Scale.MACRO, Cell(value=-0.5, confidence=0.9))
    assert iv.is_zombie() is True

    verdict = gate(HEALTHY_EVENTS, iv=iv)
    assert verdict.verdict == "BLOCK"
    assert verdict.impact_is_zombie is True


def test_flourishing_warn_only_when_decision_text_given():
    from sovereign_agent.wellbeing.gate import gate

    lockin_text = "This permanently hardcodes the value everywhere, forever."
    verdict = gate(HEALTHY_EVENTS, decision_text=lockin_text)
    assert verdict.verdict == "WARN"
    assert verdict.flourishing_verdict != "carry-forward"


def test_empty_events_is_honest_pass_not_a_block():
    from sovereign_agent.wellbeing.gate import gate

    verdict = gate([])
    assert verdict.verdict == "PASS"
    assert "nothing to check" in verdict.notes[0]


def test_kill_switch_degrades_to_pass(monkeypatch):
    from sovereign_agent.wellbeing.gate import gate

    monkeypatch.setenv("SOV_NO_WELLBEING_GATE", "1")
    verdict = gate(EMPTY_SESSION_EVENTS)
    assert verdict.verdict == "PASS"
    assert "kill-switched" in verdict.notes[0]


# ─── companion_tools.py wiring (patch-dependent) ──────────────────────────


@pytest.mark.asyncio
async def test_value_report_tool_persists_a_real_ledger_entry(monkeypatch):
    from sovereign_agent.tools import companion_tools

    if not _patched(companion_tools.ValueReportTool.execute):
        pytest.skip("pre-apply: companion_tools.py persistence hook not yet patched")
    from sovereign_agent.wellbeing import latest_wellbeing

    monkeypatch.setattr(companion_tools, "_load_recent_events_for_report",
                        lambda window: HEALTHY_EVENTS)
    tool = companion_tools.ValueReportTool()
    args = companion_tools._ValueReportArgs()
    result = await tool.execute(args, trace_id="t1")
    assert result.ok is True

    latest = latest_wellbeing()
    assert latest is not None
    assert latest["accomplished_count"] >= 1


@pytest.mark.asyncio
async def test_value_report_tool_still_returns_the_report_unchanged(monkeypatch):
    """The persistence hook must never change what the tool actually
    returns to its caller — best-effort, additive only."""
    from sovereign_agent.tools import companion_tools

    if not _patched(companion_tools.ValueReportTool.execute):
        pytest.skip("pre-apply: companion_tools.py persistence hook not yet patched")
    monkeypatch.setattr(companion_tools, "_load_recent_events_for_report",
                        lambda window: HEALTHY_EVENTS)
    tool = companion_tools.ValueReportTool()
    args = companion_tools._ValueReportArgs()
    result = await tool.execute(args, trace_id="t1")
    assert result.ok is True
    assert "overall_grade" in result.output
    assert "accomplished" in result.output


@pytest.mark.asyncio
async def test_value_report_tool_persistence_failure_never_breaks_the_tool_call(monkeypatch):
    from sovereign_agent.tools import companion_tools

    if not _patched(companion_tools.ValueReportTool.execute):
        pytest.skip("pre-apply: companion_tools.py persistence hook not yet patched")
    import sovereign_agent.wellbeing as wellbeing_mod

    def _boom(*a, **k):
        raise RuntimeError("simulated ledger failure")

    monkeypatch.setattr(wellbeing_mod, "record_wellbeing_pass", _boom)
    monkeypatch.setattr(companion_tools, "_load_recent_events_for_report",
                        lambda window: HEALTHY_EVENTS)
    tool = companion_tools.ValueReportTool()
    args = companion_tools._ValueReportArgs()
    result = await tool.execute(args, trace_id="t1")
    assert result.ok is True  # must not raise/fail despite the ledger exploding


# ─── wellbeing/__init__.py export (patch-dependent) ───────────────────────


def test_wellbeing_init_exports_the_gate():
    import sovereign_agent.wellbeing as wellbeing_mod

    if not _patched(wellbeing_mod):
        pytest.skip("pre-apply: wellbeing/__init__.py not yet patched")
    assert hasattr(wellbeing_mod, "gate")
    assert hasattr(wellbeing_mod, "WellbeingGateVerdict")
