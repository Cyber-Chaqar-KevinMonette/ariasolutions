"""Tests for movie_series_auto.py — the two narrow model-driven writing
calls Auto Series needs. agent_loop is always monkeypatched — these tests
never touch a real Ollama server or GPU."""
from __future__ import annotations

import pytest

from sovereign_agent import movie_series_auto as auto


class _FakeLoopResult:
    def __init__(self, final_message: str):
        self.final_message = final_message


def _patch_agent_loop(monkeypatch, reply: str, *, raise_instead: Exception | None = None):
    calls = []

    async def fake_agent_loop(*, goal, mode, budget, tools, enable_reflector=True, **kw):
        calls.append(goal)
        if raise_instead is not None:
            raise raise_instead
        assert tools == {}   # pure text completion, never a tool-calling turn
        return _FakeLoopResult(reply)

    # agent_loop is imported lazily inside _ask_orchestrator via
    # `from .loop import agent_loop` at call time, so patching the real
    # source module's attribute is what the lazy import actually picks up.
    import sovereign_agent.loop as loop_mod
    monkeypatch.setattr(loop_mod, "agent_loop", fake_agent_loop)
    return calls


WELL_FORMED_REPLY = (
    "TITLE: The Last Lighthouse\n"
    "LOGLINE: A lonely keeper discovers the light guides more than ships.\n"
    "GENRE: sci-fi\n"
    "STYLE: animated\n"
    "OPENING BEAT: A weathered lighthouse stands against a storm; the keeper "
    "climbs the spiral stairs, lantern in hand.\n"
)


@pytest.mark.asyncio
async def test_compose_series_concept_parses_a_well_formed_reply(monkeypatch):
    _patch_agent_loop(monkeypatch, WELL_FORMED_REPLY)
    concept = await auto.compose_series_concept("lighthouses")
    assert concept.title == "The Last Lighthouse"
    assert "lighthouse" in concept.logline.lower() or "keeper" in concept.logline.lower()
    assert concept.genre == "sci-fi"
    assert concept.style == "animated"
    assert "lighthouse" in concept.opening_beat.lower()


@pytest.mark.asyncio
async def test_compose_series_concept_uses_open_theme_default_when_blank(monkeypatch):
    calls = _patch_agent_loop(monkeypatch, WELL_FORMED_REPLY)
    await auto.compose_series_concept("")
    assert auto.DEFAULT_THEME in calls[0]


@pytest.mark.asyncio
async def test_compose_series_concept_never_raises_on_malformed_reply(monkeypatch):
    _patch_agent_loop(monkeypatch, "not the format I asked for at all")
    concept = await auto.compose_series_concept("robots")
    assert concept.title == "Untitled Auto Series"
    assert concept.genre == "short-film"
    assert concept.style == "animated"
    assert concept.opening_beat  # never empty


@pytest.mark.asyncio
async def test_compose_series_concept_never_raises_when_the_model_call_fails(monkeypatch):
    _patch_agent_loop(monkeypatch, "", raise_instead=RuntimeError("ollama unreachable"))
    concept = await auto.compose_series_concept("robots")
    assert concept.title == "Untitled Auto Series"
    assert "ollama unreachable" in concept.opening_beat


@pytest.mark.asyncio
async def test_compose_series_concept_logs_prompt_and_reply(monkeypatch, tmp_path):
    _patch_agent_loop(monkeypatch, WELL_FORMED_REPLY)
    await auto.compose_series_concept("lighthouses", workspace=tmp_path)
    log = (tmp_path / "auto_series_log.md").read_text(encoding="utf-8")
    assert "series concept" in log
    assert "The Last Lighthouse" in log


@pytest.mark.asyncio
async def test_compose_next_beat_includes_prior_beats_in_the_prompt(monkeypatch):
    calls = _patch_agent_loop(monkeypatch, "The keeper finds a second lantern, unlit.")
    beat = await auto.compose_next_beat(
        series_title="The Last Lighthouse", prior_beats=["The keeper climbs the stairs."],
        episode_number=1,
    )
    assert "second lantern" in beat
    assert "The keeper climbs the stairs." in calls[0]
    assert "The Last Lighthouse" in calls[0]


@pytest.mark.asyncio
async def test_compose_next_beat_never_raises_when_the_model_call_fails(monkeypatch):
    _patch_agent_loop(monkeypatch, "", raise_instead=RuntimeError("ollama unreachable"))
    beat = await auto.compose_next_beat(series_title="X", prior_beats=[], episode_number=2)
    assert "X" in beat
    assert beat  # never empty, never raises


# ── classify_command (Kevin, 2026-07-28: "we want full natural language
# autonomy") ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_classify_command_parses_action_and_argument(monkeypatch):
    _patch_agent_loop(monkeypatch, "ACTION: clip\nARGUMENT: a lonely lighthouse keeper\n")
    action, argument = await auto.classify_command("make something about a lighthouse keeper")
    assert action == "clip"
    assert argument == "a lonely lighthouse keeper"


@pytest.mark.asyncio
async def test_classify_command_normalizes_action_spelling(monkeypatch):
    _patch_agent_loop(monkeypatch, "ACTION: Start Episode\nARGUMENT: a storm rolls in\n")
    action, argument = await auto.classify_command("kick off a new episode about a storm")
    assert action == "start_episode"
    assert argument == "a storm rolls in"


@pytest.mark.asyncio
async def test_classify_command_rejects_an_action_not_in_the_known_list(monkeypatch):
    _patch_agent_loop(monkeypatch, "ACTION: delete_everything\nARGUMENT: oops\n")
    action, argument = await auto.classify_command("do something")
    assert action == "unknown"


@pytest.mark.asyncio
async def test_classify_command_never_raises_on_malformed_reply(monkeypatch):
    _patch_agent_loop(monkeypatch, "I don't know what you mean")
    action, argument = await auto.classify_command("do something")
    assert action == "unknown"


@pytest.mark.asyncio
async def test_classify_command_never_raises_when_the_model_call_fails(monkeypatch):
    _patch_agent_loop(monkeypatch, "", raise_instead=RuntimeError("ollama unreachable"))
    action, argument = await auto.classify_command("do the thing")
    assert action == "unknown"
    assert argument == "do the thing"   # degrades to echoing the original text


@pytest.mark.asyncio
async def test_compose_next_beat_logs_prompt_and_reply(monkeypatch, tmp_path):
    _patch_agent_loop(monkeypatch, "Something happens next.")
    await auto.compose_next_beat(
        series_title="X", prior_beats=[], episode_number=1, workspace=tmp_path,
    )
    log = (tmp_path / "auto_series_log.md").read_text(encoding="utf-8")
    assert "next beat (episode 1)" in log
    assert "Something happens next." in log
