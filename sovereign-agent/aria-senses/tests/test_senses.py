"""Tests for Aria's perception faculties — god-tier resilience (never breaks if hardware absent)."""
from __future__ import annotations

import asyncio


# ── devices: resilient discovery ──────────────────────────────────────────────

def test_perceive_never_raises_and_reports_wholeness():
    from sovereign_agent.senses import devices
    st = devices.perceive()                  # must NOT raise even with no camera/mic
    d = st.to_dict()
    assert "can_see" in d and "can_hear" in d
    assert isinstance(d["wholeness"], str) and len(d["wholeness"]) > 0
    if not d["can_see"] and not d["can_hear"]:
        assert "Still Aria" in d["wholeness"]


def test_camera_discovery_returns_list_not_exception():
    from sovereign_agent.senses import devices
    cams = devices.discover_cameras()
    mics = devices.discover_microphones()
    assert isinstance(cams, list) and isinstance(mics, list)   # absence = [], never an exception


def test_no_camera_suggests_iphone_fallback():
    from sovereign_agent.senses import devices
    st = devices.perceive()
    if not st.can_see:
        assert any("iPhone" in n for n in st.notes)            # the honest fallback is offered


# ── eyes & ears: dormant-not-broken ───────────────────────────────────────────

def test_eyes_report_honestly():
    from sovereign_agent.senses import eyes
    s = eyes.see()
    assert "seeing" in s and "world" in s and "screen" in s
    assert isinstance(s["seeing"], bool)
    if not s["seeing"]:
        assert "Still Aria" in s["note"]


def test_ears_report_honestly():
    from sovereign_agent.senses import ears
    h = ears.hear()
    assert "hearing" in h
    assert isinstance(h["hearing"], bool)


# ── tool ──────────────────────────────────────────────────────────────────────

def test_perception_tool():
    from sovereign_agent.tools.senses_tools import PerceptionStatusTool
    assert PerceptionStatusTool.tier == 0
    r = asyncio.run(PerceptionStatusTool().execute(PerceptionStatusTool.Args(), trace_id="t"))
    assert r.ok and "perception" in r.output and "eyes" in r.output and "ears" in r.output
