"""tools/hypothesis_close.py — Hypothesis lifecycle closure tools (M58).

  hypothesis_queue()        T0 — open hypotheses with no result atom, oldest first
  hypothesis_synthesis()    T0 — confirm rate + insights from recent results
  hypothesis_archive()      T1 — mark stale open hypotheses as superseded (reversible)
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field

from .base import Tool, ToolResult

try:
    from sovereign_agent.db import open_atoms_db
except ImportError:
    open_atoms_db = None  # type: ignore[assignment]


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_hypotheses(limit: int = 200) -> list[dict]:
    """Load all non-superseded hypothesis atoms, oldest first."""
    if open_atoms_db is None:
        return []
    conn = open_atoms_db()
    try:
        rows = conn.execute(
            "SELECT atom_id, content_ref, created_at FROM atoms "
            "WHERE type='hypothesis' AND superseded_at IS NULL "
            "ORDER BY created_at ASC LIMIT ?",
            (limit,),
        ).fetchall()
        results = []
        for atom_id, content_json, created_at in rows:
            try:
                content = json.loads(content_json) if content_json else {}
                data = content.get("content", {})
                if isinstance(data, str):
                    data = json.loads(data)
            except Exception:  # noqa: BLE001
                data = {}
            results.append({
                "atom_id": atom_id,
                "created_at": created_at,
                "summary": data.get("hypothesis", "?"),
                "value_if_confirmed": data.get("value_if_confirmed", 0.5),
                "estimated_test_cost": data.get("estimated_test_cost", "medium"),
                "status": data.get("status", "pending"),
            })
        return results
    except Exception:  # noqa: BLE001
        return []
    finally:
        conn.close()


def _load_results(days: int = 90) -> list[dict]:
    """Load hypothesis-result atoms from the last N days."""
    if open_atoms_db is None:
        return []
    conn = open_atoms_db()
    try:
        rows = conn.execute(
            "SELECT atom_id, content_ref, created_at FROM atoms "
            "WHERE type='hypothesis-result' AND superseded_at IS NULL "
            "ORDER BY created_at DESC LIMIT 500",
        ).fetchall()
        results = []
        for atom_id, content_json, created_at in rows:
            try:
                content = json.loads(content_json) if content_json else {}
                data = content.get("content", {})
                if isinstance(data, str):
                    data = json.loads(data)
            except Exception:  # noqa: BLE001
                data = {}
            results.append({
                "atom_id": atom_id,
                "hypothesis_id": data.get("hypothesis_id", ""),
                "verdict": data.get("verdict", "?"),
                "lesson": data.get("lesson", ""),
                "new_confidence": data.get("new_confidence", 0.5),
                "created_at": created_at,
            })
        return results
    except Exception:  # noqa: BLE001
        return []
    finally:
        conn.close()


def _evaluated_hypothesis_ids(results: list[dict]) -> set[str]:
    return {r["hypothesis_id"] for r in results if r["hypothesis_id"]}


# ── HypothesisQueueTool ───────────────────────────────────────────────────────

class _QueueArgs(BaseModel):
    limit: int = Field(default=20, ge=1, le=100, description="Max entries to return.")
    show_evaluated: bool = Field(
        default=False,
        description="If True, also return evaluated hypotheses (those with result atoms).",
    )


class HypothesisQueueTool(Tool[_QueueArgs]):
    name = "hypothesis_queue"
    tier = 0
    description = (
        "List open hypotheses (those without a hypothesis-result atom), oldest first. "
        "Use to find which hypotheses still need an experiment and evaluation. "
        "Cross-references hypothesis atoms against hypothesis-result atoms by hypothesis_id. "
        "Call evaluate_result() to close an open hypothesis."
    )
    failure_modes = ("db_unavailable",)
    Args = _QueueArgs

    async def execute(self, args: _QueueArgs, *, trace_id: str) -> ToolResult:
        try:
            hypotheses = await asyncio.to_thread(_load_hypotheses, args.limit * 4)
            results = await asyncio.to_thread(_load_results)
            evaluated_ids = _evaluated_hypothesis_ids(results)

            open_hyps = [h for h in hypotheses if h["atom_id"] not in evaluated_ids]
            evaluated_hyps = [h for h in hypotheses if h["atom_id"] in evaluated_ids]

            output_open = open_hyps[:args.limit]
            output: dict = {
                "open": output_open,
                "open_count": len(open_hyps),
                "evaluated_count": len(evaluated_hyps),
                "total_hypotheses": len(hypotheses),
            }
            if args.show_evaluated:
                output["evaluated"] = evaluated_hyps[:args.limit]

            return ToolResult(ok=True, output=output)
        except Exception as e:  # noqa: BLE001
            return ToolResult(ok=False, error=f"hypothesis_queue failed: {e}")


# ── HypothesisSynthesisTool ───────────────────────────────────────────────────

class _SynthesisArgs(BaseModel):
    days: int = Field(default=30, ge=1, le=365, description="Look back N days for results.")
    domain_filter: Optional[str] = Field(
        default=None,
        description="Filter results whose lesson contains this domain keyword.",
    )


class HypothesisSynthesisTool(Tool[_SynthesisArgs]):
    name = "hypothesis_synthesis"
    tier = 0
    description = (
        "Aggregate hypothesis-result atoms from the last N days into confirmation statistics. "
        "Returns: confirm_rate, total tested, confirmed list (summary + lesson), "
        "refuted list, inconclusive list. No LLM — pure aggregation math."
    )
    failure_modes = ("db_unavailable",)
    Args = _SynthesisArgs

    async def execute(self, args: _SynthesisArgs, *, trace_id: str) -> ToolResult:
        try:
            results = await asyncio.to_thread(_load_results, args.days)

            if args.domain_filter:
                kw = args.domain_filter.lower()
                results = [r for r in results if kw in r.get("lesson", "").lower()]

            confirmed = [r for r in results if r["verdict"] == "confirmed"]
            refuted = [r for r in results if r["verdict"] == "refuted"]
            inconclusive = [r for r in results if r["verdict"] == "inconclusive"]

            total = len(results)
            confirm_rate = round(len(confirmed) / total, 3) if total > 0 else 0.0

            return ToolResult(ok=True, output={
                "period_days": args.days,
                "total_evaluated": total,
                "confirmed_count": len(confirmed),
                "refuted_count": len(refuted),
                "inconclusive_count": len(inconclusive),
                "confirm_rate": confirm_rate,
                "confirmed": [{"hypothesis_id": r["hypothesis_id"], "lesson": r["lesson"][:200]} for r in confirmed],
                "refuted": [{"hypothesis_id": r["hypothesis_id"], "lesson": r["lesson"][:200]} for r in refuted],
                "inconclusive": [{"hypothesis_id": r["hypothesis_id"]} for r in inconclusive],
            })
        except Exception as e:  # noqa: BLE001
            return ToolResult(ok=False, error=f"hypothesis_synthesis failed: {e}")


# ── HypothesisArchiveTool ─────────────────────────────────────────────────────

class _ArchiveArgs(BaseModel):
    hypothesis_id: str = Field(description="The atom_id of the hypothesis to archive.")
    reason: str = Field(
        default="stale",
        description="Why this hypothesis is being archived: 'stale', 'superseded', 'invalid'.",
    )


class HypothesisArchiveTool(Tool[_ArchiveArgs]):
    name = "hypothesis_archive"
    tier = 1
    description = (
        "Mark an open hypothesis as superseded (archived). "
        "The original atom row is preserved — superseded_at + superseded_by are set. "
        "T1 because it modifies atom state. Reversible: original data is intact. "
        "Use for hypotheses that are >60 days old with no result atom, "
        "or ones overtaken by new evidence."
    )
    failure_modes = ("db_unavailable", "hypothesis_not_found")
    Args = _ArchiveArgs

    async def execute(self, args: _ArchiveArgs, *, trace_id: str) -> ToolResult:
        if open_atoms_db is None:
            return ToolResult(ok=False, error="DB unavailable — cannot archive.")

        try:
            result = await asyncio.to_thread(self._do_archive, args.hypothesis_id, args.reason)
            return result
        except Exception as e:  # noqa: BLE001
            return ToolResult(ok=False, error=f"hypothesis_archive failed: {e}")

    @staticmethod
    def _do_archive(hypothesis_id: str, reason: str) -> ToolResult:
        conn = open_atoms_db()
        try:
            cur = conn.execute(
                "SELECT atom_id FROM atoms WHERE atom_id = ? AND type = 'hypothesis' AND superseded_at IS NULL",
                (hypothesis_id,),
            )
            if cur.fetchone() is None:
                return ToolResult(ok=False, error=f"hypothesis not found or already archived: {hypothesis_id}")

            now = _utc_now()
            conn.execute(
                "UPDATE atoms SET superseded_at = ?, superseded_by = ? WHERE atom_id = ?",
                (now, f"archived-{reason}", hypothesis_id),
            )
            conn.commit()
            return ToolResult(ok=True, output={
                "hypothesis_id": hypothesis_id,
                "archived_at": now,
                "reason": reason,
                "note": "Original atom row preserved; superseded_at/superseded_by set. Reversible via SQL UPDATE.",
            })
        finally:
            conn.close()


__all__ = ["HypothesisQueueTool", "HypothesisSynthesisTool", "HypothesisArchiveTool"]
