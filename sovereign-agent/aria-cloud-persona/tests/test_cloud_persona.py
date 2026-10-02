"""Tests for aria-cloud-persona — cloud models receive Aria's identity, voice and inner state;
the caller's messages are never mutated; conditioning is idempotent; a failure never breaks a call."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from sovereign_agent.cloud_persona import (
    MARKER, MAX_IDENTITY_CHARS, VOICE_FALLBACK, aria_sections, condition_messages, latest_inner_voice,
    role_for_model,
)

ARIA_MD = next(p / "ARIA.md" for p in Path(__file__).resolve().parents if (p / "ARIA.md").is_file())
PAYLOAD_CLIENT = Path(__file__).parents[1] / "payload" / "src" / "sovereign_agent" / "cloud_client.py"


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    from sovereign_agent import config, events

    paths = config.Paths(config_dir=tmp_path / "config", data_dir=tmp_path / "data")
    paths.ensure()
    original = config.SETTINGS.paths
    object.__setattr__(config.SETTINGS, "paths", paths)
    captured: list[tuple[str, dict]] = []
    monkeypatch.setattr(events, "emit_event", lambda flag, **kw: captured.append((flag, kw)) or "evt")
    try:
        yield SimpleNamespace(data_dir=tmp_path / "data", events=captured)
    finally:
        object.__setattr__(config.SETTINGS, "paths", original)


@pytest.mark.parametrize("model,role", [
    ("aria-coder:latest", "coder"), ("aria-orchestrator-fast", "orchestrator_fast"),
    ("library/aria-reflector:7b", "reflector"), ("llama3", "orchestrator"), (None, "orchestrator"),
])
def test_model_names_map_to_persona_roles(model, role):
    assert role_for_model(model) == role


def test_her_own_words_come_from_aria_md():
    text = aria_sections(ARIA_MD)
    assert "## Voice" in text and "Brief, warm, technically rigorous" in text
    assert "## Tagline" in text and "trellis" in text
    assert VOICE_FALLBACK in aria_sections(Path("/nonexistent/ARIA.md"))


def test_identity_is_added_without_touching_the_callers_messages():
    original = [{"role": "system", "content": "LOOP PROMPT"}, {"role": "user", "content": "hi"}]
    snapshot = json.dumps(original)
    out = condition_messages(original, model="aria-coder", aria_md=ARIA_MD)
    assert json.dumps(original) == snapshot                         # caller's list untouched
    sys_msg = out[0]["content"]
    assert sys_msg.startswith(MARKER) and "You are Aria" in sys_msg
    assert "Your role: coder" in sys_msg or "coder" in sys_msg
    assert sys_msg.rstrip().endswith("LOOP PROMPT")                 # her identity first, loop prompt kept
    assert len(sys_msg) <= MAX_IDENTITY_CHARS + len("\n\n---\n\nLOOP PROMPT")


def test_a_system_message_is_inserted_when_there_is_none():
    out = condition_messages([{"role": "user", "content": "hi"}], aria_md=ARIA_MD)
    assert out[0]["role"] == "system" and MARKER in out[0]["content"] and out[1]["content"] == "hi"


def test_conditioning_twice_changes_nothing():
    once = condition_messages([{"role": "user", "content": "hi"}], aria_md=ARIA_MD)
    assert condition_messages(once, aria_md=ARIA_MD) == once


def test_current_inner_state_travels_with_the_call(isolated, monkeypatch):
    from sovereign_agent import emotion

    pytest.importorskip("sovereign_agent.maturity")   # inner voice needs aria-emotional-maturity
    monkeypatch.setattr(emotion, "_count_atoms_by_type", lambda *a, **k: 0)
    from sovereign_agent.maturity import emotional_checkin

    c = emotional_checkin(events=[], rewards=[], data_dir=isolated.data_dir)
    assert latest_inner_voice(isolated.data_dir) == c.inner_voice
    out = condition_messages([{"role": "user", "content": "hi"}], aria_md=ARIA_MD, data_dir=isolated.data_dir)
    assert "## Current inner state" in out[0]["content"] and c.inner_voice in out[0]["content"]


def test_bad_input_is_rejected():
    with pytest.raises(ValueError):
        condition_messages("not a list")


# ── CloudClient end to end with a fake cloud provider ───────────────────────


def _staged_client_module():
    spec = importlib.util.spec_from_file_location("sovereign_agent._staged_cloud_client", PAYLOAD_CLIENT
        if PAYLOAD_CLIENT.is_file() else importlib.util.find_spec("sovereign_agent.cloud_client").origin)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _FakePool:
    def __init__(self):
        self.seen = None

    async def achat(self, messages, **kw):
        self.seen = messages
        return SimpleNamespace(message={"role": "assistant", "content": "Done. Tests pass."},
                               text="Done. Tests pass.", model="fake/free", prompt_tokens=1, completion_tokens=1)


async def test_cloud_provider_receives_arias_identity_and_caller_list_is_unchanged():
    client = _staged_client_module().CloudClient()
    client._pool = _FakePool()
    msgs = [{"role": "system", "content": "LOOP PROMPT"}, {"role": "user", "content": "status?"}]
    reply = await client.chat(model="aria-orchestrator", messages=msgs)
    assert reply["message"]["content"] == "Done. Tests pass."
    assert MARKER in client._pool.seen[0]["content"] and "You are Aria" in client._pool.seen[0]["content"]
    assert msgs[0]["content"] == "LOOP PROMPT"


async def test_a_persona_failure_never_breaks_the_call(isolated, monkeypatch):
    import sovereign_agent.cloud_persona as cp

    monkeypatch.setattr(cp, "condition_messages", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    client = _staged_client_module().CloudClient()
    client._pool = _FakePool()
    msgs = [{"role": "user", "content": "status?"}]
    reply = await client.chat(model="aria-orchestrator", messages=msgs)
    assert reply["message"]["content"] == "Done. Tests pass." and client._pool.seen == msgs
    assert any(flag == "cloud-persona-x" for flag, _ in isolated.events)
