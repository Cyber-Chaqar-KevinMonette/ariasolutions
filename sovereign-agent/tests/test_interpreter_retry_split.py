"""Tests for the transient-vs-deterministic retry split (v0.2.26.0) —
end-to-end async behavior. Sync classification tests live in
test_interpreter_error_classification.py.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from sovereign_agent.interpreter import _chat_with_transient_retry


pytestmark = pytest.mark.asyncio


# ─── End-to-end retry behavior ─────────────────────────────────────────────


async def test_retry_helper_succeeds_on_first_try():
    client = MagicMock()
    client.chat = AsyncMock(return_value={"message": {"content": "ok"}})

    result = await _chat_with_transient_retry(
        client, model="x", messages=[], timeout_seconds=1.0,
    )
    assert result == {"message": {"content": "ok"}}
    assert client.chat.await_count == 1


async def test_retry_helper_retries_once_on_transient():
    """Transient error → one retry → success on second try."""
    client = MagicMock()
    client.chat = AsyncMock(side_effect=[
        ConnectionError("refused"),
        {"message": {"content": "ok"}},
    ])

    result = await _chat_with_transient_retry(
        client, model="x", messages=[], timeout_seconds=1.0,
    )
    assert result == {"message": {"content": "ok"}}
    assert client.chat.await_count == 2


async def test_retry_helper_fails_fast_on_deterministic():
    """Deterministic error → no retry, raise immediately."""
    client = MagicMock()
    err = Exception("model 'phi-4-mini:3.8b' not found")
    client.chat = AsyncMock(side_effect=err)

    with pytest.raises(Exception, match="not found"):
        await _chat_with_transient_retry(
            client, model="x", messages=[], timeout_seconds=1.0,
        )
    # Exactly one call — no retry
    assert client.chat.await_count == 1


async def test_retry_helper_gives_up_after_two_transients():
    """Two consecutive transient errors → raise the second one."""
    client = MagicMock()
    client.chat = AsyncMock(side_effect=[
        ConnectionError("refused #1"),
        ConnectionError("refused #2"),
    ])

    with pytest.raises(ConnectionError, match="#2"):
        await _chat_with_transient_retry(
            client, model="x", messages=[], timeout_seconds=1.0,
        )
    assert client.chat.await_count == 2
