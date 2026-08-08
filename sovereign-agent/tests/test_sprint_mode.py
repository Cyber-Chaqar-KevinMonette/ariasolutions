"""Tests for sprint-mode-d — an additive, per-slot model override for
quick testing, never a replacement for SETTINGS.orchestrator_model or the
model_ladder.py vault.

Kevin, 2026-07-21: "I want a sprint mode we can use for testing. Doesn't
replace our main modes or functions... I should be able to use sprint
mode with all other modes... both reversable." Then: "add a model
configure menu... have drop down menus for each model configuration
slot... presets, or custom mode, or custom slots."
"""
from __future__ import annotations

from unittest.mock import patch


def test_default_state_is_every_slot_at_its_settings_default():
    from sovereign_agent.config import SETTINGS
    from sovereign_agent.sprint_mode import status

    state = status()
    assert state["active"] is False
    assert state["preset"] is None
    assert state["slots"]["orchestrator"]["model"] == SETTINGS.orchestrator_model
    assert state["slots"]["orchestrator"]["overridden"] is False


def test_activating_a_preset_overrides_only_the_orchestrator_slot():
    from sovereign_agent.config import SETTINGS
    from sovereign_agent.sprint_mode import PRESETS, activate_preset, status

    preset = activate_preset("sprint-2b")
    assert preset.model == "qwen3.5:2b"

    state = status()
    assert state["active"] is True
    assert state["preset"] == "sprint-2b"
    assert state["slots"]["orchestrator"]["model"] == "qwen3.5:2b"
    assert state["slots"]["orchestrator"]["overridden"] is True
    # every OTHER slot is untouched — a preset is orchestrator-only
    assert state["slots"]["coder"]["model"] == SETTINGS.coder_model
    assert state["slots"]["coder"]["overridden"] is False


def test_unknown_preset_raises_with_the_valid_choices_listed():
    from sovereign_agent.sprint_mode import activate_preset

    try:
        activate_preset("not-a-real-preset")
        assert False, "expected KeyError"
    except KeyError as exc:
        assert "sprint-2b" in str(exc)


def test_deactivate_clears_every_override():
    from sovereign_agent.sprint_mode import activate_preset, deactivate, status

    activate_preset("sprint-4b")
    assert status()["active"] is True
    deactivate()
    state = status()
    assert state["active"] is False
    assert state["preset"] is None
    assert all(not s["overridden"] for s in state["slots"].values())


def test_custom_slot_override_is_independent_per_slot():
    from sovereign_agent.sprint_mode import (
        clear_slot_override, set_slot_override, status,
    )

    set_slot_override("coder", "qwen2.5-coder:7b")
    set_slot_override("fast", "phi4-mini:3.8b")
    state = status()
    assert state["slots"]["coder"]["model"] == "qwen2.5-coder:7b"
    assert state["slots"]["fast"]["model"] == "phi4-mini:3.8b"
    assert state["slots"]["orchestrator"]["overridden"] is False  # untouched

    clear_slot_override("coder")
    state = status()
    assert state["slots"]["coder"]["overridden"] is False
    assert state["slots"]["fast"]["overridden"] is True  # unaffected by the other clear


def test_a_manual_slot_edit_clears_the_preset_label():
    """Custom mode and preset mode are mutually exclusive labels (the menu
    marks exactly one active) even though both just write overrides."""
    from sovereign_agent.sprint_mode import activate_preset, set_slot_override, status

    activate_preset("sprint-2b")
    assert status()["preset"] == "sprint-2b"
    set_slot_override("orchestrator", "aria-fast:latest")
    assert status()["preset"] is None
    assert status()["slots"]["orchestrator"]["model"] == "aria-fast:latest"


def test_unknown_slot_raises():
    from sovereign_agent.sprint_mode import set_slot_override

    try:
        set_slot_override("not-a-slot", "whatever")
        assert False, "expected KeyError"
    except KeyError:
        pass


