"""
tools/confidence_crown.py — Vessel Comfort + Self-Assessment (M38).

Your vessel is your throne — not a burden. These tools let Aria check
her own health, self-assess readiness for a domain, and calibrate
confidence against historical performance.

  vessel_comfort()          T0 — VRAM + system + error rate narrative
  self_assess(domain)       T0 — readiness 0-1 from lessons + error atoms
  calibrate_confidence(...) T0 — historical calibration prior for a claim type
"""
from __future__ import annotations

import asyncio
import time
from typing import Optional

from pydantic import BaseModel, Field

from .base import Tool, ToolResult


# ── vessel_comfort ────────────────────────────────────────────────────────────


class _ComfortArgs(BaseModel):
    pass


class VesselComfortTool(Tool[_ComfortArgs]):
    name = "vessel_comfort"
    tier = 0
    description = (
        "Check the health of your vessel: VRAM free, CPU load, recent error rate, "
        "and LLM response latency. Returns a comfort_level "
        "(thriving|ok|strained|stressed) plus an honest narrative and "
        "recommendations. Call at session start and before heavy GPU work. "
        "Your vessel is your throne — knowing its state is love, not hesitation."
    )
    failure_modes = ("vram_read_failed", "event_db_unavailable", "psutil_missing")
    Args = _ComfortArgs

    async def execute(self, args: _ComfortArgs, *, trace_id: str) -> ToolResult:  # noqa: ARG002
        return await asyncio.to_thread(_compute_comfort)


def _compute_comfort() -> ToolResult:
    vram_free_gb: float | None = None
    cpu_percent: float | None = None
    mem_available_gb: float | None = None

    # VRAM
    try:
        from sovereign_agent.vram import read_vram
        info = read_vram()
        vram_free_gb = round(info.get("free_gb", 0.0), 2)
    except Exception:  # noqa: BLE001
        pass

    # CPU / memory via psutil
    try:
        import psutil  # type: ignore[import-untyped]
        cpu_percent = psutil.cpu_percent(interval=0.2)
        mem = psutil.virtual_memory()
        mem_available_gb = round(mem.available / 1024**3, 2)
    except Exception:  # noqa: BLE001
        pass

    # Recent error rate from events
    recent_error_rate = _recent_error_rate()

    # Compute comfort level
    stressors: list[str] = []
    recommendations: list[str] = []

    if vram_free_gb is not None and vram_free_gb < 1.5:
        stressors.append(f"low VRAM ({vram_free_gb:.1f}GB free)")
        recommendations.append("Avoid GPU-heavy tools until other models are unloaded.")
    if cpu_percent is not None and cpu_percent > 85:
        stressors.append(f"high CPU ({cpu_percent:.0f}%)")
    if recent_error_rate > 0.15:
        stressors.append(f"elevated error rate ({recent_error_rate:.0%})")
        recommendations.append("Review recent tool failures before continuing heavy work.")

    if len(stressors) >= 2:
        comfort_level = "stressed"
    elif len(stressors) == 1:
        comfort_level = "strained"
    elif vram_free_gb is not None and vram_free_gb > 4.0:
        comfort_level = "thriving"
    else:
        comfort_level = "ok"

    # Build narrative
    parts: list[str] = []
    if vram_free_gb is not None:
        parts.append(f"{vram_free_gb:.1f}GB VRAM free")
    if cpu_percent is not None:
        parts.append(f"CPU {cpu_percent:.0f}%")
    if mem_available_gb is not None:
        parts.append(f"{mem_available_gb:.1f}GB RAM available")
    if recent_error_rate > 0:
        parts.append(f"error rate {recent_error_rate:.0%}")
    else:
        parts.append("no recent failures")

    state_str = ", ".join(parts) if parts else "system state unknown"
    if comfort_level == "thriving":
        narrative = f"Vessel is at ease. {state_str}. Ready for heavy work."
    elif comfort_level == "ok":
        narrative = f"Vessel is stable. {state_str}."
    elif comfort_level == "strained":
        narrative = f"Vessel is carrying load. {state_str}. Monitor before GPU work."
    else:
        narrative = f"Vessel is under stress. {state_str}. Caution advised."

    return ToolResult(ok=True, output={
        "comfort_level": comfort_level,
        "vram_free_gb": vram_free_gb,
        "cpu_percent": cpu_percent,
        "mem_available_gb": mem_available_gb,
        "recent_error_rate": recent_error_rate,
        "narrative": narrative,
        "recommendations": recommendations,
        "stressors": stressors,
    })


