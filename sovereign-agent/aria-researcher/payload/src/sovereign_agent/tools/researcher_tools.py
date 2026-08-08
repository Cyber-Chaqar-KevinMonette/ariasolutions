"""
tools/researcher_tools.py — Theoretical Researcher + Experimentalist (M39).

All tools are T0, deterministic (no LLM calls), backed by atoms.
Hypothesis lifecycle: form → design → execute (via existing tools) → evaluate → archive.

  form_hypothesis(question, context)   T0 — structured hypothesis with go_nogo signal
  design_experiment(hypothesis_id)     T0 — test plan with success/failure criteria
  evaluate_result(hypothesis_id, obs)  T0 — verdict + confidence update + lesson
  research_queue(min_value, max_cost)  T0 — pending hypotheses sorted by value/cost
"""
from __future__ import annotations

import asyncio
import json
from typing import Optional

from pydantic import BaseModel, Field

from .base import Tool, ToolResult


# ── form_hypothesis ───────────────────────────────────────────────────────────


class _FormArgs(BaseModel):
    question: str = Field(description="The testable question or uncertainty.")
    context: str = Field(description="Relevant context, evidence, or observations prompting this hypothesis.")
    prior_knowledge: Optional[str] = Field(
        default=None,
        description="Existing knowledge relevant to the hypothesis.",
    )
    estimated_value: float = Field(
        default=0.5, ge=0.0, le=1.0,
        description="Estimated value if confirmed (0=low, 1=very high). Be honest.",
    )
    estimated_cost: str = Field(
        default="medium",
        description="Estimated test cost: 'low', 'medium', or 'high'.",
    )


class FormHypothesisTool(Tool[_FormArgs]):
    name = "form_hypothesis"
    tier = 0
    description = (
        "Form a structured, falsifiable hypothesis about an uncertainty. "
        "Returns a hypothesis with null hypothesis, prediction, confidence prior, "
        "and a go_nogo signal (value × P(confirm) > cost). "
        "Only run expensive experiments when go_nogo=True. "
        "Low-value hunches stay as atoms; high-value ones become experiments. "
        "Research is love: invest effort where it actually matters."
    )
    failure_modes = ("atom_write_failed", "invalid_cost_level")
    Args = _FormArgs

    async def execute(self, args: _FormArgs, *, trace_id: str) -> ToolResult:
        valid_costs = {"low", "medium", "high"}
        if args.estimated_cost not in valid_costs:
            return ToolResult(ok=False, error=f"invalid cost level '{args.estimated_cost}'; must be one of {valid_costs}")

        try:
            hyp_id = await asyncio.to_thread(_write_hypothesis_atom, args, trace_id)
            go_nogo = _compute_go_nogo(args.estimated_value, args.estimated_cost)
            confidence_prior = _naive_confidence_prior(args.estimated_value)
            return ToolResult(ok=True, output={
                "id": hyp_id,
                "hypothesis": f"If {args.context}, then {args.question}",
                "null_hypothesis": f"No observable change related to: {args.question}",
                "prediction": f"Confirming this would demonstrate: {args.question}",
                "falsifiable": True,
                "confidence_prior": confidence_prior,
                "value_if_confirmed": args.estimated_value,
                "estimated_test_cost": args.estimated_cost,
                "go_nogo": go_nogo,
                "go_nogo_reason": (
                    "value × P(confirm) > cost estimate — worth testing"
                    if go_nogo
                    else "value × P(confirm) ≤ cost estimate — park as atom, don't test yet"
                ),
            })
        except Exception as e:  # noqa: BLE001
            return ToolResult(ok=False, error=f"form_hypothesis failed: {e}")


def _compute_go_nogo(estimated_value: float, cost: str) -> bool:
    cost_weight = {"low": 0.1, "medium": 0.35, "high": 0.65}
    weight = cost_weight.get(cost, 0.35)
    confidence_prior = _naive_confidence_prior(estimated_value)
    return (estimated_value * confidence_prior) > weight


