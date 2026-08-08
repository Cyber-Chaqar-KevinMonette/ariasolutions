"""test_eval_crown.py — Tests for M49 (Eval Crown)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── _compute_metrics helpers ──────────────────────────────────────────────────


def test_count_atoms_returns_int():
    from sovereign_agent.tools.eval_tools import _count_atoms
    mock_conn = MagicMock()
    mock_conn.execute.return_value.fetchone.return_value = (5,)
    with patch("sovereign_agent.tools.eval_tools.open_atoms_db", return_value=mock_conn):
        result = _count_atoms("hypothesis")
    assert result == 5


def test_count_atoms_returns_zero_on_error():
    from sovereign_agent.tools.eval_tools import _count_atoms
    with patch("sovereign_agent.tools.eval_tools.open_atoms_db", side_effect=Exception("db error")):
        result = _count_atoms("hypothesis")
    assert result == 0


def test_count_lessons_returns_int():
    from sovereign_agent.tools.eval_tools import _count_lessons
    mock_conn = MagicMock()
    mock_conn.execute.return_value.fetchone.return_value = (3,)
    with patch("sovereign_agent.tools.eval_tools.open_atoms_db", return_value=mock_conn):
        result = _count_lessons()
    assert result == 3


def test_count_git_commits_returns_int():
    from sovereign_agent.tools.eval_tools import _count_git_commits
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.stdout = "abc123 commit 1\ndef456 commit 2\n"
        mock_run.return_value.returncode = 0
        result = _count_git_commits(7)
    assert result == 2


def test_count_git_commits_returns_zero_on_error():
    from sovereign_agent.tools.eval_tools import _count_git_commits
    with patch("subprocess.run", side_effect=Exception("git error")):
        result = _count_git_commits(7)
    assert result == 0


def test_score_metrics_exceptional():
    from sovereign_agent.tools.eval_tools import _score_metrics
    m = {
        "commits": 10, "lessons_written": 5, "hypotheses_formed": 5,
        "hypothesis_confirm_rate": 0.9, "experiences_logged": 5,
        "breakthroughs": 2, "hypotheses_confirmed": 4, "session_briefs": 3,
    }
    score, band = _score_metrics(m)
    assert score >= 80
    assert band == "exceptional"


def test_score_metrics_baseline():
    from sovereign_agent.tools.eval_tools import _score_metrics
    m = {
        "commits": 0, "lessons_written": 0, "hypotheses_formed": 0,
        "hypothesis_confirm_rate": 0.0, "experiences_logged": 0,
        "breakthroughs": 0, "hypotheses_confirmed": 0, "session_briefs": 0,
    }
    score, band = _score_metrics(m)
    assert score == 0
    assert band == "baseline"


def test_score_metrics_capped_at_100():
    from sovereign_agent.tools.eval_tools import _score_metrics
    m = {
        "commits": 100, "lessons_written": 100, "hypotheses_formed": 100,
        "hypothesis_confirm_rate": 1.0, "experiences_logged": 100,
        "breakthroughs": 100, "hypotheses_confirmed": 100, "session_briefs": 100,
    }
    score, _ = _score_metrics(m)
    assert score <= 100


# ── eval_session tool tests ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_eval_session_returns_ok():
    from sovereign_agent.tools.eval_tools import EvalSessionTool
    tool = EvalSessionTool()
    fake_metrics = {
        "period_days": 7, "since": "2026-06-13",
        "commits": 3, "lessons_written": 2,
        "hypotheses_formed": 1, "hypotheses_results": 0, "hypotheses_confirmed": 0,
        "hypothesis_confirm_rate": 0.0, "experiences_logged": 5,
        "avg_surprise_level": 0.4, "breakthroughs": 0,
        "objectives_written": 2, "session_briefs": 1,
    }
    with patch("asyncio.to_thread", new=AsyncMock(return_value=fake_metrics)):
        result = await tool.execute(tool.Args(days=7), trace_id="t1")
    assert result.ok
    assert "score" in result.output
    assert "band" in result.output
    assert "interpretation" in result.output
    assert result.output["commits"] == 3


@pytest.mark.asyncio
async def test_eval_session_interpretation_contains_commits():
    from sovereign_agent.tools.eval_tools import EvalSessionTool
    tool = EvalSessionTool()
    fake_metrics = {
        "period_days": 7, "since": "2026-06-13",
        "commits": 5, "lessons_written": 3,
        "hypotheses_formed": 2, "hypotheses_results": 1, "hypotheses_confirmed": 1,
        "hypothesis_confirm_rate": 1.0, "experiences_logged": 4,
        "avg_surprise_level": 0.6, "breakthroughs": 1,
        "objectives_written": 0, "session_briefs": 2,
    }
    with patch("asyncio.to_thread", new=AsyncMock(return_value=fake_metrics)):
        result = await tool.execute(tool.Args(days=7), trace_id="t1")
    assert result.ok
    assert "5 commits" in result.output["interpretation"]


# ── eval_history tool tests ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_eval_history_returns_weekly_list():
    from sovereign_agent.tools.eval_tools import EvalHistoryTool
    tool = EvalHistoryTool()

    call_count = [0]
    def _fake_thread(fn, *args, **kwargs):
        call_count[0] += 1
        return {"week": f"week-{call_count[0]}", "commits": 1, "lessons": 0,
                "hypotheses": 0, "experiences": 0, "breakthroughs": 0}

    with patch("asyncio.to_thread", new=AsyncMock(side_effect=_fake_thread)):
        result = await tool.execute(tool.Args(weeks=3), trace_id="t1")
    assert result.ok
    assert result.output["total_weeks_analyzed"] == 3
    assert len(result.output["weeks"]) == 3


@pytest.mark.asyncio
async def test_eval_history_trend_field_present():
    from sovereign_agent.tools.eval_tools import EvalHistoryTool
    tool = EvalHistoryTool()

    def _fake_thread(fn, *a, **kw):
        return {"week": "this-week", "commits": 2, "lessons": 1,
                "hypotheses": 0, "experiences": 0, "breakthroughs": 0}

    with patch("asyncio.to_thread", new=AsyncMock(side_effect=_fake_thread)):
        result = await tool.execute(tool.Args(weeks=2), trace_id="t1")
    assert result.ok
    assert "trend" in result.output
    assert result.output["trend"] in ("improving", "declining", "stable")


# ── eval_score tool tests ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_eval_score_returns_score():
    from sovereign_agent.tools.eval_tools import EvalScoreTool
    tool = EvalScoreTool()
    fake_metrics = {
        "period_days": 7, "since": "2026-06-13",
        "commits": 2, "lessons_written": 1,
        "hypotheses_formed": 0, "hypotheses_results": 0, "hypotheses_confirmed": 0,
        "hypothesis_confirm_rate": 0.0, "experiences_logged": 3,
        "avg_surprise_level": 0.5, "breakthroughs": 0,
        "objectives_written": 0, "session_briefs": 1,
    }
    with patch("asyncio.to_thread", new=AsyncMock(return_value=fake_metrics)):
        result = await tool.execute(tool.Args(), trace_id="t1")
    assert result.ok
    assert 0 <= result.output["score"] <= 100
    assert result.output["band"] in ("baseline", "early", "building", "strong", "exceptional")
    assert "verdict" in result.output
    assert "key_metrics" in result.output


# ── Tool registration tests ───────────────────────────────────────────────────


def test_eval_tools_registered():
    import sovereign_agent.tools  # noqa: F401
    from sovereign_agent.authority import _TIER_REGISTRY
    assert "eval_session" in _TIER_REGISTRY
    assert "eval_history" in _TIER_REGISTRY
    assert "eval_score" in _TIER_REGISTRY
    for name in ("eval_session", "eval_history", "eval_score"):
        assert _TIER_REGISTRY[name].tier == 0, f"{name} should be T0"


def test_eval_tools_have_failure_modes():
    from sovereign_agent.tools.eval_tools import EvalSessionTool, EvalHistoryTool, EvalScoreTool
    for cls in (EvalSessionTool, EvalHistoryTool, EvalScoreTool):
        assert cls.failure_modes, f"{cls.name} missing failure_modes"


# ── loop marker test ──────────────────────────────────────────────────────────


def test_loop_has_eval_crown_marker():
    import pathlib
    p = pathlib.Path(__file__).resolve()
    for _ in range(8):
        c = p.parent / "src" / "sovereign_agent" / "loop.py"
        if c.exists():
            src = c.read_text()
            assert "eval-crown-d" in src, "eval-crown-d missing from loop.py"
            return
        p = p.parent
    pytest.skip("loop.py not found")
