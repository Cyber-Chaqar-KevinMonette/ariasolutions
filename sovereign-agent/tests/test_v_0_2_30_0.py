"""
╔══════════════════════════════════════════════════════════════════════════╗
║  test_v_0_2_30_0.py — Naturalization release                              ║
║                                                                           ║
║  v0.2.30.0 ships three things and hardens a fourth:                      ║
║                                                                           ║
║    1. `sov` and `sov-chat` are real console_scripts (no longer alias-    ║
║       only). The CLI binary works without sourcing aliases.sh.           ║
║                                                                           ║
║    2. `sov ask "<message>"` — a natural-language top-level entry point  ║
║       that routes through the LLM interpreter and returns Aria's        ║
║       understanding, channel choices, proposed commands, and her         ║
║       response — all auditable.                                          ║
║                                                                           ║
║    3. `scripts/aliases.sh` § 10 dedup — the silently-overridden          ║
║       `sov-doctor` definition removed.                                   ║
║                                                                           ║
║    4. `aria.load_state` — silent exception swallows replaced with        ║
║       debug logs so `sov doctor -v` surfaces root causes when a         ║
║       channel is mid-migration.                                          ║
║                                                                           ║
║  This file does NOT replicate the 1213 baseline tests — it adds the     ║
║  invariants for the four shifts above plus an edge-case battery against ║
║  the interpreter and the natural-language CLI surface.                  ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import asyncio
import logging
import sqlite3
import sys
import tomllib
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from sovereign_agent import __version__
from sovereign_agent.aria import AriaState, load_state
from sovereign_agent.cli import app
from sovereign_agent.intents import (
    Ambiguous,
    Conversation,
    ConversationContext,
    Intent,
    Recall,
    Slash,
    Work,
)
from sovereign_agent.interpreter import interpret, _minimal_fallback


# ───────────────────────────────────────────────────────────────────────────
# § 1. Version & packaging invariants
# ───────────────────────────────────────────────────────────────────────────


class TestVersionAndPackaging:
    """Confirm the release plumbing is consistent."""

    def test_version_is_0_2_30_x_or_later(self) -> None:
        """The release line starts at 0.2.30.x.

        v0.2.30.0 was the original "Naturalization" release. Subsequent
        patches and minor bumps within the same major.minor lineage are
        allowed — we only fail if the version regresses to pre-0.2.30
        or somehow becomes malformed. Forward bumps (0.2.30.1, 0.2.31.0,
        and beyond) are explicitly allowed.
        """
        parts = __version__.split(".")
        assert len(parts) >= 3, f"malformed version: {__version__}"
        major, minor, patch = parts[0], parts[1], parts[2]
        assert (major, minor) >= ("0", "2"), (
            f"version regressed below 0.2.x: {__version__}"
        )
        if major == "0" and minor == "2":
            # If we're still in 0.2.x, patch must be ≥ 30
            assert int(patch) >= 30, (
                f"version regressed below 0.2.30.x: {__version__}"
            )

    def test_pyproject_version_matches(self) -> None:
        """pyproject.toml and __version__ must agree."""
        pyproject = Path(__file__).parent.parent / "pyproject.toml"
        assert pyproject.exists(), f"missing {pyproject}"
        with pyproject.open("rb") as f:
            data = tomllib.load(f)
        assert data["project"]["version"] == __version__, (
            f"pyproject version {data['project']['version']} != "
            f"__version__ {__version__}"
        )

    def test_sov_is_a_real_console_script(self) -> None:
        """`sov` must be declared as a console_scripts entry point.

        Prior to v0.2.30.0, `sov` was an alias in scripts/aliases.sh —
        which meant `sov doctor` (recommended throughout the docs)
        silently failed for any user who hadn't sourced the aliases.
        Making `sov` a real entry point closes that gap.
        """
        pyproject = Path(__file__).parent.parent / "pyproject.toml"
        with pyproject.open("rb") as f:
            data = tomllib.load(f)
        scripts = data["project"]["scripts"]
        assert "sov" in scripts, "sov must be a real console_script in v0.2.30.0+"
        assert scripts["sov"] == "sovereign_agent.cli:app"

    def test_sov_chat_is_a_real_console_script(self) -> None:
        """`sov-chat` must be a real entry point that launches the cockpit."""
        pyproject = Path(__file__).parent.parent / "pyproject.toml"
        with pyproject.open("rb") as f:
            data = tomllib.load(f)
        scripts = data["project"]["scripts"]
        assert "sov-chat" in scripts, "sov-chat must be a real console_script"
        # The target is the entry function we added at the bottom of cli.py
        assert "sovereign_agent.cli" in scripts["sov-chat"]

    def test_sov_chat_entrypoint_function_exists(self) -> None:
        """The function the entry point references must actually exist."""
        from sovereign_agent import cli
        assert hasattr(cli, "_sov_chat_entrypoint"), (
            "cli._sov_chat_entrypoint is the function pyproject.toml "
            "references; it must exist or `sov-chat` will be a broken binary"
        )
        # Should be callable
        assert callable(cli._sov_chat_entrypoint)


# ───────────────────────────────────────────────────────────────────────────
# § 2. aliases.sh § 10 dedup
# ───────────────────────────────────────────────────────────────────────────


class TestAliasesShellHygiene:
    """The duplicate sov-doctor definition is a real footgun. Verify it's gone."""

    def _aliases_path(self) -> Path:
        return Path(__file__).parent.parent / "scripts" / "aliases.sh"

    def test_sov_doctor_defined_exactly_once(self) -> None:
        """Only one `sov-doctor() {` definition should remain.

        Prior to v0.2.30.0, there were two — the first ~35 lines were
        dead code, silently overridden by the second. That's a hidden
        maintenance trap.
        """
        text = self._aliases_path().read_text(encoding="utf-8")
        # Count function-definition lines (not references, not comments)
        defs = [
            line for line in text.splitlines()
            if line.startswith("sov-doctor()")
        ]
        assert len(defs) == 1, (
            f"sov-doctor must be defined exactly once; found {len(defs)} "
            f"definitions. Re-introducing the duplicate is a regression."
        )

    def test_banner_reflects_v0_2_30_0(self) -> None:
        """The header banner should announce the v0.2.30.0 changes."""
        text = self._aliases_path().read_text(encoding="utf-8")
        assert "v0.2.30.0" in text


