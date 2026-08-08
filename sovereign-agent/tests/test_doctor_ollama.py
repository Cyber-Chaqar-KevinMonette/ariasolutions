"""Tests for the new Ollama checks in `sov doctor` (v0.2.26.0).

These verify the two new check functions:

  1. check_ollama_daemon — error when unreachable, ok when reachable.
  2. check_ollama_models — error when REQUIRED slots are un-pulled,
     warning when only OPTIONAL slots are un-pulled, ok when all set.

The slot-coverage test is the one that catches the original failure
mode: an operator with `AGENT_INTERPRETER_MODEL=phi-4-mini:3.8b` set
but no such model in their library — doctor should now flag it
explicitly with the exact `ollama pull` command to run.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sovereign_agent.doctor import check_ollama_daemon, check_ollama_models


# ─── daemon check ──────────────────────────────────────────────────────────


@patch("sovereign_agent.ollama_client.ollama.AsyncClient")
def test_daemon_check_errors_when_unreachable(mock_client_class):
    mock_aclient = MagicMock()
    mock_aclient.list = AsyncMock(side_effect=ConnectionError("refused"))
    mock_client_class.return_value = mock_aclient

    result = check_ollama_daemon()
    assert result.level == "error"
    assert "unreachable" in result.summary
    # Detail should give an actionable hint
    assert "ollama serve" in result.detail or "systemctl" in result.detail


@patch("sovereign_agent.ollama_client.ollama.AsyncClient")
def test_daemon_check_ok_when_reachable(mock_client_class):
    mock_aclient = MagicMock()
    mock_aclient.list = AsyncMock(return_value={
        "models": [
            {"name": "aria-garden:latest"},
            {"name": "nemotron-3-nano:4b"},
        ],
    })
    mock_client_class.return_value = mock_aclient

    result = check_ollama_daemon()
    assert result.level == "ok"
    assert "reachable" in result.summary


# ─── models check ──────────────────────────────────────────────────────────


@pytest.fixture
def pin_slots():
    """Pin SETTINGS model slots for a single test, then restore.

    SETTINGS is a frozen dataclass — pytest.monkeypatch.setattr can't
    teardown a frozen attribute. We bypass with ``object.__setattr__``
    (the same pattern conftest.py uses) and yield a callable so the
    test can declare which slots it cares about::

        def test_x(pin_slots):
            pin_slots(interpreter_model="x", fast_model="y", ...)
            ...

    On teardown, all originally-modified slots are restored.
    """
    from sovereign_agent.config import SETTINGS

    originals: dict[str, str] = {}

    def _pin(**slot_values: str) -> None:
        for name, value in slot_values.items():
            originals.setdefault(name, getattr(SETTINGS, name))
            object.__setattr__(SETTINGS, name, value)

    yield _pin

    for name, value in originals.items():
        object.__setattr__(SETTINGS, name, value)


@patch("sovereign_agent.ollama_client.ollama.AsyncClient")
def test_models_check_errors_when_required_slot_un_pulled(
    mock_client_class, pin_slots,
):
    """The original failure: interpreter slot points at a model that
    isn't pulled. This must be a HARD error with the pull command.

    v0.2.26.0: pin every slot explicitly so the assertion holds
    regardless of the host's AGENT_* env vars. The previous version
    of this test read SETTINGS at runtime, which made it pass on a
    clean box but fail on any operator with custom slots configured.
    """
    pin_slots(
        interpreter_model="phi-4-mini:3.8b",
        fast_model="phi-4-mini:3.8b",
        orchestrator_model="qwen3:8b",
        coder_model="qwen2.5-coder:7b",
        embed_model="nomic-embed-text",
        reflector_model="qwen3:8b",
        vision_model="llava:7b",
    )

    mock_aclient = MagicMock()
    mock_aclient.list = AsyncMock(return_value={
        "models": [
            # Has the orchestrator/coder/embed/reflector slots above...
            # but NOT phi-4-mini (interpreter+fast slot).
            {"name": "qwen3:8b"},
            {"name": "qwen2.5-coder:7b"},
            {"name": "nomic-embed-text:latest"},
            {"name": "llava:7b"},
        ],
    })
    mock_client_class.return_value = mock_aclient

    result = check_ollama_models()
    assert result.level == "error"
    # The detail must name the missing model and the exact fix
    assert "phi-4-mini" in result.detail
    assert "ollama pull phi-4-mini:3.8b" in result.detail


@patch("sovereign_agent.ollama_client.ollama.AsyncClient")
def test_models_check_warns_only_when_vision_missing(mock_client_class, pin_slots):
    """Vision is optional — missing it is a warning, not an error."""
    pin_slots(
        interpreter_model="aria-garden:latest",
        fast_model="nemotron-3-nano:4b",
        orchestrator_model="qwen3:8b",
        coder_model="qwen2.5-coder:7b",
        embed_model="nomic-embed-text",
        reflector_model="nemotron-3-nano:4b",
        vision_model="llava:7b",
    )

    # Library has every required slot's pinned model, but no llava
    mock_aclient = MagicMock()
    mock_aclient.list = AsyncMock(return_value={
        "models": [
            {"name": "qwen3:8b"},
            {"name": "qwen2.5-coder:7b"},
            {"name": "nomic-embed-text:latest"},
            {"name": "nemotron-3-nano:4b"},
            {"name": "aria-garden:latest"},
        ],
    })
    mock_client_class.return_value = mock_aclient

    result = check_ollama_models()
    assert result.level == "warning"
    assert "optional" in result.summary or "optional" in result.detail


@patch("sovereign_agent.ollama_client.ollama.AsyncClient")
def test_models_check_ok_when_all_slots_present(mock_client_class, pin_slots):
    pin_slots(
        interpreter_model="aria-garden:latest",
        fast_model="nemotron-3-nano:4b",
        orchestrator_model="qwen3:8b",
        coder_model="qwen2.5-coder:7b",
        embed_model="nomic-embed-text",
        reflector_model="nemotron-3-nano:4b",
        vision_model="llava:7b",
    )

    mock_aclient = MagicMock()
    mock_aclient.list = AsyncMock(return_value={
        "models": [
            {"name": "qwen3:8b"},
            {"name": "qwen2.5-coder:7b"},
            {"name": "nomic-embed-text:latest"},
            {"name": "nemotron-3-nano:4b"},
            {"name": "aria-garden:latest"},
            {"name": "llava:7b"},
        ],
    })
    mock_client_class.return_value = mock_aclient

    result = check_ollama_models()
    assert result.level == "ok"


@patch("sovereign_agent.ollama_client.ollama.AsyncClient")
def test_models_check_warns_when_daemon_unreachable(mock_client_class):
    """If we can't reach the daemon, we can't verify models — surface
    that gracefully, not as an error (the daemon check already errored)."""
    mock_aclient = MagicMock()
    mock_aclient.list = AsyncMock(side_effect=ConnectionError("refused"))
    mock_client_class.return_value = mock_aclient

    result = check_ollama_models()
    assert result.level == "warning"
    assert "cannot verify" in result.summary


# ─── Integration: full diagnostic still works ──────────────────────────────


@patch("sovereign_agent.ollama_client.ollama.AsyncClient")
def test_run_diagnostic_includes_new_ollama_checks(mock_client_class):
    """Smoke test: the driver picks up the new checks and the report
    still renders without raising."""
    from sovereign_agent.doctor import run_diagnostic

    mock_aclient = MagicMock()
    mock_aclient.list = AsyncMock(return_value={"models": []})
    mock_client_class.return_value = mock_aclient

    report = run_diagnostic()
    names = [c.name for c in report.checks]
    assert "ollama daemon" in names
    assert "ollama models" in names
    # render() must not raise even with errors present
    rendered = report.render()
    assert "ollama daemon" in rendered
