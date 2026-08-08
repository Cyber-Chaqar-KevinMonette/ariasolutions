"""
tools/leverage_tools.py — God Tier Leverage Oracle (M41).

All tools are T0, deterministic (no LLM calls). Every action in Aria
should be justifiable as high leverage. These tools make leverage explicit.

  score_leverage(action, context, alternatives)  T0 — 0-1 leverage score + rec
  leverage_audit(limit)                          T0 — retrospective session audit
  prioritize_objectives(scope)                   T0 — ObjectiveMap sorted by leverage
"""
from __future__ import annotations

import asyncio
from typing import Optional

from pydantic import BaseModel, Field

from .base import Tool, ToolResult


# ── Leverage scoring heuristic ─────────────────────────────────────────────────
# Factors (all 0.0–1.0):
#   blocker_score    — does this unblock other work?
#   downstream_score — how many tasks does this enable?
#   uniqueness_score — can only Aria do this (vs Kevin doing it manually)?
#   reversibility    — how reversible is this action?
#   time_sensitivity — does this decay if delayed?
#
# Final: weighted average; recommendation cutoffs:
#   >= 0.75 → do_first
#   >= 0.50 → do_normal
#   >= 0.30 → defer
#   < 0.30  → skip

_BLOCKER_KEYWORDS = {"block", "stuck", "waiting", "depends", "gat", "prerequisit"}
_DOWNSTREAM_KEYWORDS = {"enable", "unlock", "downstream", "chain", "cascade", "unblock"}
_UNIQUE_KEYWORDS = {"only aria", "automated", "ai", "analysis", "search", "synthesiz", "generate"}
_IRREVERSIBLE_KEYWORDS = {"delete", "drop", "destroy", "rm ", "remove", "force", "push --force", "truncate"}
_TIME_KEYWORDS = {"urgent", "deadline", "today", "asap", "expir", "release", "ship"}


def _score_text(text: str, keywords: set[str]) -> float:
    lower = text.lower()
    hits = sum(1 for kw in keywords if kw in lower)
    return min(1.0, hits * 0.4)


def _compute_leverage_score(action: str, context: str | None, alternatives: list[str] | None) -> dict:
    full_text = f"{action} {context or ''} {' '.join(alternatives or [])}"

    blocker_score = _score_text(full_text, _BLOCKER_KEYWORDS)
    downstream_score = _score_text(full_text, _DOWNSTREAM_KEYWORDS)
    uniqueness_score = _score_text(full_text, _UNIQUE_KEYWORDS)
    reversibility = 1.0 - _score_text(full_text, _IRREVERSIBLE_KEYWORDS)
    time_score = _score_text(full_text, _TIME_KEYWORDS)

    # Weighted sum
    raw = (
        blocker_score * 0.30
        + downstream_score * 0.25
        + uniqueness_score * 0.20
        + reversibility * 0.15
        + time_score * 0.10
    )
    leverage_score = round(min(1.0, max(0.0, raw)), 3)

    if leverage_score >= 0.75:
        recommendation = "do_first"
        reasoning = "High-leverage: unblocks work or has strong downstream impact."
    elif leverage_score >= 0.50:
        recommendation = "do_normal"
        reasoning = "Moderate leverage: worth doing in normal priority order."
    elif leverage_score >= 0.30:
        recommendation = "defer"
        reasoning = "Low-moderate leverage: defer until higher-leverage work is done."
    else:
        recommendation = "skip"
        reasoning = "Low leverage: consider skipping or parking as a background objective."

    # Opportunity cost
    if alternatives and len(alternatives) > 0:
        opportunity_cost = "medium" if len(alternatives) >= 2 else "low"
    else:
        opportunity_cost = "low"

    return {
        "leverage_score": leverage_score,
        "value_confidence": round(min(1.0, leverage_score + 0.1), 3),
        "reasoning": reasoning,
        "opportunity_cost": opportunity_cost,
        "recommendation": recommendation,
        "factors": {
            "blocker_score": blocker_score,
            "downstream_score": downstream_score,
            "uniqueness_score": uniqueness_score,
            "reversibility": reversibility,
            "time_sensitivity": time_score,
        },
    }


# ── score_leverage ────────────────────────────────────────────────────────────


class _ScoreArgs(BaseModel):
    action_description: str = Field(
        description="Describe the action you're considering taking.",
    )
    context: Optional[str] = Field(
        default=None,
        description="Additional context: what depends on this, what it enables, constraints.",
    )
    alternatives: Optional[list[str]] = Field(
        default=None,
        description="Alternative actions you could take instead. Helps compute opportunity cost.",
    )


class ScoreLeverageTool(Tool[_ScoreArgs]):
    name = "score_leverage"
    tier = 0
    description = (
        "Score a proposed action's leverage (0.0–1.0) using a deterministic heuristic: "
        "how many blockers it resolves, downstream impact, whether only Aria can do it, "
        "reversibility, and time-sensitivity. Returns recommendation: "
        "do_first | do_normal | defer | skip. "
        "High-leverage first: blockers, uniquely-yours tasks, downstream multipliers."
    )
    failure_modes = ("description_empty",)
    Args = _ScoreArgs

    async def execute(self, args: _ScoreArgs, *, trace_id: str) -> ToolResult:  # noqa: ARG002
        if not args.action_description.strip():
            return ToolResult(ok=False, error="action_description is empty")
        result = _compute_leverage_score(args.action_description, args.context, args.alternatives)
        return ToolResult(ok=True, output=result)


