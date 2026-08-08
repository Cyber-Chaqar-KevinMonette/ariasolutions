"""OllamaClient capability detection tests.

Ensures that:
  - Models that advertise ``thinking`` get think=True respected
  - Models that don't (e.g., llama3-groq-tool-use) auto-fall back to think=False
  - The capability cache prevents repeated /api/show calls
  - Failure to query show falls back to broadest assumed capabilities
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sovereign_agent.ollama_client import CallKind, OllamaClient


pytestmark = pytest.mark.asyncio


@patch("sovereign_agent.ollama_client.ollama.AsyncClient")
async def test_supports_thinking_true_for_capable_model(mock_client_class):
    mock_aclient = MagicMock()
    mock_aclient.show = AsyncMock(return_value={
        "capabilities": ["completion", "tools", "thinking"],
    })
    mock_client_class.return_value = mock_aclient

    client = OllamaClient()
    assert await client.supports_thinking("qwen3:8b") is True


@patch("sovereign_agent.ollama_client.ollama.AsyncClient")
async def test_supports_thinking_false_for_groq_model(mock_client_class):
    mock_aclient = MagicMock()
    mock_aclient.show = AsyncMock(return_value={
        "capabilities": ["completion", "tools"],   # no thinking
    })
    mock_client_class.return_value = mock_aclient

    client = OllamaClient()
    assert await client.supports_thinking("llama3-groq-tool-use:8b") is False


@patch("sovereign_agent.ollama_client.ollama.AsyncClient")
async def test_capability_cache_prevents_repeated_calls(mock_client_class):
    mock_aclient = MagicMock()
    mock_aclient.show = AsyncMock(return_value={
        "capabilities": ["completion", "tools"],
    })
    mock_client_class.return_value = mock_aclient

    client = OllamaClient()
    await client.supports_thinking("model-x")
    await client.supports_thinking("model-x")
    await client.supports_thinking("model-x")

    # show() should only fire ONCE despite three queries
    assert mock_aclient.show.await_count == 1


@patch("sovereign_agent.ollama_client.ollama.AsyncClient")
async def test_failed_show_assumes_broad_capabilities(mock_client_class):
    """If /api/show fails, we don't disable features pre-emptively."""
    mock_aclient = MagicMock()
    mock_aclient.show = AsyncMock(side_effect=RuntimeError("ollama down"))
    mock_client_class.return_value = mock_aclient

    client = OllamaClient()
    # Don't disable thinking just because we can't probe — let the actual call
    # surface any real error
    assert await client.supports_thinking("anything") is True


@patch("sovereign_agent.ollama_client.ollama.AsyncClient")
async def test_chat_disables_think_for_non_capable_model(mock_client_class):
    """Even if policy wants thinking, it's suppressed for incapable models."""
    mock_aclient = MagicMock()
    mock_aclient.show = AsyncMock(return_value={
        "capabilities": ["completion", "tools"],   # no thinking
    })
    mock_aclient.chat = AsyncMock(return_value={"message": {"content": "ok"}})
    mock_client_class.return_value = mock_aclient

    client = OllamaClient()
    await client.chat(
        model="llama3-groq-tool-use:8b",
        messages=[{"role": "user", "content": "hi"}],
        call_kind=CallKind.PLAN,   # plan_only policy WOULD want thinking
    )

    # Verify the chat call had think=False despite plan_only wanting True
    call_kwargs = mock_aclient.chat.await_args.kwargs
    assert call_kwargs["think"] is False


@patch("sovereign_agent.ollama_client.ollama.AsyncClient")
async def test_chat_enables_think_for_capable_model_when_policy_wants(mock_client_class):
    mock_aclient = MagicMock()
    mock_aclient.show = AsyncMock(return_value={
        "capabilities": ["completion", "tools", "thinking"],
    })
    mock_aclient.chat = AsyncMock(return_value={"message": {"content": "ok"}})
    mock_client_class.return_value = mock_aclient

    client = OllamaClient()
    await client.chat(
        model="qwen3:8b",
        messages=[{"role": "user", "content": "hi"}],
        call_kind=CallKind.PLAN,
    )
    call_kwargs = mock_aclient.chat.await_args.kwargs
    assert call_kwargs["think"] is True


@patch("sovereign_agent.ollama_client.ollama.AsyncClient")
async def test_chat_dispatch_default_no_think_under_plan_only(mock_client_class):
    """Under plan_only policy, DISPATCH calls go without thinking even on
    capable models — that's the whole point of plan_only."""
    mock_aclient = MagicMock()
    mock_aclient.show = AsyncMock(return_value={
        "capabilities": ["completion", "tools", "thinking"],
    })
    mock_aclient.chat = AsyncMock(return_value={"message": {"content": "ok"}})
    mock_client_class.return_value = mock_aclient

    client = OllamaClient()
    await client.chat(
        model="qwen3:8b",
        messages=[{"role": "user", "content": "hi"}],
        call_kind=CallKind.DISPATCH,
    )
    call_kwargs = mock_aclient.chat.await_args.kwargs
    assert call_kwargs["think"] is False