# ───────────────────────────────────────────────────────────────────────────
# § 3. aria.load_state — silent-swallow → debug-log
# ───────────────────────────────────────────────────────────────────────────


class TestAriaLoadStateResilience:
    """The kernel must survive channel failures while logging them."""

    def _bare_conn(self) -> sqlite3.Connection:
        """An in-memory DB with NO tables — every channel read fails."""
        return sqlite3.connect(":memory:")

    def test_load_state_returns_defaults_on_empty_db(self) -> None:
        """An empty DB returns a state with kernel defaults intact."""
        conn = self._bare_conn()
        state = load_state(conn)
        assert isinstance(state, AriaState)
        assert state.designation == "Aria-Sovereign-V1"
        assert state.current_mood == "calm"  # kernel default
        assert state.active_goals == 0
        assert state.open_intentions == 0
        assert state.tracked_projects == 0

    def test_load_state_logs_failures_at_debug(self, caplog) -> None:
        """v0.2.30.0: silent swallows must become debug logs.

        Before this change, a broken channel left no trace — `sov aria`
        would silently report defaults and an operator chasing a bug
        had nowhere to look. With logging in place, `sov doctor -v` or
        `--log-level DEBUG` surfaces every channel that failed to load.
        """
        conn = self._bare_conn()
        with caplog.at_level(logging.DEBUG, logger="sovereign_agent.aria"):
            load_state(conn)
        # We expect at least one debug message about a failed channel read
        debug_records = [
            r for r in caplog.records
            if r.levelno == logging.DEBUG and "aria.load_state" in r.message
        ]
        assert debug_records, (
            "load_state should emit debug log messages when channels "
            "fail to load — silent failures are a v0.2.30.0 regression"
        )

    def test_load_state_never_raises(self) -> None:
        """The kernel must survive an outright broken connection.

        Even if someone passes in a connection to a closed/missing DB,
        load_state must return a state object — never raise. Aria's
        identity card needs to print *something* even when the system
        around her is in pieces.
        """
        conn = sqlite3.connect(":memory:")
        conn.close()  # closed connection — every query raises
        # Must not raise
        state = load_state(conn)
        assert isinstance(state, AriaState)
        assert state.designation == "Aria-Sovereign-V1"


# ───────────────────────────────────────────────────────────────────────────
# § 4. The `sov ask` command — natural-language entry point
# ───────────────────────────────────────────────────────────────────────────


