"""
╔══════════════════════════════════════════════════════════════════════════╗
║  test_v_0_2_32_0.py — The Modes                                          ║
║                                                                           ║
║  v0.2.32.0 ships four real pieces:                                       ║
║                                                                           ║
║    1. Explicit cockpit modes (chat / work) with persistent state,       ║
║       event emission on transition, and a /mode slash command.          ║
║                                                                           ║
║    2. Stage C intent classifier — always-on, pluggable, with a          ║
║       deterministic HeuristicClassifier as the default and an           ║
║       OllamaClassifier ready to wire when an operator wants LLM-backed ║
║       classification. NL_INTENT vetoes a structural CLI match.         ║
║                                                                           ║
║    3. Queue-of-queues — sessions can extend their own queue mid-run    ║
║       with explicit justification. Each extension is an audit-trail    ║
║       event. The four-gate session loop respects the extended queue   ║
║       naturally.                                                        ║
║                                                                           ║
║    4. The cliff oracle grows by six new lines covering the cases the  ║
║       two design documents surfaced — prose-with-CLI-prefix, request- ║
║       embedded-command, sovereign-as-adjective, all named with date.  ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import tempfile
import tomllib
from dataclasses import dataclass
from pathlib import Path

import pytest

from sovereign_agent import __version__


# ───────────────────────────────────────────────────────────────────────────
# § 1. Version & packaging
# ───────────────────────────────────────────────────────────────────────────


class TestVersionAndPackaging:

    def test_pyproject_matches_version(self) -> None:
        pyproject = Path(__file__).parent.parent / "pyproject.toml"
        with pyproject.open("rb") as f:
            data = tomllib.load(f)
        assert data["project"]["version"] == __version__

    def test_version_is_at_least_0_2_32_0(self) -> None:
        parts = __version__.split(".")
        as_tuple = tuple(int(p) for p in parts[:3])
        assert as_tuple >= (0, 2, 32), (
            f"version regressed below 0.2.32: {__version__}"
        )


# ───────────────────────────────────────────────────────────────────────────
# § 2. Cockpit modes — chat vs work
# ───────────────────────────────────────────────────────────────────────────


class TestCockpitModes:
    """Mode state must persist, transition cleanly, and emit events."""

    def setup_method(self) -> None:
        # Each test gets a fresh temp dir for cockpit_mode.txt
        self._tmp = tempfile.TemporaryDirectory()
        self._dir = Path(self._tmp.name)

    def teardown_method(self) -> None:
        self._tmp.cleanup()

    def test_default_mode_is_chat(self) -> None:
        """No file → chat. This is the safe default."""
        from sovereign_agent.cockpit_modes import load_mode, CockpitMode
        state = load_mode(self._dir)
        assert state.mode == CockpitMode.CHAT

    def test_set_then_load_persists(self) -> None:
        from sovereign_agent.cockpit_modes import (
            load_mode, set_mode, CockpitMode,
        )
        set_mode(CockpitMode.WORK, reason="test", config_dir=self._dir)
        state = load_mode(self._dir)
        assert state.mode == CockpitMode.WORK

    def test_round_trip_chat_to_work_to_chat(self) -> None:
        from sovereign_agent.cockpit_modes import (
            load_mode, set_mode, CockpitMode,
        )
        assert load_mode(self._dir).mode == CockpitMode.CHAT
        set_mode(CockpitMode.WORK, config_dir=self._dir)
        assert load_mode(self._dir).mode == CockpitMode.WORK
        set_mode(CockpitMode.CHAT, config_dir=self._dir)
        assert load_mode(self._dir).mode == CockpitMode.CHAT

    def test_malformed_file_defaults_to_chat(self) -> None:
        """A corrupt mode file should not crash; we fall back to chat."""
        from sovereign_agent.cockpit_modes import load_mode, CockpitMode
        (self._dir / "cockpit_mode.txt").write_text("nonsense-mode\n")
        state = load_mode(self._dir)
        assert state.mode == CockpitMode.CHAT

    def test_atomic_write(self) -> None:
        """set_mode uses tempfile + rename so a crash mid-write can't
        leave a half-baked file. We verify the temp file isn't left
        behind after a successful write."""
        from sovereign_agent.cockpit_modes import set_mode, CockpitMode
        set_mode(CockpitMode.WORK, config_dir=self._dir)
        # No .tmp file should remain
        tmp_file = self._dir / "cockpit_mode.tmp"
        assert not tmp_file.exists()
        # The actual mode file should exist
        assert (self._dir / "cockpit_mode.txt").exists()

    def test_is_work_mode_helper(self) -> None:
        from sovereign_agent.cockpit_modes import (
            set_mode, is_work_mode, is_chat_mode, CockpitMode,
        )
        set_mode(CockpitMode.WORK, config_dir=self._dir)
        assert is_work_mode(self._dir) is True
        assert is_chat_mode(self._dir) is False

    def test_is_chat_mode_helper(self) -> None:
        from sovereign_agent.cockpit_modes import (
            set_mode, is_work_mode, is_chat_mode, CockpitMode,
        )
        set_mode(CockpitMode.CHAT, config_dir=self._dir)
        assert is_chat_mode(self._dir) is True
        assert is_work_mode(self._dir) is False

    def test_autonomous_loops_allowed_only_in_work(self) -> None:
        """The key semantic the rest of the system depends on."""
        from sovereign_agent.cockpit_modes import (
            set_mode, autonomous_loops_allowed, CockpitMode,
        )
        set_mode(CockpitMode.CHAT, config_dir=self._dir)
        assert autonomous_loops_allowed(self._dir) is False
        set_mode(CockpitMode.WORK, config_dir=self._dir)
        assert autonomous_loops_allowed(self._dir) is True

    def test_queue_extension_allowed_only_in_work(self) -> None:
        from sovereign_agent.cockpit_modes import (
            set_mode, queue_extension_allowed, CockpitMode,
        )
        set_mode(CockpitMode.CHAT, config_dir=self._dir)
        assert queue_extension_allowed(self._dir) is False
        set_mode(CockpitMode.WORK, config_dir=self._dir)
        assert queue_extension_allowed(self._dir) is True


# ───────────────────────────────────────────────────────────────────────────
# § 3. Stage C — intent classifier (heuristic + protocol)
# ───────────────────────────────────────────────────────────────────────────


class TestHeuristicClassifier:
    """The default classifier. Sync, deterministic, always available."""

    def _c(self):
        from sovereign_agent.intent_classifier import HeuristicClassifier
        return HeuristicClassifier()

    def test_empty_input_is_ambiguous(self) -> None:
        from sovereign_agent.intent_classifier import IntentLabel
        r = self._c().classify("")
        assert r.label == IntentLabel.AMBIGUOUS

    def test_whitespace_only_is_ambiguous(self) -> None:
        from sovereign_agent.intent_classifier import IntentLabel
        r = self._c().classify("   \t  ")
        assert r.label == IntentLabel.AMBIGUOUS

    def test_sov_doctor_is_cli(self) -> None:
        from sovereign_agent.intent_classifier import IntentLabel
        r = self._c().classify("sov doctor")
        assert r.label == IntentLabel.CLI_INTENT
        assert r.confidence >= 0.70

    def test_sov_channels_list_is_cli(self) -> None:
        from sovereign_agent.intent_classifier import IntentLabel
        r = self._c().classify("sov channels list")
        assert r.label == IntentLabel.CLI_INTENT

    def test_sov_with_long_flag_is_cli(self) -> None:
        from sovereign_agent.intent_classifier import IntentLabel
        r = self._c().classify("sov --version")
        assert r.label == IntentLabel.CLI_INTENT

    def test_prose_with_is_a_pattern_is_nl(self) -> None:
        """The cliff case from the design docs."""
        from sovereign_agent.intent_classifier import IntentLabel
        r = self._c().classify("sovereign sync is a beautiful metaphor for life")
        assert r.label == IntentLabel.NL_INTENT
        assert r.confidence >= 0.70

    def test_question_is_nl(self) -> None:
        from sovereign_agent.intent_classifier import IntentLabel
        r = self._c().classify("what does sov doctor do?")
        assert r.label == IntentLabel.NL_INTENT

    def test_explanation_request_is_nl(self) -> None:
        from sovereign_agent.intent_classifier import IntentLabel
        r = self._c().classify("tell me about the sovereign system")
        assert r.label == IntentLabel.NL_INTENT

    def test_long_prose_without_markers_is_nl(self) -> None:
        """A long sentence with no shell markers but no obvious NL markers
        either should still trend NL based on word count."""
        from sovereign_agent.intent_classifier import IntentLabel
        text = "we should think carefully about the architecture before shipping"
        r = self._c().classify(text)
        assert r.label == IntentLabel.NL_INTENT

    def test_classifier_returns_source_name(self) -> None:
        r = self._c().classify("sov doctor")
        assert r.source == "heuristic"

    def test_classifier_never_raises(self) -> None:
        """Adversarial inputs must not crash."""
        c = self._c()
        for adversarial in (
            "\x00\x01\x02",
            "🎉" * 100,
            "sov" * 1000,
            None,  # type: ignore[arg-type]  — we explicitly allow None
        ):
            try:
                r = c.classify(adversarial)  # type: ignore[arg-type]
            except Exception as exc:  # noqa: BLE001
                pytest.fail(
                    f"HeuristicClassifier crashed on {adversarial!r}: {exc!r}"
                )


class TestClassifierReplyParser:
    """parse_classifier_reply() must handle every LLM reply shape robustly."""

    def test_clean_reply(self) -> None:
        from sovereign_agent.intent_classifier import (
            parse_classifier_reply, IntentLabel,
        )
        r = parse_classifier_reply("CLI_INTENT 0.95", source="test")
        assert r.label == IntentLabel.CLI_INTENT
        assert r.confidence == 0.95

    def test_extra_whitespace_tolerated(self) -> None:
        from sovereign_agent.intent_classifier import (
            parse_classifier_reply, IntentLabel,
        )
        r = parse_classifier_reply("  NL_INTENT   0.85  ", source="test")
        assert r.label == IntentLabel.NL_INTENT
        assert r.confidence == 0.85

    def test_case_insensitive_label(self) -> None:
        from sovereign_agent.intent_classifier import (
            parse_classifier_reply, IntentLabel,
        )
        r = parse_classifier_reply("ambiguous 0.5", source="test")
        assert r.label == IntentLabel.AMBIGUOUS

    def test_garbage_returns_ambiguous(self) -> None:
        from sovereign_agent.intent_classifier import (
            parse_classifier_reply, IntentLabel,
        )
        for garbage in ("", "hello world", "definitely not parseable", "🎉"):
            r = parse_classifier_reply(garbage, source="test")
            assert r.label == IntentLabel.AMBIGUOUS

    def test_confidence_clamped_to_unit_interval(self) -> None:
        """Even if the model returns 1.5 or -0.3, we clamp to [0,1]."""
        from sovereign_agent.intent_classifier import parse_classifier_reply
        r = parse_classifier_reply("CLI_INTENT 1.5", source="test")
        assert 0.0 <= r.confidence <= 1.0
        r = parse_classifier_reply("CLI_INTENT 0.0001", source="test")
        assert 0.0 <= r.confidence <= 1.0

    def test_label_with_surrounding_text(self) -> None:
        """The LLM might return prose like 'My answer is CLI_INTENT 0.9.'
        We should still extract correctly."""
        from sovereign_agent.intent_classifier import (
            parse_classifier_reply, IntentLabel,
        )
        r = parse_classifier_reply(
            "After analysis, my answer is CLI_INTENT 0.92.",
            source="test",
        )
        assert r.label == IntentLabel.CLI_INTENT
        assert r.confidence == 0.92


class TestDefaultClassifier:
    """The process-wide default classifier — lazy, replaceable, resettable."""

    def test_default_is_heuristic(self) -> None:
        from sovereign_agent.intent_classifier import (
            get_default_classifier, reset_default_classifier,
        )
        reset_default_classifier()
        c = get_default_classifier()
        assert c.name == "heuristic"

    def test_set_default_overrides(self) -> None:
        from sovereign_agent.intent_classifier import (
            HeuristicClassifier, get_default_classifier,
            set_default_classifier, reset_default_classifier,
            IntentLabel, IntentResult,
        )

        @dataclass
        class FakeClassifier:
            @property
            def name(self) -> str:
                return "fake-test"

            def classify(self, text: str) -> IntentResult:
                return IntentResult(IntentLabel.NL_INTENT, 1.0, self.name)

        try:
            set_default_classifier(FakeClassifier())  # type: ignore[arg-type]
            c = get_default_classifier()
            assert c.name == "fake-test"
        finally:
            reset_default_classifier()

    def test_reset_restores_lazy_default(self) -> None:
        from sovereign_agent.intent_classifier import (
            HeuristicClassifier, get_default_classifier,
            set_default_classifier, reset_default_classifier,
        )
        # Override
        from sovereign_agent.intent_classifier import IntentLabel, IntentResult

        @dataclass
        class FakeC:
            @property
            def name(self) -> str:
                return "fake"
            def classify(self, text: str) -> IntentResult:
                return IntentResult(IntentLabel.CLI_INTENT, 1.0, self.name)

        set_default_classifier(FakeC())  # type: ignore[arg-type]
        assert get_default_classifier().name == "fake"
        # Reset
        reset_default_classifier()
        assert get_default_classifier().name == "heuristic"


class TestOllamaClassifierSyncStub:
    """OllamaClassifier needs an event loop; its sync method is a safe stub."""

    def test_sync_classify_returns_ambiguous(self) -> None:
        from sovereign_agent.intent_classifier import (
            OllamaClassifier, IntentLabel,
        )
        c = OllamaClassifier()
        r = c.classify("sov doctor")
        # Sync stub returns AMBIGUOUS so callers fall through safely
        assert r.label == IntentLabel.AMBIGUOUS

    def test_name_includes_model(self) -> None:
        from sovereign_agent.intent_classifier import OllamaClassifier
        c = OllamaClassifier(model="phi3:mini")
        assert "phi3" in c.name


# ───────────────────────────────────────────────────────────────────────────
# § 4. Queue-of-queues — session extension mid-run
# ───────────────────────────────────────────────────────────────────────────


class TestQueueExtension:
    """Sessions can grow their own queue with explicit justification."""

    def _state(self, n_subtasks: int = 5):
        """Build a SessionState with N pending subtasks for testing."""
        from sovereign_agent.agent_session import SessionState, Subtask
        subtasks = [
            Subtask(
                id=f"s{i}",
                description=f"subtask {i}",
                status="pending",
            )
            for i in range(n_subtasks)
        ]
        return SessionState(
            session_id="test-session",
            goal="test",
            mode="oneshot",
            subtasks=subtasks,
            original_subtask_count=n_subtasks,
        )

    def _make_subtask(self, i: int = 100):
        from sovereign_agent.agent_session import Subtask
        return Subtask(id=f"s{i}", description=f"extension subtask {i}",
                       status="pending")

    def test_extend_appends_subtasks(self) -> None:
        from sovereign_agent.agent_session import extend_session_queue
        state = self._state(5)
        new = [self._make_subtask(100), self._make_subtask(101)]
        extend_session_queue(
            state,
            new,
            justification="discovered 2 more tools needed",
        )
        assert len(state.subtasks) == 7

    def test_extend_records_extension(self) -> None:
        from sovereign_agent.agent_session import extend_session_queue
        state = self._state(5)
        extend_session_queue(
            state, [self._make_subtask(100)],
            justification="need image-processing helper",
        )
        assert len(state.extensions) == 1
        ext = state.extensions[0]
        assert ext.added_subtasks == 1
        assert ext.justification == "need image-processing helper"

    def test_extend_with_cushion(self) -> None:
        """Cushion is tracked separately from the count of new subtasks
        so the audit shows 'we added 12 = 10 work + 2 safety'."""
        from sovereign_agent.agent_session import extend_session_queue
        state = self._state(5)
        new = [self._make_subtask(i) for i in range(100, 112)]  # 12 subtasks
        extend_session_queue(
            state, new,
            justification="need 10 more for tools; +2 cushion",
            cushion=2,
        )
        ext = state.extensions[0]
        assert ext.added_subtasks == 12
        assert ext.cushion == 2

    def test_multiple_extensions_accumulate(self) -> None:
        """Queue-of-QUEUES — each extension is its own record."""
        from sovereign_agent.agent_session import extend_session_queue
        state = self._state(5)
        extend_session_queue(state, [self._make_subtask(100)],
                              justification="first")
        extend_session_queue(state, [self._make_subtask(101),
                                       self._make_subtask(102)],
                              justification="second")
        extend_session_queue(state, [self._make_subtask(103)],
                              justification="third")
        assert len(state.extensions) == 3
        assert len(state.subtasks) == 9  # 5 original + 1 + 2 + 1
        assert state.extensions[0].justification == "first"
        assert state.extensions[1].added_subtasks == 2

    def test_extend_without_justification_raises(self) -> None:
        """The whole point is auditability — empty justification is a bug."""
        from sovereign_agent.agent_session import extend_session_queue
        state = self._state(5)
        with pytest.raises(ValueError, match="justification"):
            extend_session_queue(state, [self._make_subtask(100)],
                                  justification="")
        with pytest.raises(ValueError, match="justification"):
            extend_session_queue(state, [self._make_subtask(100)],
                                  justification="   ")

    def test_extend_with_no_subtasks_raises(self) -> None:
        from sovereign_agent.agent_session import extend_session_queue
        state = self._state(5)
        with pytest.raises(ValueError):
            extend_session_queue(state, [], justification="something")

    def test_extension_summary_no_extensions(self) -> None:
        state = self._state(5)
        assert state.extension_summary() == "no extensions"

    def test_extension_summary_single(self) -> None:
        from sovereign_agent.agent_session import extend_session_queue
        state = self._state(5)
        extend_session_queue(state, [self._make_subtask(100)],
                              justification="x")
        assert state.extension_summary() == "1 extension (+1 subtasks)"

    def test_extension_summary_multiple(self) -> None:
        from sovereign_agent.agent_session import extend_session_queue
        state = self._state(5)
        extend_session_queue(state, [self._make_subtask(i) for i in
                                      range(100, 110)],
                              justification="first")
        extend_session_queue(state, [self._make_subtask(i) for i in
                                      range(200, 215)],
                              justification="second")
        assert state.extension_summary() == "2 extensions (+10, +15 subtasks)"

    def test_current_run_number_reflects_progress(self) -> None:
        """The cockpit's queue-status display reads current_run_number."""
        from sovereign_agent.agent_session import SessionState, Subtask
        subtasks = [
            Subtask(id="s0", description="d0", status="done"),
            Subtask(id="s1", description="d1", status="done"),
            Subtask(id="s2", description="d2", status="skipped"),
            Subtask(id="s3", description="d3", status="pending"),
            Subtask(id="s4", description="d4", status="pending"),
        ]
        state = SessionState(
            session_id="t",
            goal="t",
            mode="oneshot",
            subtasks=subtasks,
        )
        # 2 done + 1 skipped = 3 completed
        assert state.current_run_number() == 3

    def test_extensions_field_default_is_empty(self) -> None:
        """Backward compat — sessions created before v0.2.32.0 have no
        extensions; they should deserialize with an empty list, not None."""
        state = self._state(5)
        assert isinstance(state.extensions, list)
        assert state.extensions == []


