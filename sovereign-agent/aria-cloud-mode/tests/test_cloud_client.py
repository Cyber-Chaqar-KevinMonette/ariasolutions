"""Tests for CloudClient -- the Fast Free Cloud adapter.

Kevin, 2026-07-25: "let's add a fast free cloud mode?" ... "fall back can
be local when cloud mode is unavailable or refusing a task." These tests
prove the three required behaviors: (1) a good cloud reply is returned in
OllamaClient's own shape, (2) any cloud failure falls back to a real local
OllamaClient.chat() call, (3) a refusal-shaped reply also falls back
locally rather than being handed back as the answer.
"""
from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock

import pytest

from sovereign_agent.cloud_client import CloudClient, _looks_like_refusal


@dataclass
class _FakeReply:
    text: str
    model: str = "groq/llama-3.3-70b"
    message: dict | None = None
    prompt_tokens: int = 12
    completion_tokens: int = 34


class _FakePool:
    def __init__(self, reply=None, exc=None):
        self._reply = reply
        self._exc = exc
        self.achat = AsyncMock(side_effect=exc) if exc else AsyncMock(return_value=reply)


def test_looks_like_refusal_detects_common_phrasing():
    assert _looks_like_refusal("I can't help with that request.")
    assert _looks_like_refusal("As an AI language model, I cannot do this.")
    assert _looks_like_refusal("")
    assert _looks_like_refusal("   ")


def test_looks_like_refusal_false_on_a_normal_answer():
    assert not _looks_like_refusal("Here is the CAP theorem in one sentence: ...")


@pytest.mark.asyncio
async def test_chat_returns_ollama_shaped_dict_on_cloud_success():
    reply = _FakeReply(
        text="Here's the answer.",
        message={"role": "assistant", "content": "Here's the answer."},
    )
    client = CloudClient()
    client._pool = _FakePool(reply=reply)

    result = await client.chat(model="qwen2.5:1.5b", messages=[{"role": "user", "content": "hi"}])

    assert result["message"]["content"] == "Here's the answer."
    assert result["prompt_eval_count"] == 12
    assert result["eval_count"] == 34
    assert result["done"] is True
    assert "eval_duration" in result


@pytest.mark.asyncio
async def test_chat_passes_tool_calls_through_untranslated():
    tool_calls = [{"id": "1", "type": "function",
                   "function": {"name": "read_file", "arguments": '{"path": "x.py"}'}}]
    reply = _FakeReply(text="", message={"role": "assistant", "content": None,
                                          "tool_calls": tool_calls})
    client = CloudClient()
    client._pool = _FakePool(reply=reply)

    result = await client.chat(model="qwen2.5:1.5b", messages=[{"role": "user", "content": "hi"}],
                                tools=[{"type": "function", "function": {"name": "read_file"}}])

    assert result["message"]["tool_calls"] == tool_calls


@pytest.mark.asyncio
async def test_chat_falls_back_to_local_on_cloud_exception():
    client = CloudClient()
    client._pool = _FakePool(exc=RuntimeError("all providers exhausted"))
    fake_local = AsyncMock()
    fake_local.chat = AsyncMock(return_value={"message": {"role": "assistant",
                                                           "content": "local answer"}})
    client._local = fake_local

    result = await client.chat(model="qwen2.5:1.5b", messages=[{"role": "user", "content": "hi"}])

    fake_local.chat.assert_called_once()
    assert result["message"]["content"] == "local answer"


@pytest.mark.asyncio
async def test_chat_falls_back_to_local_on_refusal():
    reply = _FakeReply(text="I can't help with that.",
                       message={"role": "assistant", "content": "I can't help with that."})
    client = CloudClient()
    client._pool = _FakePool(reply=reply)
    fake_local = AsyncMock()
    fake_local.chat = AsyncMock(return_value={"message": {"role": "assistant",
                                                           "content": "local answer"}})
    client._local = fake_local

    result = await client.chat(model="qwen2.5:1.5b", messages=[{"role": "user", "content": "hi"}])

    fake_local.chat.assert_called_once()
    assert result["message"]["content"] == "local answer"