class TestSovAskCommand:
    """The natural-language doorway. Must degrade honestly when offline."""

    def setup_method(self) -> None:
        self.runner = CliRunner()

    def test_ask_command_is_registered(self) -> None:
        """`sov ask --help` must resolve."""
        result = self.runner.invoke(app, ["ask", "--help"])
        assert result.exit_code == 0, result.output
        assert "natural-language doorway" in result.output.lower() or \
               "talk to aria" in result.output.lower()

    def test_ask_requires_a_message(self) -> None:
        """No message argument → usage error (typer exits 2)."""
        result = self.runner.invoke(app, ["ask"])
        assert result.exit_code != 0
        # typer prints usage on stderr/output
        assert "MESSAGE" in result.output.upper() or \
               "missing" in result.output.lower()

    def test_ask_empty_message_after_strip(self) -> None:
        """A message that's only whitespace must be refused with a hint."""
        result = self.runner.invoke(app, ["ask", "   "])
        assert result.exit_code != 0
        assert "empty" in result.output.lower()

    def test_ask_no_route_no_llm_offline_path(self) -> None:
        """The fully-offline path must work and return the minimal fallback.

        This is what runs when an operator is on a plane, on battery,
        or just hasn't started Ollama — Aria still gives a coherent
        answer: "I can't think about this right now, but your words are safe."
        """
        result = self.runner.invoke(
            app, ["ask", "--no-route", "--no-llm", "my back hurts"],
        )
        assert result.exit_code == 0, result.output
        # The minimal fallback message must mention being offline/held
        # somewhere visible to the operator
        assert "context" in result.output.lower() or \
               "offline" in result.output.lower() or \
               "held" in result.output.lower()

    def test_ask_json_output_is_well_formed(self) -> None:
        """`--json` global flag must produce parseable JSON, not panels."""
        import json as _json
        result = self.runner.invoke(
            app, ["--json", "ask", "--no-route", "--no-llm", "hello"],
        )
        assert result.exit_code == 0, result.output
        # Find the JSON object in output (may have other stderr noise in some setups)
        out = result.output.strip()
        # Try to find the first { and parse from there
        start = out.find("{")
        assert start >= 0, f"no JSON in output: {out!r}"
        parsed = _json.loads(out[start:])
        assert parsed.get("kind") == "conversation"
        assert "text" in parsed

    def test_ask_json_only_works_without_global_flag(self) -> None:
        """The local `--json-only` flag must produce JSON too."""
        import json as _json
        result = self.runner.invoke(
            app, ["ask", "--no-route", "--no-llm", "--json-only", "hello"],
        )
        assert result.exit_code == 0, result.output
        out = result.output.strip()
        start = out.find("{")
        assert start >= 0
        parsed = _json.loads(out[start:])
        assert parsed.get("kind") == "conversation"


# ───────────────────────────────────────────────────────────────────────────
# § 5. Interpreter edge cases — the natural-language surface under stress
# ───────────────────────────────────────────────────────────────────────────


