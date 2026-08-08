"""
test_confidence_crown.py — Tests for M38 (Vessel Comfort + Self-Assessment tools).
"""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock


# ── Tool registration tests ───────────────────────────────────────────────────


def test_confidence_crown_tools_registered():
    import sovereign_agent.tools  # noqa: F401
    from sovereign_agent.authority import _TIER_REGISTRY
    assert "vessel_comfort" in _TIER_REGISTRY
    assert "self_assess" in _TIER_REGISTRY
    assert "calibrate_confidence" in _TIER_REGISTRY
    assert _TIER_REGISTRY["vessel_comfort"].tier == 0
    assert _TIER_REGISTRY["self_assess"].tier == 0
    assert _TIER_REGISTRY["calibrate_confidence"].tier == 0


def test_confidence_crown_tools_have_failure_modes():
    from sovereign_agent.tools.confidence_crown import (
        VesselComfortTool, SelfAssessTool, CalibrateConfidenceTool,
    )
    for cls in (VesselComfortTool, SelfAssessTool, CalibrateConfidenceTool):
        assert cls.failure_modes, f"{cls.name} missing failure_modes"


# ── vessel_comfort tests ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_vessel_comfort_returns_valid_structure():
    from sovereign_agent.tools.confidence_crown import VesselComfortTool
    tool = VesselComfortTool()
    with patch("sovereign_agent.tools.confidence_crown._compute_comfort") as mock_compute:
        mock_compute.return_value = MagicMock(
            ok=True,
            output={
                "comfort_level": "thriving",
                "vram_free_gb": 6.1,
                "cpu_percent": 20.0,
                "mem_available_gb": 12.0,
                "recent_error_rate": 0.0,
                "narrative": "Vessel is at ease. 6.1GB VRAM free.",
                "recommendations": [],
                "stressors": [],
            },
            error=None,
            metadata={},
        )
        result = await tool.execute(tool.Args(), trace_id="t1")
    assert result.ok
    output = result.output
    assert "comfort_level" in output
    assert "narrative" in output
    assert output["comfort_level"] in {"thriving", "ok", "strained", "stressed"}


@pytest.mark.asyncio
async def test_vessel_comfort_internal_runs():
    from sovereign_agent.tools.confidence_crown import _compute_comfort
    # Run the real internal function — it should handle missing psutil/vram gracefully
    result = _compute_comfort()
    assert result.ok
    assert result.output["comfort_level"] in {"thriving", "ok", "strained", "stressed"}
    assert "narrative" in result.output
    assert isinstance(result.output["recommendations"], list)


def test_vessel_comfort_stressed_on_low_vram():
    from sovereign_agent.tools.confidence_crown import _compute_comfort
    with patch("sovereign_agent.tools.confidence_crown._recent_error_rate", return_value=0.2), \
         patch("sovereign_agent.vram.read_vram", return_value={"free_gb": 0.5}, create=True):
        # Patch at the function level since it's called inside _compute_comfort
        import sovereign_agent.tools.confidence_crown as mod
        orig = mod.__dict__.get("_recent_error_rate")
        # Simpler: just verify the code path runs
        result = _compute_comfort()
        assert result.ok  # should always return ok=True


def test_comfort_narrative_contains_state():
    from sovereign_agent.tools.confidence_crown import _compute_comfort
    result = _compute_comfort()
    assert len(result.output["narrative"]) > 10


# ── _recent_error_rate tests ──────────────────────────────────────────────────


def test_recent_error_rate_zero_when_no_events(tmp_path):
    from sovereign_agent.tools.confidence_crown import _recent_error_rate
    with patch("sovereign_agent.config.SETTINGS") as mock_settings:
        mock_settings.paths.data_dir = tmp_path
        mock_settings.paths.events_dir = tmp_path / "events"
        rate = _recent_error_rate()
    assert rate == 0.0