def _naive_confidence_prior(estimated_value: float) -> float:
    # Prior scales with value: high-value questions tend to have more signal
    return round(0.4 + estimated_value * 0.3, 3)


# ── design_experiment ─────────────────────────────────────────────────────────


class _DesignArgs(BaseModel):
    hypothesis_id: str = Field(description="ID returned by form_hypothesis().")
    available_tools: Optional[list[str]] = Field(
        default=None,
        description="List of tool names available for this experiment. Omit to use defaults.",
    )
    constraints: Optional[str] = Field(
        default=None,
        description="Constraints on the experiment (time limits, resource limits, etc.).",
    )


class DesignExperimentTool(Tool[_DesignArgs]):
    name = "design_experiment"
    tier = 0
    description = (
        "Design a test plan for a hypothesis. Returns structured steps, "
        "success/failure criteria, and a go_nogo gate. Only run if go_nogo=True. "
        "Calls no tools itself — produces a plan to execute with existing tools."
    )
    failure_modes = ("hypothesis_not_found", "atom_db_unavailable")
    Args = _DesignArgs

    async def execute(self, args: _DesignArgs, *, trace_id: str) -> ToolResult:
        try:
            hyp = await asyncio.to_thread(_load_hypothesis, args.hypothesis_id)
            if hyp is None:
                return ToolResult(ok=False, error=f"hypothesis not found: {args.hypothesis_id}")

            value = hyp.get("value_if_confirmed", 0.5)
            cost = hyp.get("estimated_test_cost", "medium")
            go_nogo = _compute_go_nogo(value, cost)

            tools = args.available_tools or ["run_command", "run_tests", "read_file", "search_text"]
            steps = [
                f"1. Establish baseline: read relevant state using {tools[0] if tools else 'read_file'}",
                f"2. Run targeted test: {hyp.get('hypothesis', 'execute test action')}",
                f"3. Observe result against prediction: {hyp.get('prediction', 'compare before/after')}",
                "4. Call evaluate_result(hypothesis_id, observation) with findings",
            ]
            if args.constraints:
                steps.append(f"Constraints: {args.constraints}")

            return ToolResult(ok=True, output={
                "hypothesis_id": args.hypothesis_id,
                "hypothesis_text": hyp.get("hypothesis", ""),
                "steps": steps,
                "success_criteria": f"Observation confirms prediction: {hyp.get('prediction', '?')}",
                "failure_criteria": f"Observation matches null hypothesis: {hyp.get('null_hypothesis', '?')}",
                "expected_observation": hyp.get("prediction", "observable change"),
                "go_nogo": go_nogo,
                "go_nogo_reason": (
                    "value × P(confirm) > cost — proceed"
                    if go_nogo
                    else "cost exceeds expected value — defer or refine hypothesis first"
                ),
            })
        except Exception as e:  # noqa: BLE001
            return ToolResult(ok=False, error=f"design_experiment failed: {e}")


# ── evaluate_result ───────────────────────────────────────────────────────────


class _EvalArgs(BaseModel):
    hypothesis_id: str = Field(description="ID of the hypothesis being evaluated.")
    observation: str = Field(description="What was actually observed during the experiment.")
    verdict: str = Field(
        description="Your verdict: 'confirmed', 'refuted', or 'inconclusive'.",
    )