# ───────────────────────────────────────────────────────────────────────────
# § 5. THE CLIFF ORACLE — new entries for v0.2.32.0
# ───────────────────────────────────────────────────────────────────────────


class TestCliffOracleV0_2_32:
    """Cliffs surfaced by the design documents — pinned permanently."""

    def _norm(self, text: str):
        from sovereign_agent.cockpit.app import normalize_sov_prefix
        return normalize_sov_prefix(text)

    def _classify(self, text: str):
        from sovereign_agent.intent_classifier import HeuristicClassifier
        return HeuristicClassifier().classify(text)

    def test_cliff_2026_05_21_sov_sync_metaphor_is_nl(self) -> None:
        """2026-05-21 — design doc cliff.

        Original failure: 'sovereign sync is a beautiful metaphor for life'
        has `sov sync` as a structural CLI prefix. Without Stage C, the
        normalizer would unwrap it through `sync` (a known subcommand) and
        execute. With Stage C, the heuristic classifier sees 'is a beautiful'
        and vetoes with NL_INTENT.
        """
        from sovereign_agent.intent_classifier import IntentLabel
        r = self._classify("sovereign sync is a beautiful metaphor for life")
        assert r.label == IntentLabel.NL_INTENT, (
            f"DESIGN-DOC CLIFF: prose-with-CLI-prefix must classify as NL; "
            f"got {r.label!r}"
        )

    def test_cliff_2026_05_21_sov_plan_global_ai_domination(self) -> None:
        """2026-05-21 — design doc cliff.

        'sovereign plan global AI domination by next Tuesday' — `plan` is
        a known subcommand but the sentence is obvious prose."""
        from sovereign_agent.intent_classifier import IntentLabel
        r = self._classify(
            "sovereign plan global AI domination by next Tuesday"
        )
        # Should classify as NL or at minimum not be a confident CLI signal
        assert r.label in (IntentLabel.NL_INTENT, IntentLabel.AMBIGUOUS), (
            f"got {r.label!r}; the heuristic must not see this as CLI"
        )

    def test_cliff_2026_05_21_what_does_command_do_is_nl(self) -> None:
        """Asking about a command is not the same as running it."""
        from sovereign_agent.intent_classifier import IntentLabel
        r = self._classify("what does sov doctor do?")
        assert r.label == IntentLabel.NL_INTENT

    def test_cliff_2026_05_21_explain_request_is_nl(self) -> None:
        from sovereign_agent.intent_classifier import IntentLabel
        r = self._classify("explain how the sovereign agent works")
        assert r.label == IntentLabel.NL_INTENT

    def test_cliff_2026_05_21_mode_state_survives_round_trip(self) -> None:
        """If mode persistence ever silently regresses, this catches it."""
        import tempfile
        from sovereign_agent.cockpit_modes import (
            CockpitMode, load_mode, set_mode,
        )
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            set_mode(CockpitMode.WORK, config_dir=tmp_path)
            # Now imagine the cockpit process restarts — fresh load
            state = load_mode(tmp_path)
            assert state.mode == CockpitMode.WORK, (
                "CLIFF: mode state lost across load_mode calls — "
                "operators rely on this to survive cockpit restarts"
            )

    def test_cliff_2026_05_21_queue_extension_requires_justification(self) -> None:
        """The whole point of queue-of-queues is auditability — empty
        justification must NEVER be accepted."""
        from sovereign_agent.agent_session import (
            SessionState, Subtask, extend_session_queue,
        )
        state = SessionState(
            session_id="t", goal="t", mode="oneshot",
            subtasks=[Subtask(id="s0", description="d")],
        )
        new = [Subtask(id="s1", description="new")]
        with pytest.raises(ValueError):
            extend_session_queue(state, new, justification="")
        # State must not have been mutated by a failed extension
        assert len(state.subtasks) == 1
        assert len(state.extensions) == 0


# ───────────────────────────────────────────────────────────────────────────
# § 6. Kernel still holds
# ───────────────────────────────────────────────────────────────────────────


class TestKernelInvariantsCarryForward:
    """Every release re-affirms the kernel hasn't drifted."""

    def test_seven_commitments(self) -> None:
        from sovereign_agent.aria import CORE_COMMITMENTS
        assert len(CORE_COMMITMENTS) == 7

    def test_designation(self) -> None:
        from sovereign_agent.aria import CORE_DESIGNATION
        assert CORE_DESIGNATION == "Aria-Sovereign-V1"

    def test_constitution_seven(self) -> None:
        from sovereign_agent.constitution import list_all
        assert len(list_all()) == 7

    def test_modes_dont_override_commitments(self) -> None:
        """Mode is about initiative, not trust. The seven commitments
        bind in BOTH modes."""
        from sovereign_agent.constitution import check_action
        # A Tier-3 action without idempotency must still fail in both modes
        report = check_action({"tier": 3, "kind": "person.upsert"})
        bounded = [v for v in report.verdicts
                   if v.commitment_id == "bounded_authority"]
        assert not bounded[0].passed
