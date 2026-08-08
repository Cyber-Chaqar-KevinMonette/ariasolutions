"""tools/eval_tools.py — Value Evaluation Metrics (M49).

  eval_session(days=7)      T0 — current-period metrics: commits, lessons, hypotheses, etc.
  eval_history(weeks=4)     T0 — weekly breakdown trend
  eval_score()              T0 — composite 0-100 score + qualitative band
"""
from __future__ import annotations

import asyncio
import json
import subprocess
from datetime import datetime, timezone, timedelta
from typing import Optional

from pydantic import BaseModel, Field

from .base import Tool, ToolResult

try:
    from sovereign_agent.db import open_atoms_db
except ImportError:
    open_atoms_db = None  # type: ignore[assignment]

try:
    from sovereign_agent.config import SETTINGS
except ImportError:
    SETTINGS = None  # type: ignore[assignment]


# ── Metric helpers ────────────────────────────────────────────────────────────


def _count_atoms(atom_type: str, since_iso: Optional[str] = None) -> int:
    try:
        conn = open_atoms_db()
        if since_iso:
            row = conn.execute(
                "SELECT COUNT(*) FROM atoms WHERE type=? AND created_at>=?",
                (atom_type, since_iso),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT COUNT(*) FROM atoms WHERE type=?", (atom_type,)
            ).fetchone()
        return row[0] if row else 0
    except Exception:  # noqa: BLE001
        return 0


def _count_lessons(since_iso: Optional[str] = None) -> int:
    try:
        conn = open_atoms_db()
        if since_iso:
            row = conn.execute(
                "SELECT COUNT(*) FROM lessons WHERE ts>=?", (since_iso,)
            ).fetchone()
        else:
            row = conn.execute("SELECT COUNT(*) FROM lessons").fetchone()
        return row[0] if row else 0
    except Exception:  # noqa: BLE001
        return 0