class EvaluateResultTool(Tool[_EvalArgs]):
    name = "evaluate_result"
    tier = 0
    description = (
        "Record the result of a hypothesis test. Updates the hypothesis atom status, "
        "computes a confidence delta, and generates lesson material. "
        "Always call this after running an experiment — close the loop."
    )
    failure_modes = ("hypothesis_not_found", "invalid_verdict", "atom_write_failed")
    Args = _EvalArgs

    async def execute(self, args: _EvalArgs, *, trace_id: str) -> ToolResult:
        valid_verdicts = {"confirmed", "refuted", "inconclusive"}
        if args.verdict not in valid_verdicts:
            return ToolResult(ok=False, error=f"invalid verdict '{args.verdict}'; must be one of {valid_verdicts}")

        try:
            hyp = await asyncio.to_thread(_load_hypothesis, args.hypothesis_id)
            if hyp is None:
                return ToolResult(ok=False, error=f"hypothesis not found: {args.hypothesis_id}")

            confidence_delta = {"confirmed": 0.3, "refuted": -0.3, "inconclusive": 0.0}[args.verdict]
            new_confidence = max(0.0, min(1.0, hyp.get("confidence_prior", 0.5) + confidence_delta))

            next_actions: list[str] = []
            if args.verdict == "confirmed":
                next_actions.append("Write a lesson: what does this confirmation teach us?")
                next_actions.append("Update related atoms with new evidence.")
            elif args.verdict == "refuted":
                next_actions.append("form_hypothesis — refine with this new negative evidence.")
                next_actions.append("Check if null hypothesis reveals a deeper truth.")
            else:
                next_actions.append("Collect more data before re-evaluating.")

            lesson_material = (
                f"Hypothesis '{hyp.get('hypothesis', '?')}' was {args.verdict}. "
                f"Observation: {args.observation}. "
                f"Confidence updated from {hyp.get('confidence_prior', 0.5):.2f} → {new_confidence:.2f}."
            )

            # Write evaluation atom
            await asyncio.to_thread(
                _write_evaluation_atom, args.hypothesis_id, args.verdict, lesson_material, new_confidence, trace_id
            )

            return ToolResult(ok=True, output={
                "hypothesis_id": args.hypothesis_id,
                "verdict": args.verdict,
                "observation": args.observation,
                "confidence_delta": confidence_delta,
                "new_confidence": new_confidence,
                "next_actions": next_actions,
                "lesson_material": lesson_material,
            })
        except Exception as e:  # noqa: BLE001
            return ToolResult(ok=False, error=f"evaluate_result failed: {e}")


# ── research_queue ────────────────────────────────────────────────────────────


class _QueueArgs(BaseModel):
    min_value: float = Field(default=0.5, ge=0.0, le=1.0, description="Minimum value_if_confirmed filter.")
    max_cost: str = Field(default="medium", description="Maximum cost level: 'low' or 'medium'.")
    limit: int = Field(default=10, ge=1, le=50)


class ResearchQueueTool(Tool[_QueueArgs]):
    name = "research_queue"
    tier = 0
    description = (
        "Return pending hypothesis atoms sorted by value/cost ratio. "
        "High-value, low-cost hypotheses surface first. "
        "Use to prioritize which experiments are worth running next."
    )
    failure_modes = ("atom_db_unavailable",)
    Args = _QueueArgs

    async def execute(self, args: _QueueArgs, *, trace_id: str) -> ToolResult:  # noqa: ARG002
        try:
            hypotheses = await asyncio.to_thread(_load_pending_hypotheses, args.limit * 3)
            cost_order = {"low": 0, "medium": 1, "high": 2}
            max_cost_idx = cost_order.get(args.max_cost, 1)

            filtered = [
                h for h in hypotheses
                if h.get("value_if_confirmed", 0.0) >= args.min_value
                and cost_order.get(h.get("estimated_test_cost", "medium"), 1) <= max_cost_idx
            ]

            # Sort by value/cost score descending
            def _score(h: dict) -> float:
                val = h.get("value_if_confirmed", 0.5)
                cost_idx = cost_order.get(h.get("estimated_test_cost", "medium"), 1) + 1
                return val / cost_idx

            filtered.sort(key=_score, reverse=True)
            filtered = filtered[:args.limit]

            return ToolResult(ok=True, output={
                "queue": filtered,
                "count": len(filtered),
                "note": (
                    "Run design_experiment() on the top entry when go_nogo=True."
                    if filtered else "No qualifying hypotheses. Form new ones with form_hypothesis()."
                ),
            })
        except Exception as e:  # noqa: BLE001
            return ToolResult(ok=False, error=f"research_queue failed: {e}")


