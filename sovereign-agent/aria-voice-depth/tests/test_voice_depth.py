"""Tests for ARIAVoice depth directive + session-start awareness."""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest


def _repo_root() -> Path:
    here = Path(__file__).resolve().parent
    for _ in range(6):
        if (here / "pyproject.toml").exists():
            return here
        here = here.parent
    raise RuntimeError("repo root not found")


def _voice():
    from sovereign_agent.quantum.voice import voice_directive
    return voice_directive


def test_rich_exploratory_is_expansive():
    vd = _voice()
    d = vd(coherence=0.9, lam=0.1, neg_frac=0.9)
    assert d["verbosity"] >= 7
    assert d["style"] in ("expansive", "maximum")
    assert d["advisory"] is True


def test_committed_low_richness_is_terse():
    vd = _voice()
    d = vd(coherence=0.1, lam=0.95, neg_frac=0.1)
    assert d["verbosity"] <= 3
    assert d["style"] in ("terse", "normal")


def test_verbosity_in_range():
    vd = _voice()
    for c in (0.0, 0.3, 0.7, 1.0):
        for l in (0.0, 0.5, 1.0):
            d = vd(c, l)
            assert 1 <= d["verbosity"] <= 10


def test_neg_frac_dominates_when_given():
    vd = _voice()
    high = vd(coherence=0.2, lam=0.5, neg_frac=0.95)
    low = vd(coherence=0.2, lam=0.5, neg_frac=0.05)
    assert high["verbosity"] > low["verbosity"]


def test_session_portrait_includes_voice_directive():
    # session_portrait is patched to add voice_directive + globe coherence (session-start awareness)
    from sovereign_agent.tools.session_portrait_tool import SessionPortraitTool
    t = SessionPortraitTool()
    res = asyncio.run(t.execute(t.Args(), trace_id="t"))
    assert res.ok
    assert "voice_directive" in res.output