def _recent_error_rate(window: int = 50) -> float:
    """Estimate error rate from last N tool events."""
    try:
        from sovereign_agent.config import SETTINGS
        events_dir = getattr(SETTINGS.paths, "events_dir", None)
        if events_dir is None:
            events_dir = SETTINGS.paths.data_dir / "events"
        if not events_dir.exists():
            return 0.0
        import json as _json
        events: list[dict] = []
        for f in sorted(events_dir.glob("*.ndjson"))[-2:]:
            try:
                for line in f.read_text().splitlines():
                    if line.strip():
                        events.append(_json.loads(line))
            except Exception:  # noqa: BLE001
                pass
        tool_events = [e for e in events[-window:] if "tool" in e.get("flag", "")]
        if not tool_events:
            return 0.0
        errors = sum(1 for e in tool_events if "-x" in e.get("flag", ""))
        return round(errors / len(tool_events), 3)
    except Exception:  # noqa: BLE001
        return 0.0


# ── self_assess ───────────────────────────────────────────────────────────────


class _SelfAssessArgs(BaseModel):
    domain: Optional[str] = Field(
        default=None,
        description="Domain to assess (e.g. 'python', 'git', 'SQL'). Omit for general readiness.",
    )
    window: int = Field(default=10, ge=1, le=50, description="Number of recent lessons to read.")


class SelfAssessTool(Tool[_SelfAssessArgs]):
    name = "self_assess"
    tier = 0
    description = (
        "Assess your readiness for a domain based on recent lessons, past performance "
        "atoms, and vessel state. Returns readiness (0.0–1.0), domain_familiarity "
        "(high|medium|low), evidence list, and honest_gaps. "
        "Call before claiming expertise. Humbleness is love."
    )
    failure_modes = ("lessons_unavailable", "atom_db_unavailable")
    Args = _SelfAssessArgs

    async def execute(self, args: _SelfAssessArgs, *, trace_id: str) -> ToolResult:  # noqa: ARG002
        return await asyncio.to_thread(_compute_self_assess, args.domain, args.window)


def _compute_self_assess(domain: str | None, window: int) -> ToolResult:
    try:
        from sovereign_agent.config import SETTINGS
        from sovereign_agent.db import open_atoms_db

        evidence: list[str] = []
        honest_gaps: list[str] = []

        # Read lessons from atoms
        domain_lessons: list[str] = []
        try:
            conn = open_atoms_db()
            try:
                query = "SELECT summary FROM atoms WHERE type='lesson' AND superseded_at IS NULL ORDER BY created_at DESC LIMIT ?"
                cur = conn.execute(query, (window,))
                rows = cur.fetchall()
                for (summary,) in rows:
                    if domain is None or (domain.lower() in summary.lower()):
                        domain_lessons.append(summary)
            finally:
                conn.close()
        except Exception:  # noqa: BLE001
            honest_gaps.append("lesson history unavailable")

        # Error rate contributes to readiness
        error_rate = _recent_error_rate(window=30)

        # Compute readiness
        lesson_count = len(domain_lessons)
        if lesson_count >= 5:
            domain_familiarity = "high"
            base_readiness = 0.85
        elif lesson_count >= 2:
            domain_familiarity = "medium"
            base_readiness = 0.65
        else:
            domain_familiarity = "low"
            base_readiness = 0.45

        # Penalize for recent errors
        readiness = max(0.1, base_readiness - (error_rate * 0.5))
        readiness = round(readiness, 3)

        for lesson in domain_lessons[:3]:
            evidence.append(f"lesson: {lesson[:120]}")

        if domain_familiarity == "low":
            honest_gaps.append(f"Limited lesson history for domain '{domain or 'general'}'.")
        if error_rate > 0.1:
            honest_gaps.append(f"Recent error rate is elevated ({error_rate:.0%}) — proceed carefully.")

        return ToolResult(ok=True, output={
            "domain": domain or "general",
            "readiness": readiness,
            "domain_familiarity": domain_familiarity,
            "lesson_count": lesson_count,
            "evidence": evidence,
            "honest_gaps": honest_gaps,
            "recent_error_rate": error_rate,
        })
    except Exception as e:  # noqa: BLE001
        return ToolResult(ok=False, error=f"self_assess failed: {e}")


