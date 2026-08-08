"""
╔══════════════════════════════════════════════════════════════════════════╗
║  test_v_0_2_30_1.py — Cockpit naturalization patch                       ║
║                                                                           ║
║  v0.2.30.1 makes the cockpit a pure natural-language home: muscle-memory ║
║  CLI strings like `sov ask "..."` or `sov heartbeat pulse "..."` typed  ║
║  inside the cockpit now do the right thing transparently.               ║
║                                                                           ║
║  Two cases, one helper:                                                  ║
║                                                                           ║
║    • `sov ask`/`sov do` wrappers are stripped — the cockpit is the      ║
║      natural-language home, so wrappers are redundant in here. The      ║
║      user's actual message goes to Aria's interpreter as if they had    ║
║      just typed it directly.                                            ║
║                                                                           ║
║    • Any other `sov <subcommand>` runs as a real subprocess. Direct     ║
║      CLI invocations now work from inside the cockpit too — `sov        ║
║      doctor`, `sov heartbeat pulse "..."`, `sov channels list` — all    ║
║      execute as if from a bash prompt.                                  ║
║                                                                           ║
║  This file pins the parser invariants. The cockpit's input handler is   ║
║  tested via the parser (which is the surface that contains the real     ║
║  logic); driving Textual's full event loop in unit tests is brittle     ║
║  and adds little signal.                                                ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from sovereign_agent import __version__


# ───────────────────────────────────────────────────────────────────────────
# § 1. Version bump
# ───────────────────────────────────────────────────────────────────────────


class TestVersionBump:

    def test_version_is_at_least_0_2_30_1(self) -> None:
        """The release line is at least 0.2.30.1.

        v0.2.30.1 shipped the cockpit naturalization patch. Forward bumps
        within 0.2.x and beyond are explicitly allowed — this test pins
        the lineage, not the exact patch.
        """
        parts = __version__.split(".")
        assert len(parts) >= 3, f"malformed version: {__version__}"
        as_tuple = tuple(int(p) for p in parts[:3])
        assert as_tuple >= (0, 2, 30), (
            f"version regressed below 0.2.30: {__version__}"
        )

    def test_pyproject_matches(self) -> None:
        pyproject = Path(__file__).parent.parent / "pyproject.toml"
        with pyproject.open("rb") as f:
            data = tomllib.load(f)
        # The pyproject version must match __version__ — they're the same
        # release. We don't pin a specific number; only consistency.
        assert data["project"]["version"] == __version__


# ───────────────────────────────────────────────────────────────────────────
# § 2. normalize_sov_prefix — the parser
# ───────────────────────────────────────────────────────────────────────────


def _norm(text: str):
    """Test helper: import & call the normalizer."""
    from sovereign_agent.cockpit.app import normalize_sov_prefix
    return normalize_sov_prefix(text)


class TestNormalizerReturnsNoneForPlainEnglish:
    """The normalizer must never grab plain-English input that just
    happens to contain the word 'sov' or 'sovereign'.
    """

    def test_empty_string_returns_none(self) -> None:
        assert _norm("") is None

    def test_whitespace_only_returns_none(self) -> None:
        assert _norm("   \t  ") is None

    def test_plain_english_returns_none(self) -> None:
        assert _norm("hello aria") is None

    def test_plain_english_with_sov_substring_returns_none(self) -> None:
        """`sovereign` appears in normal English (e.g. 'sovereign nation').
        Only the first WORD matters.
        """
        assert _norm("sovereign citizens are a topic in political science") is None
        assert _norm("the sov agent is great") is None
        assert _norm("how is sovereign doing today?") is None

    def test_mid_sentence_sov_returns_none(self) -> None:
        assert _norm("can you check sov doctor for me?") is None


class TestNormalizerUnwrapsAskAndDo:
    """`sov ask "X"` and `sov do "X"` inside the cockpit are redundant.
    The normalizer strips the wrapper so the inner message reaches Aria
    as if the operator had just typed it."""

    def test_sov_ask_quoted(self) -> None:
        r = _norm('sov ask "hello"')
        assert r is not None
        assert r.kind == "natural"
        assert r.text == "hello"

    def test_sov_ask_unquoted(self) -> None:
        r = _norm("sov ask hello world")
        assert r is not None
        assert r.kind == "natural"
        assert r.text == "hello world"

    def test_sov_ask_with_punctuation(self) -> None:
        r = _norm('sov ask "what do I have on rollbacks?"')
        assert r is not None
        assert r.kind == "natural"
        assert r.text == "what do I have on rollbacks?"

    def test_sovereign_ask_is_equivalent(self) -> None:
        """Both `sov` and `sovereign` are real binaries — both unwrap."""
        r = _norm('sovereign ask "hello"')
        assert r is not None
        assert r.kind == "natural"
        assert r.text == "hello"

    def test_sov_do_unwraps_too(self) -> None:
        r = _norm('sov do "pause my dream"')
        assert r is not None
        assert r.kind == "natural"
        assert r.text == "pause my dream"

    def test_sov_ask_with_no_message_returns_none(self) -> None:
        """`sov ask` with no further args isn't a meaningful unwrap —
        the operator probably pressed Enter early. Let the LLM see it."""
        assert _norm("sov ask") is None

    def test_sov_ask_with_only_quotes_returns_none(self) -> None:
        """Empty quoted message → not a meaningful unwrap."""
        assert _norm('sov ask ""') is None

    def test_case_insensitive_binary(self) -> None:
        """Capitalization of the binary doesn't matter for the prefix check."""
        r = _norm('SOV ask "hello"')
        assert r is not None
        assert r.kind == "natural"
        assert r.text == "hello"

    def test_case_insensitive_subcommand(self) -> None:
        r = _norm('sov ASK "hello"')
        assert r is not None
        assert r.kind == "natural"
        assert r.text == "hello"

    def test_leading_trailing_whitespace_stripped(self) -> None:
        r = _norm('   sov ask "hello"   ')
        assert r is not None
        assert r.kind == "natural"
        assert r.text == "hello"

    def test_emoji_and_unicode_in_message_preserved(self) -> None:
        r = _norm('sov ask "café ☕ aria"')
        assert r is not None
        assert r.kind == "natural"
        # Note: shlex preserves the unicode content; the exact spacing
        # may collapse around the quotes
        assert "café" in r.text
        assert "☕" in r.text
        assert "aria" in r.text


