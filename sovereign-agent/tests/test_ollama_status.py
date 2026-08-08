"""Sync invariants for OllamaStatus.reason_phrase().

Kept in their own file to avoid pytest-asyncio's auto-mode tagging
them as coroutine tests (which would emit warnings).
"""
from __future__ import annotations

from sovereign_agent.ollama_client import OllamaStatus


def test_reason_phrase_when_unreachable():
    s = OllamaStatus(
        host="http://localhost:11434",
        daemon_reachable=False,
        error="ConnectionError: refused",
    )
    p = s.reason_phrase()
    assert "Ollama unreachable" in p
    assert "http://localhost:11434" in p


def test_reason_phrase_when_model_missing_includes_pull_command():
    s = OllamaStatus(
        host="http://localhost:11434",
        daemon_reachable=True,
        model="phi-4-mini:3.8b",
        model_present=False,
        available_models=("aria-garden:latest",),
    )
    assert "ollama pull phi-4-mini:3.8b" in s.reason_phrase()


def test_reason_phrase_when_healthy():
    s = OllamaStatus(
        host="http://localhost:11434",
        daemon_reachable=True,
        available_models=("aria-garden:latest",),
    )
    assert "ready" in s.reason_phrase().lower()


def test_healthy_property_invariants():
    """daemon_reachable + (no model OR model_present) → healthy."""
    # Down → not healthy
    assert OllamaStatus(host="x", daemon_reachable=False).healthy is False

    # Up, no model asked → healthy
    assert OllamaStatus(host="x", daemon_reachable=True).healthy is True

    # Up, model present → healthy
    assert OllamaStatus(
        host="x", daemon_reachable=True,
        model="m", model_present=True,
    ).healthy is True

    # Up, model missing → NOT healthy
    assert OllamaStatus(
        host="x", daemon_reachable=True,
        model="m", model_present=False,
    ).healthy is False