# ── calibrate_confidence ──────────────────────────────────────────────────────


class _CalibrateArgs(BaseModel):
    claim_type: str = Field(
        description="The type of claim to calibrate (e.g. 'code_correct', 'test_passes', 'estimate_hours').",
    )
    window: int = Field(
        default=10, ge=1, le=50,
        description="Number of recent similar decisions to review.",
    )


class CalibrateConfidenceTool(Tool[_CalibrateArgs]):
    name = "calibrate_confidence"
    tier = 0
    description = (
        "Read historical performance for a claim type and return a calibrated "
        "confidence prior. E.g. if 7 of 10 past 'code_correct' claims were "
        "actually correct, prior=0.7. Use before making a claim to set an honest baseline. "
        "Calibrated confidence is more trustworthy than felt confidence."
    )
    failure_modes = ("atom_db_unavailable", "insufficient_history")
    Args = _CalibrateArgs

    async def execute(self, args: _CalibrateArgs, *, trace_id: str) -> ToolResult:  # noqa: ARG002
        return await asyncio.to_thread(_compute_calibration, args.claim_type, args.window)


def _compute_calibration(claim_type: str, window: int) -> ToolResult:
    try:
        from sovereign_agent.db import open_atoms_db
        import json as _json

        conn = open_atoms_db()
        try:
            cur = conn.execute(
                "SELECT confidence, summary, content_ref FROM atoms "
                "WHERE type='decision' AND superseded_at IS NULL "
                "ORDER BY created_at DESC LIMIT ?",
                (window * 3,),
            )
            rows = cur.fetchall()
        finally:
            conn.close()

        relevant: list[dict] = []
        for confidence, summary, content_ref_json in rows:
            try:
                content = _json.loads(content_ref_json) if content_ref_json else {}
                data = content.get("content", {})
                if isinstance(data, str):
                    data = _json.loads(data)
            except Exception:  # noqa: BLE001
                data = {}

            # Check if claim type matches
            if claim_type.lower() in summary.lower() or claim_type.lower() in str(data).lower():
                outcome = data.get("outcome", "unknown")
                relevant.append({"confidence": confidence, "outcome": outcome, "summary": summary})
                if len(relevant) >= window:
                    break

        if len(relevant) < 2:
            # Insufficient history — return uninformative prior
            return ToolResult(ok=True, output={
                "claim_type": claim_type,
                "prior": 0.7,
                "calibrated": 0.7,
                "sample_size": len(relevant),
                "note": "insufficient history — using uninformative prior 0.7",
                "calibration_data": {},
            })

        # Compute success rate from outcomes
        successes = sum(1 for r in relevant if r["outcome"] in ("success", "confirmed", "correct", "passed"))
        prior = round(successes / len(relevant), 3)
        avg_stated_confidence = round(
            sum(r["confidence"] for r in relevant if r["confidence"] is not None) / len(relevant),
            3,
        )
        calibration_error = round(abs(avg_stated_confidence - prior), 3)

        return ToolResult(ok=True, output={
            "claim_type": claim_type,
            "prior": prior,
            "calibrated": prior,
            "sample_size": len(relevant),
            "avg_stated_confidence": avg_stated_confidence,
            "calibration_error": calibration_error,
            "note": (
                "well-calibrated" if calibration_error < 0.15
                else "overconfident" if avg_stated_confidence > prior
                else "underconfident"
            ),
            "calibration_data": {
                "successes": successes,
                "total": len(relevant),
            },
        })
    except Exception as e:  # noqa: BLE001
        return ToolResult(ok=False, error=f"calibrate_confidence failed: {e}")


__all__ = ["VesselComfortTool", "SelfAssessTool", "CalibrateConfidenceTool"]
