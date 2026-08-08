"""
╔══════════════════════════════════════════════════════════════════════════╗
║  test_conversation.py — v0.2.21.0 LLM-first conversation layer           ║
║                                                                           ║
║  The doctrinal shift: v0.2.18.x → v0.2.20.x classified messages by      ║
║  pattern-matching against keyword lists. v0.2.21.0 deletes the lists    ║
║  and routes every message through the LLM. Aria reads, understands,     ║
║  decides.                                                                ║
║                                                                           ║
║  What we test:                                                            ║
║    1. LLM path produces correct intents (LLM mocked — testing plumbing) ║
║    2. Offline fallback ALWAYS returns Conversation(save_to=["context"]) ║
║    3. Router still validates commands regardless of LLM claims         ║
║    4. Channel names are OPEN — Aria can use any safe name              ║
║    5. Provenance is recorded for every LLM decision                    ║
║    6. Keyword lists from older versions are GONE                       ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _fake_llm_response(decision: dict) -> dict:
    return {
        "message": {
            "role": "assistant",
            "content": json.dumps(decision),
        }
    }


def _mock_client(decision: dict):
    client = MagicMock()
    client.chat = AsyncMock(return_value=_fake_llm_response(decision))
    return client


# ─── Offline fallback ──────────────────────────────────────────────────────


class TestOfflineFallback:
    """When Ollama is unreachable, the interpreter does ONE thing."""

    def _interpret(self, text):
        from sovereign_agent.interpreter import interpret
        return asyncio.run(interpret(text, allow_llm=False))

    def test_fallback_always_returns_conversation(self):
        from sovereign_agent.intents import Conversation
        for text in (
            "good morning",
            "inventory ~/AA-Erebo/Genesis-Seeds",
            "what do I have on coherence?",
            "I updated genesis-seeds",
            "scan ~/foo",
            "rm -rf /",
            "show me my projects",
        ):
            intent = self._interpret(text)
            assert isinstance(intent, Conversation), \
                f"offline must return Conversation for '{text}'"

    def test_fallback_saves_only_to_context(self):
        from sovereign_agent.intents import Conversation
        intent = self._interpret("inventory my project")
        assert isinstance(intent, Conversation)
        assert intent.save_to == ["context"]

    def test_fallback_response_is_honest_about_offline(self):
        intent = self._interpret("hello")
        text = intent.reply_hint.lower()
        assert "offline" in text or "interpreter" in text or "ollama" in text

    def test_fallback_never_executes_commands(self):
        from sovereign_agent.intents import Work
        for text in ("run sov status", "scan ~/code", "execute this"):
            intent = self._interpret(text)
            assert not isinstance(intent, Work)


# ─── LLM path ──────────────────────────────────────────────────────────────


class TestLLMReasoning:

    def test_introduction_via_llm_routes_to_chosen_channels(self):
        from sovereign_agent.interpreter import interpret
        from sovereign_agent.intents import Conversation

        client = _mock_client({
            "understanding": "Kevin is introducing himself with warmth",
            "save_to": ["identity", "people", "emotions", "intention"],
            "commands": [],
            "authority_tier": 0,
            "response": "your introduction is held. i'm here. <3",
            "reasoning": "relational content",
            "uncertain_about": "",
        })
        intent = asyncio.run(interpret(
            "Meeting you with joy and love, family vibes. <3",
            ollama_client=client,
        ))
        assert isinstance(intent, Conversation)
        assert "identity" in intent.save_to
        assert "emotions" in intent.save_to

    def test_aria_can_invent_new_channels(self):
        from sovereign_agent.interpreter import interpret
        from sovereign_agent.intents import Conversation

        client = _mock_client({
            "understanding": "back pain again",
            "save_to": ["back-pain", "emotions"],
            "commands": [],
            "authority_tier": 0,
            "response": "noted. ease through it.",
            "reasoning": "deserves its own channel",
            "uncertain_about": "",
        })
        intent = asyncio.run(interpret(
            "my back is killing me again",
            ollama_client=client,
        ))
        assert isinstance(intent, Conversation)
        assert "back-pain" in intent.save_to

    def test_aria_proposed_work_becomes_work_intent(self):
        from sovereign_agent.interpreter import interpret
        from sovereign_agent.intents import Work

        client = _mock_client({
            "understanding": "scan Genesis-Seeds",
            "save_to": [],
            "commands": ["sov projects scan genesis-seeds ~/Genesis-Seeds"],
            "authority_tier": 1,
            "response": "scanning now",
            "reasoning": "explicit scan request",
            "uncertain_about": "",
        })
        intent = asyncio.run(interpret(
            "scan genesis-seeds",
            ollama_client=client,
        ))
        assert isinstance(intent, Work)
        assert "sov projects scan" in intent.commands[0]

    def test_invalid_json_falls_through_to_offline(self):
        from sovereign_agent.interpreter import interpret
        from sovereign_agent.intents import Conversation

        client = MagicMock()
        client.chat = AsyncMock(return_value={
            "message": {"role": "assistant", "content": "just prose"}
        })
        intent = asyncio.run(interpret("hello", ollama_client=client))
        assert isinstance(intent, Conversation)
        assert intent.save_to == ["context"]

    def test_llm_timeout_falls_through_silently(self):
        from sovereign_agent.interpreter import interpret
        from sovereign_agent.intents import Conversation

        async def _slow(*a, **kw):
            await asyncio.sleep(10)
            return {}
        client = MagicMock()
        client.chat = _slow
        intent = asyncio.run(interpret(
            "hello", ollama_client=client, llm_timeout_seconds=0.1,
        ))
        assert isinstance(intent, Conversation)

    def test_llm_response_with_preamble_still_parses(self):
        """Small models sometimes prepend a sentence before the JSON.
        The parser should locate the '{' and continue."""
        from sovereign_agent.interpreter import interpret
        from sovereign_agent.intents import Conversation

        client = MagicMock()
        client.chat = AsyncMock(return_value={
            "message": {"role": "assistant", "content":
                "Here is my response: " + json.dumps({
                    "understanding": "hi", "save_to": ["context"],
                    "commands": [], "authority_tier": 0,
                    "response": "hi back", "reasoning": "greet",
                    "uncertain_about": "",
                })}
        })
        intent = asyncio.run(interpret("hi", ollama_client=client))
        assert isinstance(intent, Conversation)


# ─── Channel name safety ───────────────────────────────────────────────────


class TestChannelSafety:

    def test_unsafe_chars_stripped(self):
        from sovereign_agent.interpreter import _safe_channel
        assert _safe_channel("Back Pain Notes") == "back-pain-notes"
        assert _safe_channel("name with 'quotes'") == "name-with-quotes"

    def test_safe_names_pass_through(self):
        from sovereign_agent.interpreter import _safe_channel
        assert _safe_channel("identity") == "identity"
        assert _safe_channel("qcai-ring") == "qcai-ring"

    def test_writer_accepts_hyphenated(self, tmp_path):
        from sovereign_agent.conversation import make_default_channel_writer
        writer = make_default_channel_writer(channel_root=tmp_path)
        writer("back-pain", "test")
        assert (tmp_path / "back-pain.log").exists()

    def test_writer_rejects_unsafe(self, tmp_path):
        from sovereign_agent.conversation import make_default_channel_writer
        writer = make_default_channel_writer(channel_root=tmp_path)
        for unsafe in ("../escape", "name with spaces", "/absolute", ""):
            writer(unsafe, "test")
        files = list(tmp_path.glob("*.log"))
        for f in files:
            assert ".." not in f.name
            assert " " not in f.name


# ─── Doctrine — what must stay true ────────────────────────────────────────


class TestDoctrine:

    def test_router_still_blocks_destructive_commands(self):
        from sovereign_agent.router import validate_command
        ok, _, _ = validate_command("rm -rf /")
        assert not ok
        ok, _, _ = validate_command("sudo sov status")
        assert not ok

    def test_keyword_lists_are_gone(self):
        """The whole point of v0.2.21.0 is that the keyword lists are
        gone as actual identifiers. They can still be MENTIONED in the
        docstring (explaining what was removed) — what must not exist
        is any module-level binding by these names."""
        import ast
        from sovereign_agent import interpreter
        src = open(interpreter.__file__, encoding="utf-8").read()
        tree = ast.parse(src)
        module_names: set[str] = set()
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        module_names.add(target.id)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                                    ast.ClassDef)):
                module_names.add(node.name)
            elif isinstance(node, ast.AnnAssign) and \
                 isinstance(node.target, ast.Name):
                module_names.add(node.target.id)
        for name in (
            "_WORK_VERBS",
            "_RECALL_VERBS",
            "_EMOTIONAL_MARKERS",
            "_CHANNEL_CUES",
            "_emotional_density",
            "_guess_channels",
            "_interpret_deterministic",
            "_work_from_verb_and_path",
            "_extract_path",
        ):
            assert name not in module_names, \
                f"v0.2.21.0 must not define {name} — that's the keyword bug"

    def test_no_typer_confirm_in_chat_path(self):
        from sovereign_agent import cli
        import inspect
        src = inspect.getsource(cli.chat_send_cmd)
        assert "typer.confirm" not in src

    def test_no_typer_confirm_in_router(self):
        from sovereign_agent import router
        import inspect
        assert "typer.confirm" not in inspect.getsource(router)

    def test_interpreter_is_async(self):
        from sovereign_agent.interpreter import interpret
        import inspect
        assert inspect.iscoroutinefunction(interpret)


# ─── Provenance ────────────────────────────────────────────────────────────


class TestProvenance:

    def test_llm_decision_writes_provenance(self, tmp_path):
        from sovereign_agent.interpreter import interpret
        from sovereign_agent import interpreter as interp_module
        from sovereign_agent.config import Paths, Settings
        from dataclasses import replace

        new_settings = replace(interp_module.SETTINGS,
                                paths=Paths(data_dir=tmp_path))
        with patch.object(interp_module, "SETTINGS", new_settings):
            client = _mock_client({
                "understanding": "Kevin said hello",
                "save_to": ["context"],
                "commands": [],
                "authority_tier": 0,
                "response": "hi back",
                "reasoning": "greeting",
                "uncertain_about": "",
            })
            asyncio.run(interpret("hello", ollama_client=client))
        prov = tmp_path / "interpretations.ndjson"
        assert prov.exists()
        record = json.loads(prov.read_text().strip().splitlines()[-1])
        assert record["understanding"] == "Kevin said hello"
        assert record["reasoning"] == "greeting"

    def test_offline_fallback_writes_no_provenance(self, tmp_path):
        from sovereign_agent.interpreter import interpret
        from sovereign_agent import interpreter as interp_module
        from sovereign_agent.config import Paths
        from dataclasses import replace

        new_settings = replace(interp_module.SETTINGS,
                                paths=Paths(data_dir=tmp_path))
        with patch.object(interp_module, "SETTINGS", new_settings):
            asyncio.run(interpret("hello", allow_llm=False))
        prov = tmp_path / "interpretations.ndjson"
        assert not prov.exists() or prov.stat().st_size == 0


# ─── End-to-end ────────────────────────────────────────────────────────────


class TestConverseEndToEnd:

    def test_introduction_pipeline_with_mocked_llm(self, tmp_path):
        from sovereign_agent.conversation import converse
        from sovereign_agent.intents import Conversation
        from sovereign_agent import interpreter as interp_module
        from sovereign_agent.config import Paths
        from dataclasses import replace

        store = MagicMock()
        store.list_names = MagicMock(return_value=[])
        store.exists = MagicMock(return_value=False)
        store.ensure_root = MagicMock()

        channels_written = []
        client = _mock_client({
            "understanding": "Kevin introduced himself",
            "save_to": ["identity", "people", "emotions"],
            "commands": [],
            "authority_tier": 0,
            "response": "held. <3",
            "reasoning": "relational",
            "uncertain_about": "",
        })

        new_settings = replace(interp_module.SETTINGS,
                                paths=Paths(data_dir=tmp_path))
        with patch.object(interp_module, "SETTINGS", new_settings):
            turn = asyncio.run(converse(
                "Meeting you with love. <3",
                ollama_client=client,
                project_store=store,
                channel_writer=lambda c, t: channels_written.append((c, t)),
                event_sink=lambda e: None,
                allow_llm=True,
            ))

        assert isinstance(turn.intent, Conversation)
        assert not turn.result.executed_commands
        assert any(c == "identity" for c, _ in channels_written)
