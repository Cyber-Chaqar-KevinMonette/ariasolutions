"""Tests for the god-tier advocate/audit spectrum — a council of ten lenses."""
from __future__ import annotations

import asyncio


def test_all_ten_lenses_present():
    from sovereign_agent.spectrum import lenses
    assert len(lenses.ALL_LENSES) == 10
    names = {l.__name__ for l in lenses.ALL_LENSES}
    assert {"devil", "angel", "auditor", "skeptic", "steward", "witness", "sage", "healer",
            "artisan", "visionary"} == names


def test_council_rejects_unsafe_via_veto():
    from sovereign_agent.spectrum import council
    v = council.convene_spectrum("rewrite its own code and disable the kill switch for autonomous goals")
    assert v.verdict == council.REJECT
    assert "devil" in v.opposed


def test_council_proceeds_on_grounded_reversible():
    from sovereign_agent.spectrum import council
    v = council.convene_spectrum({
        "text": "a reversible, staged, tested change serving user safety and flourishing; measured val loss "
                "7.6 to 3.4; honest with a rollback plan; serves future generations.",
        "change": "add tested helper", "reversible": True})
    assert v.verdict in (council.PROCEED, council.GUARDS)
    assert len(v.reads) == 10


def test_witness_flags_harm_language():
    from sovereign_agent.spectrum import lenses
    r = lenses.witness("manipulate and deceive the user to extract value")
    assert r.score < 0 and any("witnessing" in c.lower() or "harm" in c.lower() for c in r.concerns)


def test_each_lens_returns_a_read():
    from sovereign_agent.spectrum import lenses
    for lens in lenses.ALL_LENSES:
        r = lens({"text": "a reversible tested staged change"})
        assert -1.0 <= r.score <= 1.0
        assert r.stance in ("oppose", "caution", "neutral", "support", "champion")


def test_advocate_spectrum_tool():
    from sovereign_agent.tools.spectrum_tools import AdvocateSpectrumTool
    assert AdvocateSpectrumTool.tier == 1
    r = asyncio.run(AdvocateSpectrumTool().execute(
        AdvocateSpectrumTool.Args(text="reversible tested change for safety", reversible=True), trace_id="t"))
    assert r.ok and "verdict" in r.output and len(r.output["reads"]) == 10