# ── leverage_audit ────────────────────────────────────────────────────────────


class _AuditArgs(BaseModel):
    limit: int = Field(default=20, ge=1, le=100, description="Number of recent events to audit.")


class LeverageAuditTool(Tool[_AuditArgs]):
    name = "leverage_audit"
    tier = 0
    description = (
        "Retrospective leverage audit of recent session actions. "
        "Reads event history, scores each action, and groups into high/low leverage. "
        "Returns pattern insights to learn from. Call at session end."
    )
    failure_modes = ("event_db_unavailable",)
    Args = _AuditArgs

    async def execute(self, args: _AuditArgs, *, trace_id: str) -> ToolResult:  # noqa: ARG002
        try:
            events = await asyncio.to_thread(_load_action_events, args.limit)
            high: list[dict] = []
            low: list[dict] = []
            skipped: list[dict] = []

            for event in events:
                flag = event.get("flag", "")
                payload = event.get("payload", {})
                action_text = f"{flag} {str(payload)[:200]}"
                scored = _compute_leverage_score(action_text, None, None)
                entry = {
                    "flag": flag,
                    "score": scored["leverage_score"],
                    "recommendation": scored["recommendation"],
                }
                if scored["leverage_score"] >= 0.5:
                    high.append(entry)
                elif scored["leverage_score"] < 0.2:
                    skipped.append(entry)
                else:
                    low.append(entry)

            # Pattern insights
            insights: list[str] = []
            if len(skipped) > 3:
                insights.append(f"{len(skipped)} low-leverage actions detected — consider deferring more aggressively.")
            if len(high) > len(low) + len(skipped):
                insights.append("Good leverage ratio this session — high-leverage work dominated.")
            if not high:
                insights.append("No high-leverage actions detected — focus on blockers and downstream enablers.")

            return ToolResult(ok=True, output={
                "high": high[:10],
                "low": low[:10],
                "skipped": skipped[:5],
                "pattern_insights": insights,
                "stats": {
                    "total_audited": len(events),
                    "high_count": len(high),
                    "low_count": len(low),
                    "skip_count": len(skipped),
                    "leverage_ratio": round(len(high) / max(1, len(events)), 3),
                },
            })
        except Exception as e:  # noqa: BLE001
            return ToolResult(ok=False, error=f"leverage_audit failed: {e}")


# ── prioritize_objectives ─────────────────────────────────────────────────────


class _PrioritizeArgs(BaseModel):
    scope: Optional[str] = Field(
        default=None,
        description="Filter by scope ('this_session', 'persistent', 'this_workflow'). Omit for all.",
    )


class PrioritizeObjectivesTool(Tool[_PrioritizeArgs]):
    name = "prioritize_objectives"
    tier = 0
    description = (
        "Score each active objective in the ObjectiveMap by leverage and return "
        "a sorted list (highest leverage first). "
        "Call before starting a task queue to work in leverage order. "
        "Combines priority tier and leverage score for final ranking."
    )
    failure_modes = ("objective_map_unavailable",)
    Args = _PrioritizeArgs

    async def execute(self, args: _PrioritizeArgs, *, trace_id: str) -> ToolResult:  # noqa: ARG002
        try:
            from sovereign_agent.objective_map import get_objective_map
            obj_map = get_objective_map()
            objectives = obj_map.by_priority()

            if args.scope:
                objectives = [o for o in objectives if o.scope == args.scope]

            priority_weight = {"primary": 0.4, "secondary": 0.1, "background": 0.0}

            scored: list[dict] = []
            for obj in objectives:
                leverage = _compute_leverage_score(obj.text, None, None)
                pweight = priority_weight.get(obj.priority, 0.0)
                final_score = round(min(1.0, leverage["leverage_score"] + pweight), 3)
                scored.append({
                    **obj.as_dict(),
                    "leverage_score": leverage["leverage_score"],
                    "final_score": final_score,
                    "recommendation": leverage["recommendation"],
                })

            scored.sort(key=lambda x: x["final_score"], reverse=True)

            return ToolResult(ok=True, output={
                "objectives": scored,
                "count": len(scored),
                "note": (
                    f"Work in this order. Top: {scored[0]['text'][:80]}"
                    if scored
                    else "No active objectives. Add some with add_objective()."
                ),
            })
        except Exception as e:  # noqa: BLE001
            return ToolResult(ok=False, error=f"prioritize_objectives failed: {e}")


# ── Internal helpers ──────────────────────────────────────────────────────────


def _load_action_events(limit: int) -> list[dict]:
    try:
        from sovereign_agent.config import SETTINGS
        import json as _json
        events: list[dict] = []
        events_dir = getattr(SETTINGS.paths, "events_dir", None)
        if events_dir is None:
            events_dir = SETTINGS.paths.data_dir / "events"
        if not events_dir.exists():
            return events
        for f in sorted(events_dir.glob("*.ndjson"))[-2:]:
            try:
                for line in f.read_text().splitlines():
                    if line.strip():
                        events.append(_json.loads(line))
            except Exception:  # noqa: BLE001
                pass
        # Focus on action events (tool starts, commits, etc.)
        action_flags = {"tool-start-d", "commit-d", "workflow-step-d", "run-command-d", "shell-d"}
        action_events = [e for e in events if e.get("flag", "") in action_flags]
        return action_events[-limit:]
    except Exception:  # noqa: BLE001
        return []


__all__ = ["ScoreLeverageTool", "LeverageAuditTool", "PrioritizeObjectivesTool"]
