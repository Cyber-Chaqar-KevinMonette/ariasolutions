"""Sync tests for _is_transient_error classification (v0.2.26.0).

Separated from test_interpreter_retry_split.py so pytest-asyncio's auto
mode doesn't spuriously tag these sync tests as coroutines.
"""
from __future__ import annotations

import asyncio

import pytest

from sovereign_agent.interpreter import _is_transient_error


def test_timeout_is_transient():
    assert _is_transient_error(asyncio.TimeoutError()) is True


def test_connection_error_is_transient():
    assert _is_transient_error(ConnectionError("refused")) is True


def test_os_error_is_transient():
    assert _is_transient_error(OSError("broken pipe")) is True


def test_model_not_found_is_deterministic():
    """The original failure mode. Must NOT retry — surface fast."""
    assert _is_transient_error(Exception("model 'phi-4-mini:3.8b' not found")) is False


def test_404_string_is_deterministic():
    assert _is_transient_error(Exception("HTTP 404 from /api/chat")) is False


def test_unknown_exception_defaults_to_deterministic():
    """Don't burn cycles retrying things we don't recognize."""
    assert _is_transient_error(ValueError("something weird")) is False


def test_ollama_response_error_5xx_is_transient():
    """If ollama-python's ResponseError carries a 5xx, treat as transient."""
    try:
        from ollama import ResponseError
    except ImportError:
        pytest.skip("ollama.ResponseError not available")

    try:
        exc = ResponseError("server error")
    except TypeError:
        exc = ResponseError("server error", 503)  # older signature
    exc.status_code = 503  # type: ignore[attr-defined]
    assert _is_transient_error(exc) is True


def test_ollama_response_error_4xx_is_deterministic():
    try:
        from ollama import ResponseError
    except ImportError:
        pytest.skip("ollama.ResponseError not available")

    try:
        exc = ResponseError("not found")
    except TypeError:
        exc = ResponseError("not found", 404)
    exc.status_code = 404  # type: ignore[attr-defined]
    assert _is_transient_error(exc) is False
