"""Tests for the diagnosed offline fallback (v0.2.26.0).

When the LLM call fails, the interpreter used to fall back with a bare
"interpreter offline" hint that gave the operator no idea why. These
tests verify the new behavior:

  1. When no ollama_client is provided, the fallback is still the bare
     "offline" message (no diagnosis possible, none claimed).
  2. When the client's probe says the daemon is unreachable, the hint
     surfaces THAT specifically.
  3. When the client's probe says a model is missing, the hint surfaces
     the model name AND the `ollama pull` command.
  4. When probe itself raises, the fallback degrades to bare offline
     (the diagnostic must never break the fallback).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from sovereign_agent.intents import Conversation, ConversationContext
from sovereign_agent.interpreter import interpret
from sovereign_agent.ollama_client import OllamaStatus


pytestmark = pytest.mark.asyncio


# ─── (1) no client → bare offline message ──────────────────────────────────


async def test_no_ollama_client_gives_bare_offline_message():
    intent = await interpret("hello", context=ConversationContext())
    assert isinstance(intent, Conversation)
    assert "interpreter offline" in (intent.reply_hint or "")
    # No diagnostic suffix when there's nothing to probe
    assert "·" not in (intent.reply_hint or "")


# ─── (2) daemon unreachable → operator sees host in hint ───────────────────


async def test_offline_hint_names_unreachable_host():
    """When the LLM call fails AND probe reports daemon-down, the offline
    hint surfaces the host so the operator knows where to look."""
    client = MagicMock()
    # chat() fails — simulates real connection-refused
    client.chat = AsyncMock(side_effect=ConnectionError("refused"))
    # probe() reports daemon down
    client.probe = AsyncMock(return_value=OllamaStatus(
        host="http://localhost:11434",
        daemon_reachable=False,
        error="ConnectionError: refused",
    ))

    intent = await interpret(
        "hello",
        context=ConversationContext(),
        ollama_client=client,
        llm_timeout_seconds=0.5,
    )

    hint = intent.reply_hint or ""
    assert "interpreter offline" in hint
    assert "Ollama unreachable" in hint
    assert "http://localhost:11434" in hint


# ─── (3) the original failure mode — model not pulled ──────────────────────


async def test_offline_hint_names_missing_model_and_suggests_pull():
    """This is the exact failure that motivated the whole patch.
    Operator had `phi-4-mini:3.8b` as the configured interpreter model but
    never pulled it. They should see WHICH model is missing and HOW to fix.
    """
    client = MagicMock()
    client.chat = AsyncMock(side_effect=Exception("model 'phi-4-mini:3.8b' not found"))
    client.probe = AsyncMock(return_value=OllamaStatus(
        host="http://localhost:11434",
        daemon_reachable=True,
        model="phi-4-mini:3.8b",
        model_present=False,
        available_models=("aria-garden:latest",),
    ))

    intent = await interpret(
        "hello",
        context=ConversationContext(),
        ollama_client=client,
        llm_timeout_seconds=0.5,
    )

    hint = intent.reply_hint or ""
    assert "phi-4-mini:3.8b" in hint
    assert "ollama pull phi-4-mini:3.8b" in hint


# ─── (4) probe must never break the fallback ───────────────────────────────


async def test_offline_fallback_survives_probe_raising():
    """The diagnostic is best-effort. If probe itself raises, the
    operator still gets the bare offline message — never an exception."""
    client = MagicMock()
    client.chat = AsyncMock(side_effect=Exception("primary call failed"))
    client.probe = AsyncMock(side_effect=RuntimeError("probe itself blew up"))

    intent = await interpret(
        "hello",
        context=ConversationContext(),
        ollama_client=client,
        llm_timeout_seconds=0.5,
    )
    # We get a Conversation, not an exception
    assert isinstance(intent, Conversation)
    assert "interpreter offline" in (intent.reply_hint or "")


# ─── Reply-voice + save_to invariants preserved ────────────────────────────


async def test_diagnosed_fallback_preserves_save_behavior():
    """The whole point of the offline path is to hold the operator's
    message safely. The diagnosis must not change that."""
    client = MagicMock()
    client.chat = AsyncMock(side_effect=Exception("boom"))
    client.probe = AsyncMock(return_value=OllamaStatus(
        host="http://localhost:11434",
        daemon_reachable=False,
        error="x",
    ))

    intent = await interpret(
        "remember: my back hurts today",
        context=ConversationContext(),
        ollama_client=client,
        llm_timeout_seconds=0.5,
    )
    assert isinstance(intent, Conversation)
    assert intent.text == "remember: my back hurts today"
    assert "context" in intent.save_to
    assert intent.reply_voice == "quiet"
