"""tools/calibration_tools.py — Prediction calibration ledger (M79).

Three tools:
  log_prediction     T1 — write a prediction with a confidence score
  resolve_prediction T1 — record the outcome of a prior prediction
  calibration_ledger T0 — read calibration stats grouped by confidence bucket

This is the infrastructure for the mos-intuition-pipeline clause's
"100 calibrated reps with honest feedback" requirement. Calibration is
wisdom infrastructure: it measures not what you know, but how well you
know what you know.

Storage: data_dir/calibration/ledger.ndjson (created on first write)
"""
from __future__ import annotations

import json
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from .base import Tool, ToolResult


def _ledger_path() -> Path:
    from sovereign_agent.config import SETTINGS
    path = SETTINGS.paths.data_dir / "calibration" / "ledger.ndjson"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _read_entries(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    entries = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return entries


def _write_entry(path: Path, entry: dict) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        f.flush()


def _bucket(confidence: float) -> float:
    """Round confidence to nearest 0.1 bucket for calibration grouping."""
    return round(round(confidence * 10) / 10, 1)


# ── LogPredictionTool ─────────────────────────────────────────────────────────


class LogPredictionTool(Tool):
    """Write a prediction with a confidence score to the calibration ledger.

    Each prediction is identified by an entry_id (UUID). After an outcome
    is known, use resolve_prediction(entry_id=..., correct=True/False) to
    close the loop. calibration_ledger() reads the accuracy per confidence
    bucket.

    FAILURE MODES: write_error
    """

    name = "log_prediction"
    tier = 1
    description = (
        "Write a prediction to the calibration ledger. "
        "Args: claim (str), confidence (0.0–1.0), domain (str), "
        "evidence_refs (list[str] optional). "
        "Returns entry_id for later resolution."
    )
    failure_modes = ("write_error",)

    class Args(BaseModel):
        claim: str = Field(description="What you predict will be true.")
        confidence: float = Field(ge=0.0, le=1.0, description="Confidence in the prediction.")
        domain: str = Field(description="Domain or topic (e.g. 'code-review', 'testing').")
        evidence_refs: list[str] = Field(
            default_factory=list,
            description="Optional: evidence that informed the prediction.",
        )

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        entry_id = str(uuid.uuid4())
        entry = {
            "entry_id": entry_id,
            "ts": _iso_now(),
            "claim": args.claim,
            "confidence": args.confidence,
            "domain": args.domain,
            "evidence_refs": list(args.evidence_refs),
            "outcome": None,
            "outcome_ts": None,
            "outcome_correct": None,
        }
        try:
            path = _ledger_path()
            _write_entry(path, entry)
        except Exception as exc:
            return ToolResult(ok=False, error=f"write_error: {exc!r}")

        return ToolResult(
            ok=True,
            output={"entry_id": entry_id, "claim": args.claim, "confidence": args.confidence},
            metadata={"source": "log_prediction", "entry_id": entry_id},
        )


# ── ResolvePredictionTool ─────────────────────────────────────────────────────


class ResolvePredictionTool(Tool):
    """Record the outcome of a prior prediction.

    Reads the calibration ledger, finds the entry by entry_id, and
    rewrites it with outcome_correct set. If already resolved, returns
    an error.

    FAILURE MODES: entry_not_found, already_resolved, write_error
    """

    name = "resolve_prediction"
    tier = 1
    description = (
        "Record the outcome of a prediction logged with log_prediction. "
        "Args: entry_id (str), correct (bool), notes (str optional). "
        "FAILURE MODES: entry_not_found, already_resolved, write_error."
    )
    failure_modes = ("entry_not_found", "already_resolved", "write_error")

    class Args(BaseModel):
        entry_id: str = Field(description="UUID returned by log_prediction.")
        correct: bool = Field(description="Was the prediction correct?")
        notes: str = Field(default="", description="Optional notes on the outcome.")

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        try:
            path = _ledger_path()
            entries = _read_entries(path)
        except Exception as exc:
            return ToolResult(ok=False, error=f"write_error: {exc!r}")

        target = None
        for e in entries:
            if e.get("entry_id") == args.entry_id:
                target = e
                break

        if target is None:
            return ToolResult(ok=False, error=f"entry_not_found: {args.entry_id}")

        if target.get("outcome_correct") is not None:
            return ToolResult(
                ok=False,
                error=f"already_resolved: entry {args.entry_id} already has outcome_correct="
                      f"{target['outcome_correct']}",
            )

        # Rewrite ledger with the resolved entry (append-only: mark old entry
        # superseded by writing a resolution entry).
        resolution = dict(target)
        resolution["outcome_correct"] = args.correct
        resolution["outcome_ts"] = _iso_now()
        resolution["outcome"] = "correct" if args.correct else "incorrect"
        if args.notes:
            resolution["notes"] = args.notes.strip()

        # Strategy: rewrite the whole file with the updated entry.
        updated = []
        for e in entries:
            if e.get("entry_id") == args.entry_id:
                updated.append(resolution)
            else:
                updated.append(e)

        try:
            tmp = path.with_suffix(".ndjson.tmp")
            with tmp.open("w", encoding="utf-8") as f:
                for e in updated:
                    f.write(json.dumps(e, ensure_ascii=False) + "\n")
            import os
            os.replace(tmp, path)
        except Exception as exc:
            return ToolResult(ok=False, error=f"write_error: {exc!r}")

        return ToolResult(
            ok=True,
            output={
                "entry_id": args.entry_id,
                "correct": args.correct,
                "claim": target.get("claim", ""),
                "confidence": target.get("confidence", 0.0),
            },
            metadata={"source": "resolve_prediction"},
        )


# ── CalibrationLedgerTool ─────────────────────────────────────────────────────


class CalibrationLedgerTool(Tool):
    """Read calibration stats grouped by confidence bucket.

    Groups resolved predictions by confidence bucket (0.1 increments)
    and computes accuracy per bucket. Drift = (accuracy - confidence),
    so negative drift means overconfidence.

    Returns calibration_score: weighted accuracy across all resolved entries.
    Empty ledger: ok=True, total_predictions=0.

    FAILURE MODES: read_error
    """

    name = "calibration_ledger"
    tier = 0
    description = (
        "Read calibration stats from the ledger. "
        "Args: domain (str, optional filter), resolved_only (bool), limit (int). "
        "Returns calibration_score, by_bucket stats, recent_predictions."
    )
    failure_modes = ("read_error",)

    class Args(BaseModel):
        domain: Optional[str] = Field(default=None, description="Filter by domain.")
        resolved_only: bool = Field(
            default=False,
            description="Return only predictions that have been resolved.",
        )
        limit: int = Field(default=50, ge=1, le=500)

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        try:
            path = _ledger_path()
            entries = _read_entries(path)
        except Exception as exc:
            return ToolResult(ok=False, error=f"read_error: {exc!r}")

        if args.domain:
            entries = [e for e in entries if e.get("domain") == args.domain]

        if args.resolved_only:
            entries = [e for e in entries if e.get("outcome_correct") is not None]

        total = len(entries)
        resolved = [e for e in entries if e.get("outcome_correct") is not None]

        # Group resolved by confidence bucket
        bucket_data: dict[float, list[bool]] = defaultdict(list)
        for e in resolved:
            b = _bucket(float(e.get("confidence", 0.5)))
            bucket_data[b].append(bool(e["outcome_correct"]))

        by_bucket = []
        for b in sorted(bucket_data.keys()):
            outcomes = bucket_data[b]
            accuracy = sum(outcomes) / len(outcomes) if outcomes else 0.0
            by_bucket.append({
                "confidence_bucket": b,
                "count": len(outcomes),
                "accuracy": round(accuracy, 3),
                "drift": round(accuracy - b, 3),
            })

        # Overall calibration score: weighted accuracy
        if resolved:
            calibration_score = sum(
                1 for e in resolved if e.get("outcome_correct")
            ) / len(resolved)
        else:
            calibration_score = None

        recent = sorted(entries, key=lambda e: e.get("ts", ""), reverse=True)[:args.limit]

        return ToolResult(
            ok=True,
            output={
                "domain": args.domain,
                "total_predictions": total,
                "resolved_predictions": len(resolved),
                "calibration_score": round(calibration_score, 3) if calibration_score is not None else None,
                "by_bucket": by_bucket,
                "recent_predictions": recent,
            },
            metadata={"source": "calibration_ledger"},
        )
