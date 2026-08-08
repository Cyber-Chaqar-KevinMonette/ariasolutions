"""Tests for the Ollama reachability probe (v0.2.26.0).

The probe exists so the interpreter's offline message can say something
useful instead of just "offline". These tests cover the cases an operator
will actually hit:

  1. Daemon unreachable (connection refused) — probe doesn't raise,
     status carries an error message.
  2. Timeout — same shape as (1) but a different error label.
  3. Daemon up, no model asked — healthy, model_present is None.
  4. Daemon up, model present — healthy, model_present is True.
  5. Daemon up, model missing — NOT healthy, model_present is False,
     reason_phrase suggests the right `ollama pull` command.
  6. `:latest` normalization — "foo" and "foo:latest" are equivalent.
  7. Response-shape resilience — dict vs object listings both parse.
  8. Instance shortcut — client.probe() returns the same answer.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sovereign_agent.ollama_client import (
    OllamaClient,
    OllamaStatus,
    probe_ollama,
)


# ─── Async probe behavior ──────────────────────────────────────────────────
# Sync invariant tests for OllamaStatus.reason_phrase() live in
# test_ollama_status.py so the auto-asyncio mark in this file doesn't
# spuriously tag them.


pytestmark = pytest.mark.asyncio


# ─── (1) connection refused ────────────────────────────────────────────────


@patch("sovereign_agent.ollama_client.ollama.AsyncClient")
async def test_probe_returns_unreachable_on_connection_error(mock_client_class):
    mock_aclient = MagicMock()
    mock_aclient.list = AsyncMock(
        side_effect=ConnectionError("Connection refused")
    )
    mock_client_class.return_value = mock_aclient

    status = await probe_ollama("http://localhost:11434")

    assert status.daemon_reachable is False
    assert status.host == "http://localhost:11434"
    assert status.error is not None
    assert "ConnectionError" in status.error
    assert status.healthy is False


# ─── (2) timeout ───────────────────────────────────────────────────────────


@patch("sovereign_agent.ollama_client.ollama.AsyncClient")
async def test_probe_returns_unreachable_on_timeout(mock_client_class):
    import asyncio

    async def hang():
        await asyncio.sleep(10)

    mock_aclient = MagicMock()
    mock_aclient.list = AsyncMock(side_effect=hang)
    mock_client_class.return_value = mock_aclient

    status = await probe_ollama("http://localhost:11434", timeout_seconds=0.1)

    assert status.daemon_reachable is False
    assert "timed out" in (status.error or "")


# ─── (3) daemon up, no model asked ─────────────────────────────────────────


@patch("sovereign_agent.ollama_client.ollama.AsyncClient")
async def test_probe_healthy_without_model_query(mock_client_class):
    mock_aclient = MagicMock()
    mock_aclient.list = AsyncMock(return_value={
        "models": [
            {"name": "aria-garden:latest"},
            {"name": "nemotron-3-nano:4b"},
        ],
    })
    mock_client_class.return_value = mock_aclient

    status = await probe_ollama("http://localhost:11434")

    assert status.daemon_reachable is True
    assert status.model is None
    assert status.model_present is None  # tri-state: not asked
    assert status.healthy is True
    assert "aria-garden:latest" in status.available_models
    assert "nemotron-3-nano:4b" in status.available_models


# ─── (4) daemon up, model present ──────────────────────────────────────────


@patch("sovereign_agent.ollama_client.ollama.AsyncClient")
async def test_probe_model_present(mock_client_class):
    mock_aclient = MagicMock()
    mock_aclient.list = AsyncMock(return_value={
        "models": [{"name": "aria-garden:latest"}],
    })
    mock_client_class.return_value = mock_aclient

    status = await probe_ollama("http://localhost:11434", model="aria-garden:latest")

    assert status.daemon_reachable is True
    assert status.model_present is True
    assert status.healthy is True
    assert "ready" in status.reason_phrase().lower()


# ─── (5) daemon up, model MISSING — the failure mode that motivated the probe


@patch("sovereign_agent.ollama_client.ollama.AsyncClient")
async def test_probe_model_missing_suggests_pull_command(mock_client_class):
    mock_aclient = MagicMock()
    mock_aclient.list = AsyncMock(return_value={
        "models": [{"name": "aria-garden:latest"}],
    })
    mock_client_class.return_value = mock_aclient

    status = await probe_ollama(
        "http://localhost:11434", model="phi-4-mini:3.8b",
    )

    assert status.daemon_reachable is True
    assert status.model_present is False
    assert status.healthy is False
    phrase = status.reason_phrase()
    assert "phi-4-mini:3.8b" in phrase
    assert "ollama pull phi-4-mini:3.8b" in phrase


# ─── (6) :latest normalization ─────────────────────────────────────────────


@patch("sovereign_agent.ollama_client.ollama.AsyncClient")
async def test_probe_treats_implicit_latest_as_equivalent(mock_client_class):
    """Library lists 'foo:latest'; operator asked for 'foo'. Same thing."""
    mock_aclient = MagicMock()
    mock_aclient.list = AsyncMock(return_value={
        "models": [{"name": "nomic-embed-text:latest"}],
    })
    mock_client_class.return_value = mock_aclient

    status = await probe_ollama(
        "http://localhost:11434", model="nomic-embed-text",
    )
    assert status.model_present is True


@patch("sovereign_agent.ollama_client.ollama.AsyncClient")
async def test_probe_treats_explicit_latest_as_equivalent(mock_client_class):
    """Library lists 'foo'; operator asked for 'foo:latest'. Same thing."""
    mock_aclient = MagicMock()
    mock_aclient.list = AsyncMock(return_value={
        "models": [{"name": "nomic-embed-text"}],
    })
    mock_client_class.return_value = mock_aclient

    status = await probe_ollama(
        "http://localhost:11434", model="nomic-embed-text:latest",
    )
    assert status.model_present is True


# ─── (7) response-shape resilience ─────────────────────────────────────────


@patch("sovereign_agent.ollama_client.ollama.AsyncClient")
async def test_probe_parses_object_style_response(mock_client_class):
    """Newer ollama-python returns objects, not dicts. Probe handles both."""
    class _Entry:
        def __init__(self, name): self.model = name
    class _Listing:
        def __init__(self): self.models = [_Entry("aria-garden:latest")]

    mock_aclient = MagicMock()
    mock_aclient.list = AsyncMock(return_value=_Listing())
    mock_client_class.return_value = mock_aclient

    status = await probe_ollama("http://localhost:11434", model="aria-garden:latest")
    assert status.daemon_reachable is True
    assert status.model_present is True


# ─── (8) instance shortcut ─────────────────────────────────────────────────


@patch("sovereign_agent.ollama_client.ollama.AsyncClient")
async def test_client_probe_method_delegates_to_module_function(mock_client_class):
    mock_aclient = MagicMock()
    mock_aclient.list = AsyncMock(return_value={
        "models": [{"name": "aria-garden:latest"}],
    })
    mock_client_class.return_value = mock_aclient

    client = OllamaClient(host="http://localhost:11434")
    status = await client.probe(model="aria-garden:latest")
    assert isinstance(status, OllamaStatus)
    assert status.host == "http://localhost:11434"
    assert status.model_present is True