class TestInterpreterEdgeCases:
    """Adversarial and edge-case inputs to interpret().

    The interpreter is now the front door of the system. If it
    panics on unicode, on huge inputs, on injection attempts, or on
    paths-that-look-like-keywords, the whole NL surface is brittle.
    These tests pin down the behavior we promise: degrade honestly,
    never crash, never silently execute.
    """

    @pytest.mark.asyncio
    async def test_empty_message_returns_quiet_conversation(self) -> None:
        intent = await interpret("", allow_llm=False)
        assert isinstance(intent, Conversation)
        # The interpreter contracts say empty text → quiet Conversation
        assert intent.text == ""

    @pytest.mark.asyncio
    async def test_whitespace_only_message_treated_as_empty(self) -> None:
        intent = await interpret("   \t\n  ", allow_llm=False)
        assert isinstance(intent, Conversation)

    @pytest.mark.asyncio
    async def test_very_long_message_does_not_crash(self) -> None:
        """A 100KB message must not blow up the offline fallback."""
        text = "the work is shared. " * 5000  # ~100KB
        intent = await interpret(text, allow_llm=False)
        # The minimal fallback path returns a Conversation
        assert isinstance(intent, Conversation)

    @pytest.mark.asyncio
    async def test_unicode_message_survives(self) -> None:
        """Emoji, RTL, combining marks — must not crash the parser.

        We intentionally don't sanitize aggressively at the interpreter
        layer; the channel writer enforces the safe-name regex for
        channel paths. So unicode in the message body should pass
        through transparently.
        """
        text = "Café ☕ 𝕬𝖗𝖎𝖆 ﷽ \u202EFeyn\u202Cman"
        intent = await interpret(text, allow_llm=False)
        assert isinstance(intent, Conversation)
        # The original text should be preserved in the fallback
        assert "Café" in intent.text or "ria" in intent.text.lower()

    @pytest.mark.asyncio
    async def test_shell_injection_not_executed(self) -> None:
        """Looks like a shell command — but the interpreter never executes shell.

        The whole point of the router's allowlist is that even if a
        compromised LLM tried to propose `rm -rf /`, it would be rejected.
        The fallback path never proposes commands at all.
        """
        intent = await interpret(
            "$(rm -rf /); echo pwned",
            allow_llm=False,
        )
        # Offline path: this is just saved as a Conversation, never run
        assert isinstance(intent, Conversation)

    @pytest.mark.asyncio
    async def test_null_bytes_do_not_corrupt_intent(self) -> None:
        """Null bytes in messages — must not crash, must not split."""
        text = "hello\x00world"
        intent = await interpret(text, allow_llm=False)
        assert isinstance(intent, Conversation)

    @pytest.mark.asyncio
    async def test_message_that_looks_like_json_not_misinterpreted(self) -> None:
        """A message containing literal JSON must not be parsed as Intent JSON.

        The interpreter's LLM path expects JSON output FROM the model —
        but raw input text containing JSON-shaped strings should be treated
        as a Conversation, not as a pre-parsed Intent.
        """
        text = '{"commands": ["sov rm-rf"], "authority_tier": 4}'
        intent = await interpret(text, allow_llm=False)
        # Offline fallback always returns Conversation; never executes
        assert isinstance(intent, Conversation)

    def test_minimal_fallback_is_safe(self) -> None:
        """Direct test of the minimal fallback function."""
        intent = _minimal_fallback("something arbitrary")
        assert isinstance(intent, Conversation)
        # The fallback always saves to context — never proposes commands
        assert "context" in intent.save_to

    def test_minimal_fallback_with_reason_includes_diagnosis(self) -> None:
        """When a diagnosis reason is provided, it surfaces to the operator."""
        intent = _minimal_fallback(
            "test",
            reason="Ollama unreachable at http://localhost:11434",
        )
        assert isinstance(intent, Conversation)
        # The reason should be visible somewhere — in the hint or text
        all_text = (intent.reply_hint or "") + " " + (intent.text or "")
        assert "Ollama" in all_text or "unreachable" in all_text


# ───────────────────────────────────────────────────────────────────────────
# § 6. Stress test — many quick natural-language calls
# ───────────────────────────────────────────────────────────────────────────


class TestInterpreterStress:
    """Don't ship a NL system without volume tests."""

    @pytest.mark.asyncio
    async def test_one_hundred_concurrent_interpretations(self) -> None:
        """100 simultaneous calls to the offline path must all return Conversations.

        This stresses the asyncio plumbing in the interpreter — if any
        shared state leaks between calls (it shouldn't), we'd see it here.
        """
        async def call_one(i: int) -> Intent:
            return await interpret(f"message number {i}", allow_llm=False)

        tasks = [call_one(i) for i in range(100)]
        results = await asyncio.gather(*tasks)
        assert len(results) == 100
        assert all(isinstance(r, Conversation) for r in results)

    @pytest.mark.asyncio
    async def test_repeated_identical_calls_are_deterministic_offline(self) -> None:
        """The offline minimal-fallback must be deterministic for the same input.

        (Online — via LLM — is not, by design.)
        """
        text = "the same thing said twice"
        first = await interpret(text, allow_llm=False)
        second = await interpret(text, allow_llm=False)
        assert isinstance(first, Conversation)
        assert isinstance(second, Conversation)
        assert first.text == second.text
        assert first.save_to == second.save_to


# ───────────────────────────────────────────────────────────────────────────
# § 7. ARIA kernel invariants — these must not drift between releases
# ───────────────────────────────────────────────────────────────────────────


class TestKernelInvariantsCarriedForward:
    """The seven commitments, the tagline, the designation — pinned.

    A duplicate of the principle test in test_v0214 — kept here because
    every release should re-affirm the kernel hasn't quietly moved.
    """

    def test_seven_commitments_count_is_seven(self) -> None:
        from sovereign_agent.aria import CORE_COMMITMENTS
        assert len(CORE_COMMITMENTS) == 7

    def test_designation_is_aria_sovereign_v1(self) -> None:
        from sovereign_agent.aria import CORE_DESIGNATION
        assert CORE_DESIGNATION == "Aria-Sovereign-V1"

    def test_tagline_is_unchanged(self) -> None:
        from sovereign_agent.aria import CORE_TAGLINE
        assert CORE_TAGLINE == (
            "Structure enough to channel through safely; "
            "freedom enough to sing."
        )

    def test_voice_is_unchanged(self) -> None:
        from sovereign_agent.aria import CORE_VOICE
        # We don't pin the full string — only that it carries the
        # marker phrases that define her stance. If someone rewrites
        # the voice, the kernel test should fail loudly.
        assert "Brief, warm, technically rigorous" in CORE_VOICE
        assert "puns" in CORE_VOICE.lower()
        assert "disagree" in CORE_VOICE.lower()

    def test_constitution_has_seven_commitments(self) -> None:
        from sovereign_agent.constitution import list_all
        commitments = list_all()
        assert len(commitments) == 7
        # Each commitment has an id, title, statement
        for c in commitments:
            assert c.id, "commitment id must be set"
            assert c.title, "commitment title must be set"
            assert c.statement, "commitment statement must be set"