class TestNormalizerExecutesOtherSubcommands:
    """Anything that isn't `ask`/`do` becomes a direct subprocess command.
    The argv always starts with the canonical `sovereign` binary name —
    that's what gets logged in the audit trail.
    """

    def test_sov_doctor_executes(self) -> None:
        r = _norm("sov doctor")
        assert r is not None
        assert r.kind == "execute"
        assert r.argv == ("sovereign", "doctor")

    def test_sov_heartbeat_pulse_quoted(self) -> None:
        r = _norm('sov heartbeat pulse "first pulse on v0.2.30.1"')
        assert r is not None
        assert r.kind == "execute"
        assert r.argv[0] == "sovereign"
        assert r.argv[1] == "heartbeat"
        assert r.argv[2] == "pulse"
        # The quoted string becomes one argv entry, quotes stripped
        assert r.argv[3] == "first pulse on v0.2.30.1"

    def test_sov_channels_list_executes(self) -> None:
        r = _norm("sov channels list")
        assert r is not None
        assert r.kind == "execute"
        assert r.argv == ("sovereign", "channels", "list")

    def test_sovereign_binary_normalized_to_sovereign(self) -> None:
        """Whether the operator typed `sov` or `sovereign`, the audit
        trail records the canonical name."""
        r_short = _norm("sov doctor")
        r_long = _norm("sovereign doctor")
        assert r_short.argv == r_long.argv == ("sovereign", "doctor")

    def test_bare_sov_returns_execute_for_help(self) -> None:
        """Just `sov` with nothing else — execute to get --help."""
        r = _norm("sov")
        assert r is not None
        assert r.kind == "execute"
        assert r.argv == ("sovereign",)

    def test_sov_with_double_dash_flags(self) -> None:
        r = _norm("sov --version")
        assert r is not None
        assert r.kind == "execute"
        assert r.argv == ("sovereign", "--version")

    def test_sov_with_subcommand_and_flag(self) -> None:
        r = _norm('sov heartbeat list --limit 10')
        assert r is not None
        assert r.kind == "execute"
        assert r.argv == ("sovereign", "heartbeat", "list", "--limit", "10")