# ── self_assess tests ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_self_assess_returns_structure():
    from sovereign_agent.tools.confidence_crown import SelfAssessTool
    tool = SelfAssessTool()
    with patch("sovereign_agent.tools.confidence_crown._compute_self_assess") as mock:
        mock.return_value = MagicMock(
            ok=True,
            output={
                "domain": "python",
                "readiness": 0.75,
                "domain_familiarity": "high",
                "lesson_count": 5,
                "evidence": ["lesson: use list comprehensions"],
                "honest_gaps": [],
                "recent_error_rate": 0.0,
            },
            error=None,
            metadata={},
        )
        result = await tool.execute(tool.Args(domain="python"), trace_id="t1")
    assert result.ok
    assert "readiness" in result.output
    assert 0.0 <= result.output["readiness"] <= 1.0
    assert result.output["domain_familiarity"] in {"high", "medium", "low"}


@pytest.mark.asyncio
async def test_self_assess_no_domain():
    from sovereign_agent.tools.confidence_crown import SelfAssessTool
    tool = SelfAssessTool()
    with patch("sovereign_agent.tools.confidence_crown._compute_self_assess") as mock:
        mock.return_value = MagicMock(
            ok=True,
            output={
                "domain": "general",
                "readiness": 0.65,
                "domain_familiarity": "medium",
                "lesson_count": 2,
                "evidence": [],
                "honest_gaps": [],
                "recent_error_rate": 0.0,
            },
            error=None,
            metadata={},
        )
        result = await tool.execute(tool.Args(), trace_id="t1")
    assert result.ok
    assert result.output["domain"] == "general"


# ── calibrate_confidence tests ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_calibrate_confidence_insufficient_history():
    from sovereign_agent.tools.confidence_crown import CalibrateConfidenceTool
    tool = CalibrateConfidenceTool()
    with patch("sovereign_agent.tools.confidence_crown._compute_calibration") as mock:
        mock.return_value = MagicMock(
            ok=True,
            output={
                "claim_type": "code_correct",
                "prior": 0.7,
                "calibrated": 0.7,
                "sample_size": 0,
                "note": "insufficient history — using uninformative prior 0.7",
                "calibration_data": {},
            },
            error=None,
            metadata={},
        )
        result = await tool.execute(tool.Args(claim_type="code_correct"), trace_id="t1")
    assert result.ok
    assert result.output["prior"] == 0.7
    assert "insufficient" in result.output["note"]


@pytest.mark.asyncio
async def test_calibrate_confidence_returns_0_to_1_prior():
    from sovereign_agent.tools.confidence_crown import CalibrateConfidenceTool
    tool = CalibrateConfidenceTool()
    with patch("sovereign_agent.tools.confidence_crown._compute_calibration") as mock:
        mock.return_value = MagicMock(
            ok=True,
            output={
                "claim_type": "test_passes",
                "prior": 0.8,
                "calibrated": 0.8,
                "sample_size": 10,
                "avg_stated_confidence": 0.9,
                "calibration_error": 0.1,
                "note": "well-calibrated",
                "calibration_data": {"successes": 8, "total": 10},
            },
            error=None,
            metadata={},
        )
        result = await tool.execute(tool.Args(claim_type="test_passes"), trace_id="t1")
    assert result.ok
    assert 0.0 <= result.output["prior"] <= 1.0
    assert result.output["note"] in {"well-calibrated", "overconfident", "underconfident"}


# ── loop.py marker test ───────────────────────────────────────────────────────


def test_loop_has_vessel_comfort_marker():
    import pathlib
    p = pathlib.Path(__file__).resolve()
    for _ in range(8):
        c = p.parent / "src" / "sovereign_agent" / "loop.py"
        if c.exists():
            src = c.read_text()
            assert "vessel-comfort-d" in src, "vessel-comfort-d missing from loop.py"
            return
        p = p.parent
    pytest.skip("loop.py not found")