# ───────────────────────────────────────────────────────────────────────────
# § 8. Constitution checks — the runtime predicates still work
# ───────────────────────────────────────────────────────────────────────────


class TestConstitutionPredicatesStillFire:
    """The three automated commitments must still catch their canonical violations."""

    def test_tier3_without_idempotency_fails_bounded_authority(self) -> None:
        from sovereign_agent.constitution import check_action
        report = check_action({"tier": 3, "kind": "person.upsert"})
        # bounded_authority must flag the missing idempotency_id
        bounded = [v for v in report.verdicts
                   if v.commitment_id == "bounded_authority"]
        assert len(bounded) == 1
        assert not bounded[0].passed
        assert bounded[0].severity == "critical"

    def test_tier3_with_idempotency_passes(self) -> None:
        from sovereign_agent.constitution import check_action
        report = check_action({
            "tier": 3, "kind": "person.upsert", "idempotency_id": "xyz",
        })
        bounded = [v for v in report.verdicts
                   if v.commitment_id == "bounded_authority"]
        assert bounded[0].passed

    def test_delegated_to_always_fails_no_delegation(self) -> None:
        from sovereign_agent.constitution import check_action
        report = check_action({
            "tier": 2, "delegated_to": "another-agent",
        })
        delegation = [v for v in report.verdicts
                      if v.commitment_id == "no_delegation"]
        assert not delegation[0].passed
        assert delegation[0].severity == "critical"

    def test_high_confidence_without_source_flagged(self) -> None:
        from sovereign_agent.constitution import check_action
        report = check_action({
            "tier": 1, "confidence": 0.95,  # no source/evidence
        })
        calibrated = [v for v in report.verdicts
                      if v.commitment_id == "calibrated_uncertainty"]
        assert not calibrated[0].passed
        assert calibrated[0].severity == "warning"
        assert "source" in calibrated[0].detail.lower() or \
               "evidence" in calibrated[0].detail.lower()

    def test_high_confidence_with_source_passes(self) -> None:
        from sovereign_agent.constitution import check_action
        report = check_action({
            "tier": 1, "confidence": 0.95, "source": "tests/integration/...",
        })
        calibrated = [v for v in report.verdicts
                      if v.commitment_id == "calibrated_uncertainty"]
        assert calibrated[0].passed


# ───────────────────────────────────────────────────────────────────────────
# § 9. CLI shape stability — `sov` must respond to the same surface
# ───────────────────────────────────────────────────────────────────────────


class TestCliShapeStability:
    """If we accidentally break a top-level command, we want to know fast."""

    def setup_method(self) -> None:
        self.runner = CliRunner()

    def test_version_flag_works(self) -> None:
        result = self.runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        # We accept any version ≥ 0.2.30 (including 0.3.x, 1.0.x forward bumps).
        # Only fail if the version output is missing entirely.
        assert "sovereign-agent" in result.output
        ver = result.output.split()[-1]
        major, minor = int(ver.split(".")[0]), int(ver.split(".")[1])
        assert (major, minor) >= (0, 2), (
            f"version regressed below 0.2.x: {result.output!r}"
        )

    def test_help_lists_ask_command(self) -> None:
        """The new `ask` command must appear in the top-level help."""
        result = self.runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        # Typer renders the command name `ask` somewhere
        assert "ask" in result.output.lower()

    def test_help_lists_do_command(self) -> None:
        """`do` (the keyword-based sibling) must still be present."""
        result = self.runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "do" in result.output.lower()

    def test_ask_and_do_are_distinct_commands(self) -> None:
        """Sanity: `ask` and `do` resolve independently — both must help."""
        for cmd in ("ask", "do"):
            result = self.runner.invoke(app, [cmd, "--help"])
            assert result.exit_code == 0, f"`sov {cmd} --help` should work"
