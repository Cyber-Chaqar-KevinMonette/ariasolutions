"""Reflector tests — threading bug regression + lesson schema invariants.

The original v0.2 code opened atoms.db in one thread (via asyncio.to_thread)
and used it from another (the calling coroutine). SQLite's default
same-thread guard raised ProgrammingError. This test ensures the fix
holds: reflect() must own its own connection lifecycle inside a single
worker thread.
"""
from __future__ import annotations

import asyncio
import json
import sqlite3
from unittest.mock import AsyncMock, patch

import pytest

from sovereign_agent.config import SETTINGS
from sovereign_agent.db import open_atoms_db
from sovereign_agent.reflector import reflect


pytestmark = pytest.mark.asyncio


def _fake_chat_response(json_payload: dict) -> dict:
    """Mock Ollama response shape."""
    return {
        "message": {
            "content": json.dumps(json_payload),
        }
    }


def _valid_lesson() -> dict:
    return {
        "trigger": "completed_first_task",
        "context": "agent read /etc/hostname and returned its contents",
        "failure_mode": "",
        "correction": "search memory before reading files for cached results",
        "rule": "memory_search before file reads when result may be cached",
        "confidence": 0.7,
    }


async def test_reflect_writes_lesson_without_threading_error():
    """Regression test for the v0.2 SQLite-cross-thread bug."""
    # Make sure the lessons table exists (init via open_atoms_db side effect)
    conn = open_atoms_db()
    conn.close()

    fake_response = _fake_chat_response(_valid_lesson())

    with patch(
        "sovereign_agent.reflector.OllamaClient.chat",
        new=AsyncMock(return_value=fake_response),
    ):
        lesson_id = await reflect(
            trace_id="test-trace",
            outcome="settle",
            goal="read /etc/hostname",
            final_message="pop-os",
            recent_events=[
                {"event_id": "ev1", "flag": "ingest-d", "payload": {}},
                {"event_id": "ev2", "flag": "settle-d", "payload": {}},
            ],
        )

    assert lesson_id is not None
    assert len(lesson_id) >= 26  # ULID

    # Verify the lesson actually landed
    conn = open_atoms_db()
    try:
        row = conn.execute(
            "SELECT trigger, rule, confidence FROM lessons WHERE lesson_id = ?",
            (lesson_id,),
        ).fetchone()
    finally:
        conn.close()

    assert row is not None
    assert "settle-d" in row[0]
    assert row[1] == _valid_lesson()["rule"]
    assert row[2] == _valid_lesson()["confidence"]


async def test_reflect_handles_malformed_json():
    """Reflector should silently skip when model returns garbage, never crash."""
    conn = open_atoms_db()
    conn.close()

    bad_response = {"message": {"content": "this is not JSON {[}"}}

    with patch(
        "sovereign_agent.reflector.OllamaClient.chat",
        new=AsyncMock(return_value=bad_response),
    ):
        lesson_id = await reflect(
            trace_id="test-trace",
            outcome="settle",
            goal="x",
            final_message=None,
            recent_events=[],
        )

    assert lesson_id is None


async def test_reflect_handles_schema_violation():
    """Reflector skips when model returns JSON without required keys."""
    conn = open_atoms_db()
    conn.close()

    incomplete = {"message": {"content": json.dumps({"trigger": "x"})}}  # missing keys

    with patch(
        "sovereign_agent.reflector.OllamaClient.chat",
        new=AsyncMock(return_value=incomplete),
    ):
        lesson_id = await reflect(
            trace_id="test-trace",
            outcome="settle",
            goal="x",
            final_message=None,
            recent_events=[],
        )

    assert lesson_id is None