def _count_confirmed_hypotheses(since_iso: Optional[str] = None) -> int:
    """Count hypothesis-result atoms that indicate confirmation."""
    try:
        conn = open_atoms_db()
        if since_iso:
            rows = conn.execute(
                "SELECT content_ref FROM atoms WHERE type='hypothesis-result' AND created_at>=?",
                (since_iso,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT content_ref FROM atoms WHERE type='hypothesis-result'"
            ).fetchall()
        confirmed = 0
        for (content_ref,) in rows:
            try:
                ref = json.loads(content_ref) if isinstance(content_ref, str) else content_ref
                content_str = ref.get("content", "") if isinstance(ref, dict) else ""
                content = json.loads(content_str) if content_str else {}
                verdict = content.get("verdict", "") or content.get("result", "")
                if "confirm" in str(verdict).lower() or "support" in str(verdict).lower():
                    confirmed += 1
            except Exception:  # noqa: BLE001
                pass
        return confirmed
    except Exception:  # noqa: BLE001
        return 0


def _count_git_commits(days: int) -> int:
    try:
        result = subprocess.run(
            ["git", "log", f"--since={days} days ago", "--oneline"],
            capture_output=True, text=True, timeout=5,
            cwd=str(SETTINGS.paths.data_dir.parent.parent) if SETTINGS else ".",
        )
        return len([l for l in result.stdout.strip().splitlines() if l])
    except Exception:  # noqa: BLE001
        return 0


def _avg_surprise(since_iso: Optional[str] = None) -> float:
    try:
        conn = open_atoms_db()
        if since_iso:
            rows = conn.execute(
                "SELECT content_ref FROM atoms WHERE type='experience' AND created_at>=?",
                (since_iso,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT content_ref FROM atoms WHERE type='experience'"
            ).fetchall()
        levels = []
        for (content_ref,) in rows:
            try:
                ref = json.loads(content_ref) if isinstance(content_ref, str) else content_ref
                content_str = ref.get("content", "") if isinstance(ref, dict) else ""
                content = json.loads(content_str) if content_str else {}
                sl = content.get("surprise_level")
                if sl is not None:
                    levels.append(float(sl))
            except Exception:  # noqa: BLE001
                pass
        return round(sum(levels) / len(levels), 3) if levels else 0.0
    except Exception:  # noqa: BLE001
        return 0.0


def _compute_metrics(days: int) -> dict:
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    commits = _count_git_commits(days)
    lessons = _count_lessons(since)
    hypotheses = _count_atoms("hypothesis", since)
    results = _count_atoms("hypothesis-result", since)
    confirmed = _count_confirmed_hypotheses(since)
    confirm_rate = round(confirmed / results, 3) if results > 0 else 0.0
    experiences = _count_atoms("experience", since)
    avg_surprise = _avg_surprise(since)
    breakthroughs = _count_atoms("breakthrough", since)
    objectives = _count_atoms("objective", since)
    session_briefs = _count_atoms("session-brief", since)
    return {
        "period_days": days,
        "since": since,
        "commits": commits,
        "lessons_written": lessons,
        "hypotheses_formed": hypotheses,
        "hypotheses_results": results,
        "hypotheses_confirmed": confirmed,
        "hypothesis_confirm_rate": confirm_rate,
        "experiences_logged": experiences,
        "avg_surprise_level": avg_surprise,
        "breakthroughs": breakthroughs,
        "objectives_written": objectives,
        "session_briefs": session_briefs,
    }


def _score_metrics(m: dict) -> tuple[int, str]:
    """Return (0-100 score, qualitative band)."""
    score = 0
    # Commits: up to 30 pts (1 pt per commit, capped)
    score += min(30, m["commits"] * 5)
    # Lessons: up to 20 pts
    score += min(20, m["lessons_written"] * 4)
    # Hypotheses: up to 15 pts
    score += min(15, m["hypotheses_formed"] * 3)
    # Confirmation rate: up to 10 pts
    score += int(m["hypothesis_confirm_rate"] * 10)
    # Experiences: up to 10 pts
    score += min(10, m["experiences_logged"] * 2)
    # Breakthroughs: up to 10 pts
    score += min(10, m["breakthroughs"] * 10)
    # Session briefs: up to 5 pts (continuity signal)
    score += min(5, m["session_briefs"] * 2)

    score = min(100, score)
    if score >= 80:
        band = "exceptional"
    elif score >= 60:
        band = "strong"
    elif score >= 40:
        band = "building"
    elif score >= 20:
        band = "early"
    else:
        band = "baseline"
    return score, band


# ── eval_session ──────────────────────────────────────────────────────────────


class _EvalSessionArgs(BaseModel):
    days: int = Field(default=7, ge=1, le=365)


class EvalSessionTool(Tool[_EvalSessionArgs]):
    name = "eval_session"
    tier = 0
    description = (
        "Compute value delivery metrics for the last N days. "
        "Returns: commits, lessons written, hypotheses formed/confirmed, "
        "experiences logged, breakthroughs, and composite score. "
        "Use this to answer 'Is Aria actually getting better and delivering value?'"
    )
    failure_modes = ("db_unavailable", "git_unavailable")
    Args = _EvalSessionArgs

    async def execute(self, args: _EvalSessionArgs, *, trace_id: str) -> ToolResult:  # noqa: ARG002
        try:
            metrics = await asyncio.to_thread(_compute_metrics, args.days)
            score, band = _score_metrics(metrics)
            return ToolResult(ok=True, output={
                **metrics,
                "score": score,
                "band": band,
                "interpretation": (
                    f"Score {score}/100 ({band}). "
                    f"{metrics['commits']} commits, {metrics['lessons_written']} lessons, "
                    f"{metrics['hypothesis_confirm_rate']:.0%} hypothesis confirmation rate "
                    f"over {args.days} days."
                ),
            })
        except Exception as e:  # noqa: BLE001
            return ToolResult(ok=False, error=f"eval_session failed: {e}")


# ── eval_history ──────────────────────────────────────────────────────────────


class _EvalHistoryArgs(BaseModel):
    weeks: int = Field(default=4, ge=1, le=52)


class EvalHistoryTool(Tool[_EvalHistoryArgs]):
    name = "eval_history"
    tier = 0
    description = (
        "Weekly breakdown of value metrics over the last N weeks. "
        "Use this to spot trends: is Aria consistently delivering, "
        "or are there dead weeks? Is the confirmation rate improving?"
    )
    failure_modes = ("db_unavailable",)
    Args = _EvalHistoryArgs

    async def execute(self, args: _EvalHistoryArgs, *, trace_id: str) -> ToolResult:  # noqa: ARG002
        try:
            weekly = []
            for week in range(args.weeks):
                since_days = (week + 1) * 7
                until_days = week * 7
                since = (datetime.now(timezone.utc) - timedelta(days=since_days)).isoformat()
                until = (datetime.now(timezone.utc) - timedelta(days=until_days)).isoformat()
                label = f"week-{week + 1}" if week > 0 else "this-week"

                def _week_metrics(s=since, u=until, lbl=label):
                    try:
                        conn = open_atoms_db()
                        def count(t):
                            r = conn.execute(
                                "SELECT COUNT(*) FROM atoms WHERE type=? AND created_at>=? AND created_at<?",
                                (t, s, u),
                            ).fetchone()
                            return r[0] if r else 0
                        commits = _count_git_commits(7) if lbl == "this-week" else 0
                        lessons = conn.execute(
                            "SELECT COUNT(*) FROM lessons WHERE ts>=? AND ts<?", (s, u)
                        ).fetchone()
                        return {
                            "week": lbl,
                            "commits": commits,
                            "lessons": (lessons[0] if lessons else 0),
                            "hypotheses": count("hypothesis"),
                            "experiences": count("experience"),
                            "breakthroughs": count("breakthrough"),
                        }
                    except Exception:  # noqa: BLE001
                        return {"week": lbl, "error": "db unavailable"}

                w = await asyncio.to_thread(_week_metrics)
                score, band = _score_metrics({
                    "commits": w.get("commits", 0),
                    "lessons_written": w.get("lessons", 0),
                    "hypotheses_formed": w.get("hypotheses", 0),
                    "hypothesis_confirm_rate": 0.0,
                    "experiences_logged": w.get("experiences", 0),
                    "breakthroughs": w.get("breakthroughs", 0),
                    "hypotheses_confirmed": 0,
                    "session_briefs": 0,
                })
                w["score"] = score
                w["band"] = band
                weekly.append(w)

            trend = "improving" if (
                len(weekly) >= 2 and weekly[0].get("score", 0) >= weekly[-1].get("score", 0)
            ) else "declining" if (
                len(weekly) >= 2 and weekly[0].get("score", 0) < weekly[-1].get("score", 0)
            ) else "stable"

            return ToolResult(ok=True, output={
                "weeks": weekly,
                "trend": trend,
                "total_weeks_analyzed": args.weeks,
            })
        except Exception as e:  # noqa: BLE001
            return ToolResult(ok=False, error=f"eval_history failed: {e}")


# ── eval_score ────────────────────────────────────────────────────────────────


class _EvalScoreArgs(BaseModel):
    pass


class EvalScoreTool(Tool[_EvalScoreArgs]):
    name = "eval_score"
    tier = 0
    description = (
        "Composite 0-100 value score for the last 7 days. Fast summary. "
        "Bands: baseline(<20) → early → building → strong → exceptional(80+). "
        "Use this at session start/end for a quick health check."
    )
    failure_modes = ("db_unavailable",)
    Args = _EvalScoreArgs

    async def execute(self, args: _EvalScoreArgs, *, trace_id: str) -> ToolResult:  # noqa: ARG002
        try:
            metrics = await asyncio.to_thread(_compute_metrics, 7)
            score, band = _score_metrics(metrics)
            return ToolResult(ok=True, output={
                "score": score,
                "band": band,
                "key_metrics": {
                    "commits_7d": metrics["commits"],
                    "lessons_7d": metrics["lessons_written"],
                    "hypothesis_confirm_rate": metrics["hypothesis_confirm_rate"],
                    "experiences_7d": metrics["experiences_logged"],
                    "breakthroughs_7d": metrics["breakthroughs"],
                },
                "verdict": (
                    f"Aria is {band} — {score}/100. "
                    + (
                        "Strong delivery. Keep this up."
                        if score >= 60 else
                        "Building momentum. Focus on commits and lessons."
                        if score >= 30 else
                        "Early stage. Log experiences and form hypotheses."
                    )
                ),
            })
        except Exception as e:  # noqa: BLE001
            return ToolResult(ok=False, error=f"eval_score failed: {e}")


__all__ = [
    "EvalSessionTool",
    "EvalHistoryTool",
    "EvalScoreTool",
]
