"""Reflector — post-task lesson capture. Architecture §6 invariant 5 + MOS §28.

Fires on every ``settle-d`` (success) and ``poison-d`` (consecutive failures
beyond limit) event. Calls the orchestrator with a small instruction to
distill the trace into a Lesson — a durable, queryable rule for future runs.

Lessons live in atoms.db ``lessons`` table, separate from atoms because
they have a distinct schema (trigger, failure_mode, correction, rule).

The reflector has its own token budget (``reflector_max_tokens_per_task``,
default 5000) carved out of the overall task budget so reflection cannot
itself starve the loop.
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from ulid import ULID

from .config import SETTINGS
from .events import emit_event
from .ollama_client import CallKind, OllamaClient
from .tribunal import gate_ring2_improvement  # reflect-gate-wire-import-d


REFLECTOR_PROMPT = """\
You are the Reflector for a sovereign local agent. A task just ended.
Your job: distill ONE durable lesson the agent should remember next time.

Format your response as STRICT JSON with exactly these keys:
{
  "trigger":      "<what state/action triggered this lesson; <=120 chars>",
  "context":      "<what the agent was trying to do; <=300 chars>",
  "failure_mode": "<the failure pattern, or empty if successful run>",
  "correction":   "<what to do differently; <=300 chars>",
  "rule":         "<a one-line, generalizable rule; <=200 chars>",
  "confidence":   <float 0..1>
}

Rules for good lessons:
  - Generalizable: not "don't write to /tmp/foo123" but "write under sandbox dir"
  - Actionable: the rule must be checkable next time
  - Honest about confidence: 1.0 only if you saw it more than once