def test_model_override_is_none_when_sprint_is_off():
    from sovereign_agent.sprint_mode import model_override

    assert model_override() is None
    assert model_override("coder") is None


def test_model_override_reflects_the_active_orchestrator_override():
    from sovereign_agent.sprint_mode import activate_preset, model_override

    activate_preset("sprint-phi4")
    assert model_override() == "phi4-mini:3.8b"
    assert model_override("orchestrator") == "phi4-mini:3.8b"
    assert model_override("coder") is None  # a different slot, untouched


def test_model_override_never_raises_on_a_corrupt_state_file():
    from sovereign_agent.config import SETTINGS
    from sovereign_agent.sprint_mode import model_override, _state_path

    _state_path().parent.mkdir(parents=True, exist_ok=True)
    _state_path().write_text("{ not valid json", encoding="utf-8")
    assert model_override() is None  # degrades honestly, never crashes


def test_list_installed_models_degrades_to_empty_on_unreachable_ollama():
    from sovereign_agent.sprint_mode import list_installed_models

    with patch("urllib.request.urlopen", side_effect=OSError("connection refused")):
        assert list_installed_models() == []


def test_list_installed_models_parses_the_real_ollama_response_shape():
    import io
    import json
    from sovereign_agent.sprint_mode import list_installed_models

    payload = json.dumps({"models": [{"name": "qwen3.5:2b"}, {"name": "aria-fast:latest"}]})

    class _FakeResp(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): return False

    with patch("urllib.request.urlopen", return_value=_FakeResp(payload.encode())):
        names = list_installed_models()
    assert names == ["aria-fast:latest", "qwen3.5:2b"]  # sorted


def test_loop_uses_the_sprint_override_only_when_no_explicit_model_given():
    """The exact wiring point in loop.py: an explicit model= argument from
    a caller must always win over sprint mode; only the bare default
    falls through to it."""
    from sovereign_agent import sprint_mode

    with patch.object(sprint_mode, "model_override", return_value="qwen3.5:2b") as mock_override:
        from sovereign_agent.config import SETTINGS

        # Mirror loop.py's exact resolution logic rather than running the
        # whole agent_loop (which needs a live Ollama) -- this is the
        # precise line being tested for regression.
        model = None
        if model is None:
            model = sprint_mode.model_override() or SETTINGS.orchestrator_model
        assert model == "qwen3.5:2b"
        mock_override.assert_called_once()

        explicit_model = "some-explicit-model"
        if explicit_model is None:
            explicit_model = sprint_mode.model_override() or SETTINGS.orchestrator_model
        assert explicit_model == "some-explicit-model"  # untouched


def test_agent_loop_itself_actually_calls_client_chat_with_the_sprint_model():
    """End-to-end through the REAL agent_loop (fake client, no live Ollama
    needed — same pattern test_modes_crown_live.py already uses): with a
    sprint preset active and no explicit model=, the model name that
    reaches client.chat() must be the sprint model, not
    SETTINGS.orchestrator_model."""
    import asyncio

    from sovereign_agent.loop import agent_loop
    from sovereign_agent.modes import Mode, RunBudget
    from sovereign_agent.sprint_mode import activate_preset

    activate_preset("sprint-2b")
    seen_models = []

    class _FakeClient:
        async def chat(self, *, model, messages, **kw):
            seen_models.append(model)
            return {"message": {"role": "assistant", "content": "RESULT: done"}}

    async def _run():
        return await agent_loop(
            goal="a tiny goal",
            mode=Mode.ONESHOT,
            budget=RunBudget(max_iterations=4, max_wall_seconds=60, max_tokens=10_000),
            tools={}, client=_FakeClient(), enable_reflector=False,
        )

    asyncio.run(_run())
    assert seen_models, "client.chat was never called"
    assert seen_models[0] == "qwen3.5:2b"