class TestNormalizerSafetyOnMalformedInput:
    """The normalizer must NEVER raise. Even unparseable input degrades
    to None so the LLM interpreter — the safety net — sees the message.
    """

    def test_unclosed_quote_returns_none(self) -> None:
        """Unclosed quotes can't be parsed; we fall back to the LLM."""
        r = _norm('sov ask "hello')
        # Specifically: we must NOT raise. None is the safe answer.
        assert r is None

    def test_only_a_quote_returns_none(self) -> None:
        r = _norm('"')
        assert r is None

    def test_very_long_input_does_not_crash(self) -> None:
        """A 100KB input must not crash the normalizer."""
        text = 'sov ask "' + ("hello " * 10_000) + '"'
        r = _norm(text)
        # Must not raise. May parse cleanly or return None — either is fine.
        # If it parsed, the natural text must be huge.
        if r is not None:
            assert r.kind == "natural"
            assert len(r.text) > 50_000

    def test_null_bytes_do_not_crash(self) -> None:
        """Null bytes in input must not crash."""
        # Most shlex implementations handle nulls fine; we just verify
        # we don't raise an unhandled exception either way.
        r = _norm("sov\x00ask hello")
        # Whatever the parser decides, it must not have raised.
        # (We don't assert on the exact return value — it's environment-
        # dependent — only that we got here.)
        assert r is None or r.kind in ("natural", "execute")

    def test_only_whitespace_after_binary_returns_none(self) -> None:
        r = _norm("sov    ")
        # After strip: "sov" alone → execute (bare)
        assert r is not None
        assert r.kind == "execute"
        assert r.argv == ("sovereign",)


class TestNormalizerInteractionWithSlashCommands:
    """Slash commands take their own dispatch path; the normalizer should
    not touch them (they don't start with `sov`). This is a sanity test —
    slash routing happens BEFORE the normalizer in on_input_submitted,
    but defense in depth never hurts."""

    def test_slash_help_returns_none(self) -> None:
        assert _norm("/help") is None

    def test_slash_cancel_returns_none(self) -> None:
        assert _norm("/cancel") is None

    def test_slash_with_sov_in_arg_returns_none(self) -> None:
        """A slash command whose argument mentions `sov` is still a slash
        command — the normalizer never grabs it (the leading `/` shape
        doesn't match)."""
        assert _norm("/draft sov-trace ~/projects/foo") is None


# ───────────────────────────────────────────────────────────────────────────
# § 3. The cockpit help screen carries the new behavior
# ───────────────────────────────────────────────────────────────────────────


class TestHelpScreenMentionsNaturalLanguage:
    """If the help screen drifts from the actual behavior, operators
    will be confused. Pin the key explanatory phrases."""

    def test_help_text_says_no_sov_ask_needed(self) -> None:
        """Verify the help string explicitly tells the operator they
        don't need to type `sov ask` inside the cockpit."""
        from sovereign_agent.cockpit.app import HelpScreen
        # The compose method builds the Static — we look at the source
        # text by introspecting the module
        import inspect
        src = inspect.getsource(HelpScreen)
        # The key promise must be visible somewhere
        assert "natural-language home" in src or \
               "no need for `sov ask`" in src or \
               "never need to" in src.lower()

    def test_help_text_mentions_v0_2_30_1_behavior(self) -> None:
        """The version-marked block should reference the new naturalization."""
        from sovereign_agent.cockpit.app import HelpScreen
        import inspect
        src = inspect.getsource(HelpScreen)
        assert "v0.2.30.1" in src or "unwrap" in src.lower()


# ───────────────────────────────────────────────────────────────────────────
# § 4. End-to-end shape — the data flow we promise the operator
# ───────────────────────────────────────────────────────────────────────────


class TestEndToEndShapeWeOweTheOperator:
    """High-level invariants that downstream cockpit code depends on.

    These don't drive the Textual event loop; they verify that the
    NormalizedInput shape stays stable, so cockpit/_dispatch_turn and
    cockpit/_run_cli_async can rely on it.
    """

    def test_natural_kind_carries_text_not_argv(self) -> None:
        r = _norm('sov ask "hello"')
        assert r.kind == "natural"
        assert r.text == "hello"
        assert r.argv == ()  # not populated for natural

    def test_execute_kind_carries_argv_not_text(self) -> None:
        r = _norm("sov doctor")
        assert r.kind == "execute"
        assert r.argv == ("sovereign", "doctor")
        assert r.text == ""  # not populated for execute

    def test_normalized_input_is_frozen(self) -> None:
        """The dataclass is frozen — accidental mutation in a downstream
        handler should raise instead of silently corrupting state."""
        from sovereign_agent.cockpit.app import NormalizedInput
        r = NormalizedInput(kind="natural", text="hello")
        with pytest.raises(Exception):
            r.text = "tampered"  # type: ignore[misc]