Output ONLY the JSON. No prose, no fences."""


@dataclass(frozen=True)
class Lesson:
    """A distilled rule. Schema mirrors the lessons table."""

    trigger: str
    context: str
    correction: str
    rule: str
    confidence: float
    failure_mode: str | None
    evidence_event_ids: list[str]


async def _gate_high_confidence_lesson(*, trace_id: str, lesson_id: str, lesson: "Lesson") -> None:  # reflect-gate-wire-fn-d
    """Route a high-confidence lesson through the tribunal + EXPAI evidence gate.

    Propose-only: gate_ring2_improvement never mutates code or values -- it appends a
    promote/dismiss decision to improvement_ledger.ndjson for human review. Best-effort:
    a gate failure must never affect reflect()'s already-successful lesson capture.
    """
    proposal = {
        "change": lesson.rule,
        "ring": "ring-2",
        "reversible": True,  # a lesson is a lessons-table row; deleting/superseding it has zero blast radius
        "evidence": (
            f"reflector lesson_id={lesson_id} confidence={lesson.confidence:.2f} "
            f"trigger={lesson.trigger} evidence_events={lesson.evidence_event_ids}"
        ),
        "changelog": f"Reflector captured high-confidence lesson: {lesson.rule}",
    }
    try:
        result = await asyncio.to_thread(gate_ring2_improvement, proposal, SETTINGS.paths.data_dir)
    except Exception as exc:  # noqa: BLE001 -- gate is best-effort, never blocks lesson capture
        emit_event(
            "reflect-gate-x",
            plane="control",
            trace_id=trace_id,
            payload={"lesson_id": lesson_id, "error": str(exc)[:500]},
        )
        return
    emit_event(
        "reflect-gate-d",
        plane="control",
        trace_id=trace_id,
        payload={
            "lesson_id": lesson_id,
            "tribunal_verdict": result.get("tribunal_verdict"),
            "gate_decision": result.get("gate_decision"),
        },
    )


async def reflect(
    *,
    trace_id: str,
    outcome: str,                  # "settle" | "poison"
    goal: str,
    final_message: str | None,
    recent_events: list[dict[str, Any]],
    client: OllamaClient | None = None,
) -> str | None:
    """Run the Reflector. Returns the lesson_id if one was written, else None.

    Opens its own atoms.db connection inside a worker thread for the write.
    SQLite forbids cross-thread connection use; keeping open+write+close in
    one thread keeps us correct without needing check_same_thread=False.

    Skips silently if the model returns malformed JSON — better to lose a
    lesson than corrupt the lessons table.
    """
    client = client or OllamaClient()

    # Build a compact transcript for the model — last 30 events trimmed
    transcript = json.dumps(recent_events[-30:], default=str)
    user_payload = (
        f"OUTCOME: {outcome}\n"
        f"GOAL: {goal[:500]}\n"
        f"FINAL: {(final_message or '')[:500]}\n"
        f"RECENT_EVENTS:\n{transcript[:4000]}"
    )

    try:
        response = await client.chat(
            model=SETTINGS.reflector_model,
            messages=[
                {"role": "system", "content": REFLECTOR_PROMPT},
                {"role": "user", "content": user_payload},
            ],
            call_kind=CallKind.REFLECT,
            temperature=0.2,
        )
    except Exception as exc:  # noqa: BLE001 — never let reflector crash caller
        emit_event(
            "reflect-x",
            plane="control",
            trace_id=trace_id,
            payload={"error": str(exc)[:500]},
        )
        return None

    msg = response.get("message", {}).get("content", "")
    msg = msg.strip()
    if msg.startswith("```"):
        # Strip code fences if the model added them despite instructions
        msg = msg.strip("`")
        msg = msg.split("\n", 1)[-1] if "\n" in msg else msg

    try:
        parsed = json.loads(msg)
    except json.JSONDecodeError:
        emit_event(
            "reflect-x",
            plane="control",
            trace_id=trace_id,
            payload={"error": "malformed_json", "raw": msg[:500]},
        )
        return None

    try:
        lesson = Lesson(
            trigger=str(parsed["trigger"])[:120],
            context=str(parsed["context"])[:300],
            failure_mode=parsed.get("failure_mode") or None,
            correction=str(parsed["correction"])[:300],
            rule=str(parsed["rule"])[:200],
            confidence=max(0.0, min(1.0, float(parsed.get("confidence", 0.5)))),
            evidence_event_ids=[e.get("event_id", "") for e in recent_events[-10:]],
        )
    except (KeyError, ValueError, TypeError) as exc:
        emit_event(
            "reflect-x",
            plane="control",
            trace_id=trace_id,
            payload={"error": f"schema_violation: {exc}"},
        )
        return None

    lesson_id = str(ULID())
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    # Off-thread DB write — open + write + close in same thread to avoid
    # SQLite's same-thread guard.
    def _write_lesson() -> None:
        from .db import open_atoms_db

        conn = open_atoms_db()
        try:
            conn.execute(
                "INSERT INTO lessons "
                "(lesson_id, ts, trigger, context, failure_mode, correction, rule, "
                "evidence_refs, confidence) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    lesson_id,
                    now,
                    f"{outcome}-d:{lesson.trigger}",
                    lesson.context,
                    lesson.failure_mode,
                    lesson.correction,
                    lesson.rule,
                    json.dumps(lesson.evidence_event_ids, sort_keys=True),
                    lesson.confidence,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    try:
        await asyncio.to_thread(_write_lesson)
    except Exception as exc:  # noqa: BLE001
        emit_event(
            "reflect-x",
            plane="control",
            trace_id=trace_id,
            payload={"error": f"db_write_failed: {exc}"},
        )
        return None

    emit_event(
        "reflect-d",
        plane="control",
        trace_id=trace_id,
        payload={
            "lesson_id": lesson_id,
            "rule": lesson.rule,
            "confidence": lesson.confidence,
        },
    )
    if lesson.confidence > 0.8:  # reflect-gate-wire-call-d
        await _gate_high_confidence_lesson(trace_id=trace_id, lesson_id=lesson_id, lesson=lesson)

    return lesson_id