async def test_reflect_clamps_confidence_to_unit_interval():
    """Confidence outside [0,1] gets clamped, not rejected."""
    conn = open_atoms_db()
    conn.close()

    out_of_range = _valid_lesson()
    out_of_range["confidence"] = 5.0   # nonsense

    fake_response = _fake_chat_response(out_of_range)

    with patch(
        "sovereign_agent.reflector.OllamaClient.chat",
        new=AsyncMock(return_value=fake_response),
    ):
        lesson_id = await reflect(
            trace_id="test-trace",
            outcome="settle",
            goal="x",
            final_message=None,
            recent_events=[],
        )

    assert lesson_id is not None
    conn = open_atoms_db()
    try:
        row = conn.execute(
            "SELECT confidence FROM lessons WHERE lesson_id = ?", (lesson_id,)
        ).fetchone()
    finally:
        conn.close()
    assert 0.0 <= row[0] <= 1.0


async def test_reflect_strips_code_fences():
    """Models often wrap JSON in ```json ... ``` despite instructions."""
    conn = open_atoms_db()
    conn.close()

    fenced = {
        "message": {
            "content": "```json\n" + json.dumps(_valid_lesson()) + "\n```",
        }
    }

    with patch(
        "sovereign_agent.reflector.OllamaClient.chat",
        new=AsyncMock(return_value=fenced),
    ):
        lesson_id = await reflect(
            trace_id="test-trace",
            outcome="settle",
            goal="x",
            final_message=None,
            recent_events=[],
        )
    assert lesson_id is not None


# reflect-gate-wire-tests-d
async def test_reflect_gates_high_confidence_lesson():
    """confidence > 0.8 must route through gate_ring2_improvement."""
    conn = open_atoms_db()
    conn.close()

    high_conf = _valid_lesson()
    high_conf["confidence"] = 0.9
    fake_response = _fake_chat_response(high_conf)

    with patch(
        "sovereign_agent.reflector.OllamaClient.chat",
        new=AsyncMock(return_value=fake_response),
    ), patch(
        "sovereign_agent.reflector.gate_ring2_improvement",
        return_value={"tribunal_verdict": "proceed", "gate_decision": "promoted"},
    ) as mock_gate:
        lesson_id = await reflect(
            trace_id="test-trace-gate",
            outcome="settle",
            goal="x",
            final_message=None,
            recent_events=[],
        )

    assert lesson_id is not None
    mock_gate.assert_called_once()
    args, kwargs = mock_gate.call_args
    proposal = args[0] if args else kwargs["proposal"]
    assert proposal["change"] == high_conf["rule"]
    assert proposal["ring"] == "ring-2"
    assert proposal["reversible"] is True


async def test_reflect_does_not_gate_low_confidence_lesson():
    """confidence <= 0.8 must NOT trigger the tribunal gate."""
    conn = open_atoms_db()
    conn.close()

    low_conf = _valid_lesson()
    low_conf["confidence"] = 0.7
    fake_response = _fake_chat_response(low_conf)

    with patch(
        "sovereign_agent.reflector.OllamaClient.chat",
        new=AsyncMock(return_value=fake_response),
    ), patch(
        "sovereign_agent.reflector.gate_ring2_improvement",
    ) as mock_gate:
        lesson_id = await reflect(
            trace_id="test-trace-nogate",
            outcome="settle",
            goal="x",
            final_message=None,
            recent_events=[],
        )

    assert lesson_id is not None
    mock_gate.assert_not_called()


async def test_reflect_gate_failure_does_not_fail_lesson():
    """A gate error must never turn a successful lesson capture into a failure."""
    conn = open_atoms_db()
    conn.close()

    high_conf = _valid_lesson()
    high_conf["confidence"] = 0.95
    fake_response = _fake_chat_response(high_conf)

    with patch(
        "sovereign_agent.reflector.OllamaClient.chat",
        new=AsyncMock(return_value=fake_response),
    ), patch(
        "sovereign_agent.reflector.gate_ring2_improvement",
        side_effect=RuntimeError("boom"),
    ):
        lesson_id = await reflect(
            trace_id="test-trace-gate-fail",
            outcome="settle",
            goal="x",
            final_message=None,
            recent_events=[],
        )

    assert lesson_id is not None