@pytest.mark.asyncio
async def test_chat_falls_back_to_local_when_groq_credits_run_out():
    """Kevin, 2026-07-25: "if she is working and runs out of groq credits
    somehow -- she can keep working by falling back to local models."
    freellmpool raises AllProvidersExhausted when every configured
    provider (Groq included) is rate-limited/out of quota -- that's just
    another exception this method's generic `except Exception` already
    catches, same fallback path as any other cloud failure.

    Skips cleanly if freellmpool isn't installed (it's an optional
    dependency) -- the generic-exception fallback is already proven by
    the other tests in this file regardless."""
    errors = pytest.importorskip("freellmpool.errors")
    AllProvidersExhausted = errors.AllProvidersExhausted

    client = CloudClient()
    client._pool = _FakePool(
        exc=AllProvidersExhausted([("groq", "HTTP 429 — quota exhausted")])
    )
    fake_local = AsyncMock()
    fake_local.chat = AsyncMock(return_value={"message": {"role": "assistant",
                                                           "content": "local answer"}})
    client._local = fake_local

    result = await client.chat(model="qwen2.5:1.5b", messages=[{"role": "user", "content": "hi"}])

    fake_local.chat.assert_called_once()
    assert result["message"]["content"] == "local answer"


@pytest.mark.asyncio
async def test_chat_falls_back_to_local_when_there_is_no_internet():
    """Kevin, 2026-07-25: "the system should fall back to local if there
    is no internet connection." A connection error from httpx (inside
    freellmpool's own transport) is just another exception this method's
    generic `except Exception` already catches -- same fallback path as
    any other cloud failure, made explicit here so it can't regress."""
    import httpx

    client = CloudClient()
    client._pool = _FakePool(exc=httpx.ConnectError("network is unreachable"))
    fake_local = AsyncMock()
    fake_local.chat = AsyncMock(return_value={"message": {"role": "assistant",
                                                           "content": "local answer"}})
    client._local = fake_local

    result = await client.chat(model="qwen2.5:1.5b", messages=[{"role": "user", "content": "hi"}])

    fake_local.chat.assert_called_once()
    assert result["message"]["content"] == "local answer"


@pytest.mark.asyncio
async def test_chat_falls_back_to_local_when_freellmpool_not_installed():
    """Simulates the package being absent regardless of whether it happens
    to be installed in whatever env runs this test (it now IS installed on
    Kevin's machine, by his own request -- the test must not depend on
    that ambient, environment-specific fact)."""
    client = CloudClient()

    async def _raise_import_error():
        raise ImportError("No module named 'freellmpool'")

    client._get_pool = _raise_import_error
    fake_local = AsyncMock()
    fake_local.chat = AsyncMock(return_value={"message": {"role": "assistant",
                                                           "content": "local answer"}})
    client._local = fake_local

    result = await client.chat(model="qwen2.5:1.5b", messages=[{"role": "user", "content": "hi"}])

    fake_local.chat.assert_called_once()
    assert result["message"]["content"] == "local answer"


@pytest.mark.asyncio
async def test_chat_forwards_args_to_local_fallback_unchanged():
    from sovereign_agent.ollama_client import CallKind

    client = CloudClient()
    client._pool = _FakePool(exc=RuntimeError("boom"))
    fake_local = AsyncMock()
    fake_local.chat = AsyncMock(return_value={"message": {"role": "assistant", "content": "x"}})
    client._local = fake_local

    tools = [{"type": "function", "function": {"name": "noop"}}]
    messages = [{"role": "user", "content": "hi"}]
    await client.chat(model="m1", messages=messages, tools=tools,
                      call_kind=CallKind.PLAN, temperature=0.7, num_ctx=4096)

    fake_local.chat.assert_called_once_with(
        model="m1", messages=messages, tools=tools,
        call_kind=CallKind.PLAN, temperature=0.7, num_ctx=4096,
    )