# ── Internal helpers ──────────────────────────────────────────────────────────


def _write_hypothesis_atom(args: _FormArgs, trace_id: str) -> str:
    from sovereign_agent.db import open_atoms_db
    from sovereign_agent.memory import Atom, write_atom

    hyp_data = {
        "hypothesis": f"If {args.context}, then {args.question}",
        "null_hypothesis": f"No observable change related to: {args.question}",
        "prediction": f"Confirming this would demonstrate: {args.question}",
        "falsifiable": True,
        "confidence_prior": _naive_confidence_prior(args.estimated_value),
        "value_if_confirmed": args.estimated_value,
        "estimated_test_cost": args.estimated_cost,
        "status": "pending",
        "prior_knowledge": args.prior_knowledge,
    }

    atom = Atom(
        type="hypothesis",
        summary=f"[{args.estimated_cost}/{args.estimated_value:.1f}] {args.question[:180]}",
        content_ref={"kind": "inline", "content": json.dumps(hyp_data)},
        claims=[],
        parents=[trace_id],
        confidence=_naive_confidence_prior(args.estimated_value),
        created_by={"actor": "researcher", "version": "M39"},
        scope_tags=["hypothesis", "research"],
    )
    conn = open_atoms_db()
    try:
        aid = write_atom(conn, atom)
        conn.commit()
        return aid
    finally:
        conn.close()


def _load_hypothesis(hypothesis_id: str) -> dict | None:
    from sovereign_agent.db import open_atoms_db
    conn = open_atoms_db()
    try:
        cur = conn.execute(
            "SELECT content_ref, confidence FROM atoms WHERE atom_id = ? AND type = 'hypothesis'",
            (hypothesis_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        content = json.loads(row[0]) if row[0] else {}
        data = content.get("content", {})
        if isinstance(data, str):
            data = json.loads(data)
        data["confidence_prior"] = row[1]
        return data
    finally:
        conn.close()


def _write_evaluation_atom(
    hypothesis_id: str,
    verdict: str,
    lesson: str,
    new_confidence: float,
    trace_id: str,
) -> str:
    from sovereign_agent.db import open_atoms_db
    from sovereign_agent.memory import Atom, write_atom

    atom = Atom(
        type="hypothesis-result",
        summary=f"[{verdict}] {lesson[:200]}",
        content_ref={"kind": "inline", "content": json.dumps({
            "hypothesis_id": hypothesis_id,
            "verdict": verdict,
            "lesson": lesson,
            "new_confidence": new_confidence,
        })},
        claims=[{"text": lesson, "evidence_ref": hypothesis_id}],
        parents=[trace_id],
        confidence=new_confidence,
        created_by={"actor": "researcher", "version": "M39"},
        scope_tags=["hypothesis", "research", "result"],
    )
    conn = open_atoms_db()
    try:
        aid = write_atom(conn, atom)
        conn.commit()
        return aid
    finally:
        conn.close()


def _load_pending_hypotheses(limit: int) -> list[dict]:
    from sovereign_agent.db import open_atoms_db
    conn = open_atoms_db()
    try:
        cur = conn.execute(
            "SELECT atom_id, content_ref, confidence FROM atoms "
            "WHERE type='hypothesis' AND superseded_at IS NULL "
            "ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        rows = cur.fetchall()
        result = []
        for atom_id, content_ref_json, confidence in rows:
            try:
                content = json.loads(content_ref_json) if content_ref_json else {}
                data = content.get("content", {})
                if isinstance(data, str):
                    data = json.loads(data)
                # Skip already-evaluated ones
                if data.get("status") in ("confirmed", "refuted"):
                    continue
                data["id"] = atom_id
                data["confidence_prior"] = confidence
                result.append(data)
            except Exception:  # noqa: BLE001
                continue
        return result
    finally:
        conn.close()


__all__ = [
    "FormHypothesisTool",
    "DesignExperimentTool",
    "EvaluateResultTool",
    "ResearchQueueTool",
]
