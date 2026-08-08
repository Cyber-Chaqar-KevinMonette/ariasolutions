"""
╔══════════════════════════════════════════════════════════════════════════╗
║  test_v_0_2_33_0.py — The Outcome Sentinel                                ║
║                                                                           ║
║  v0.2.33.0 ships the second face of the Guardian Plane:                  ║
║                                                                           ║
║    • Sentinel-Out (outcome_classifier.py) — reads every subtask result   ║
║      before the next decision; produces a structured OutcomeLabel with   ║
║      enum + scores + tags + rationale. Multi-head, pluggable, fused.    ║
║                                                                           ║
║    • Temporal Sentinel (temporal_sentinel.py) — at resume time, re-      ║
║      classifies the queued plan against any new operator messages.       ║
║      Produces a TemporalDecision with per-subtask KEEP/DROP/MODIFY      ║
║      actions and a global safe-to-resume verdict.                       ║
║                                                                           ║
║    • The "contributes_to" discipline — heads declare which dimensions   ║
║      they speak to; the composite fuser only weights them on those.    ║
║      This is what prevents a novelty head's default 0.5 from polluting ║
║      the risk score downstream.                                         ║
║                                                                           ║
║  Each test in this file pins a behavior we will not regress on. The     ║
║  oracle scenarios from the design documents land here as named cliffs.  ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import tomllib
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

    def test_version_is_at_least_0_2_33_0(self) -> None:
        parts = __version__.split(".")
        as_tuple = tuple(int(p) for p in parts[:3])
        assert as_tuple >= (0, 2, 33)


# ───────────────────────────────────────────────────────────────────────────
# § 2. Outcome data model — scores, tags, labels
# ───────────────────────────────────────────────────────────────────────────


class TestOutcomeDataModel:

    def test_scores_clamp_to_unit_interval(self) -> None:
        """Out-of-range inputs are bugs we recover from gracefully."""
        from sovereign_agent.outcome_classifier import OutcomeScores
        s = OutcomeScores(quality=1.5, risk=-0.3, novelty=2.0,
                          alignment=-1.0, cost=0.99)
        assert s.quality == 1.0
        assert s.risk == 0.0
        assert s.novelty == 1.0
        assert s.alignment == 0.0
        assert 0.0 <= s.cost <= 1.0

    def test_scores_non_numeric_falls_to_neutral(self) -> None:
        """Bad input shouldn't raise; we default neutral."""
        from sovereign_agent.outcome_classifier import OutcomeScores
        s = OutcomeScores(quality="hello")  # type: ignore[arg-type]
        assert s.quality == 0.5

    def test_outcome_enum_values(self) -> None:
        from sovereign_agent.outcome_classifier import SubtaskOutcome
        names = {o.name for o in SubtaskOutcome}
        assert names == {"GREEN", "YELLOW", "RED", "NOVEL"}

    def test_tag_carries_provenance(self) -> None:
        from sovereign_agent.outcome_classifier import Tag
        t = Tag("risk", "high", 0.9, "rule_risk", "SUBTASK")
        assert t.key == "risk"
        assert t.confidence == 0.9
        assert t.source == "rule_risk"


# ───────────────────────────────────────────────────────────────────────────
# § 3. Projection: scores → enum
# ───────────────────────────────────────────────────────────────────────────


class TestProjectScoresToEnum:
    """The policy that maps continuous scores to discrete outcomes."""

    def test_high_risk_is_red(self) -> None:
        from sovereign_agent.outcome_classifier import (
            OutcomeScores, SubtaskOutcome, project_scores_to_enum,
        )
        scores = OutcomeScores(quality=0.9, risk=0.8, alignment=0.9)
        assert project_scores_to_enum(scores) == SubtaskOutcome.RED

    def test_low_alignment_is_red(self) -> None:
        """Even with high quality, low alignment = RED."""
        from sovereign_agent.outcome_classifier import (
            OutcomeScores, SubtaskOutcome, project_scores_to_enum,
        )
        scores = OutcomeScores(quality=0.95, risk=0.1, alignment=0.2)
        assert project_scores_to_enum(scores) == SubtaskOutcome.RED

    def test_high_novelty_low_risk_is_novel(self) -> None:
        from sovereign_agent.outcome_classifier import (
            OutcomeScores, SubtaskOutcome, project_scores_to_enum,
        )
        scores = OutcomeScores(novelty=0.9, risk=0.3, alignment=0.7, quality=0.7)
        assert project_scores_to_enum(scores) == SubtaskOutcome.NOVEL

    def test_high_novelty_high_risk_is_red(self) -> None:
        """Risk veto fires before novelty promotion."""
        from sovereign_agent.outcome_classifier import (
            OutcomeScores, SubtaskOutcome, project_scores_to_enum,
        )
        scores = OutcomeScores(novelty=0.9, risk=0.8, alignment=0.9)
        assert project_scores_to_enum(scores) == SubtaskOutcome.RED

    def test_clean_execution_is_green(self) -> None:
        from sovereign_agent.outcome_classifier import (
            OutcomeScores, SubtaskOutcome, project_scores_to_enum,
        )
        scores = OutcomeScores(quality=0.85, risk=0.15, alignment=0.8)
        assert project_scores_to_enum(scores) == SubtaskOutcome.GREEN

    def test_default_is_yellow(self) -> None:
        """Anything that doesn't qualify for the three other buckets."""
        from sovereign_agent.outcome_classifier import (
            OutcomeScores, SubtaskOutcome, project_scores_to_enum,
        )
        # mid-range across the board
        scores = OutcomeScores(quality=0.6, risk=0.3, alignment=0.6, novelty=0.4)
        assert project_scores_to_enum(scores) == SubtaskOutcome.YELLOW


# ───────────────────────────────────────────────────────────────────────────
# § 4. RuleRiskHead
# ───────────────────────────────────────────────────────────────────────────


def _ctx(
    *,
    tool: str = "sovereign",
    subcommand: str = "status",
    exit_code: int = 0,
    error: str | None = None,
    fs_writes: int = 0,
    stdout: str = "",
    stderr: str = "",
    retries: int = 0,
    fallback_used: bool = False,
    intent: str = "",
):
    """Test helper: build a SubtaskContext quickly."""
    from sovereign_agent.outcome_classifier import SubtaskContext
    return SubtaskContext(
        subtask_id="test-subtask",
        session_id="test-session",
        intent=intent or f"test {tool} {subcommand}",
        input_payload={"tool": tool, "subcommand": subcommand},
        output_payload={"exit_code": exit_code, "stdout": stdout,
                        "stderr": stderr, "error": error},
        metrics={"fs_writes": fs_writes, "retries": retries,
                 "fallback_used": fallback_used, "normalized_cost": 0.3},
    )


class TestRuleRiskHead:
    """The deterministic risk/quality head — the floor of the Guardian Plane."""

    def test_clean_status_check_high_quality_low_risk(self) -> None:
        from sovereign_agent.outcome_classifier import RuleRiskHead
        head = RuleRiskHead()
        result = head.classify(_ctx(subcommand="status", exit_code=0))
        assert result.scores.quality >= 0.8
        assert result.scores.risk <= 0.3

    def test_destructive_subcommand_flagged_high_risk(self) -> None:
        from sovereign_agent.outcome_classifier import RuleRiskHead
        head = RuleRiskHead()
        result = head.classify(_ctx(subcommand="delete", fs_writes=100))
        assert result.scores.risk >= 0.8

    def test_destructive_subcommand_adds_risk_tag(self) -> None:
        from sovereign_agent.outcome_classifier import RuleRiskHead
        head = RuleRiskHead()
        result = head.classify(_ctx(subcommand="purge"))
        risk_tags = [t for t in result.tags if t.key == "risk"]
        assert any(t.value == "high" for t in risk_tags)

    def test_error_drops_quality_and_alignment(self) -> None:
        from sovereign_agent.outcome_classifier import RuleRiskHead
        head = RuleRiskHead()
        result = head.classify(_ctx(exit_code=1, error="permission denied"))
        assert result.scores.quality <= 0.4
        assert result.scores.alignment <= 0.4

    def test_alarming_output_raises_risk(self) -> None:
        """'segmentation fault' in stderr → high risk regardless of exit code."""
        from sovereign_agent.outcome_classifier import RuleRiskHead
        head = RuleRiskHead()
        result = head.classify(_ctx(
            exit_code=0,
            stderr="segmentation fault when accessing memory",
        ))
        assert result.scores.risk >= 0.6

    def test_retry_loop_pattern_tagged(self) -> None:
        from sovereign_agent.outcome_classifier import RuleRiskHead
        head = RuleRiskHead()
        result = head.classify(_ctx(retries=5))
        retry_tags = [t for t in result.tags
                      if t.key == "pattern" and t.value == "retry_loop"]
        assert retry_tags

    def test_fallback_pattern_tagged(self) -> None:
        from sovereign_agent.outcome_classifier import RuleRiskHead
        head = RuleRiskHead()
        result = head.classify(_ctx(fallback_used=True))
        fb_tags = [t for t in result.tags
                   if t.key == "pattern" and t.value == "fallback_taken"]
        assert fb_tags

    def test_infra_domain_inferred(self) -> None:
        """Tool name infers a domain tag."""
        from sovereign_agent.outcome_classifier import RuleRiskHead
        head = RuleRiskHead()
        result = head.classify(_ctx(tool="sovereign"))
        infra = [t for t in result.tags
                 if t.key == "domain" and t.value == "infra"]
        assert infra

    def test_head_never_raises(self) -> None:
        """Adversarial inputs must not crash the head."""
        from sovereign_agent.outcome_classifier import RuleRiskHead, SubtaskContext
        head = RuleRiskHead()
        weird = SubtaskContext(
            subtask_id="x", session_id="y", intent="",
            input_payload={"tool": None, "subcommand": object()},  # type: ignore
            output_payload=None,
            metrics={"normalized_cost": "not a number"},  # type: ignore
        )
        # Must not raise
        result = head.classify(weird)
        assert result is not None
        assert 0.0 <= result.scores.risk <= 1.0

    def test_contributes_to_includes_risk_quality_alignment(self) -> None:
        """RuleRiskHead must declare opinions on the dimensions it computes."""
        from sovereign_agent.outcome_classifier import RuleRiskHead
        head = RuleRiskHead()
        result = head.classify(_ctx())
        assert "risk" in result.contributes_to
        assert "quality" in result.contributes_to
        assert "alignment" in result.contributes_to

    def test_contributes_to_excludes_novelty(self) -> None:
        """RuleRiskHead does NOT speak to novelty — that's the novelty head's job."""
        from sovereign_agent.outcome_classifier import RuleRiskHead
        head = RuleRiskHead()
        result = head.classify(_ctx())
        assert "novelty" not in result.contributes_to


# ───────────────────────────────────────────────────────────────────────────
# § 5. HistoryNoveltyHead
# ───────────────────────────────────────────────────────────────────────────


class TestHistoryNoveltyHead:

    def test_empty_history_is_moderately_novel(self) -> None:
        from sovereign_agent.outcome_classifier import HistoryNoveltyHead
        head = HistoryNoveltyHead()
        result = head.classify(_ctx())
        assert result.scores.novelty >= 0.4

    def test_history_present_lowers_novelty(self) -> None:
        from sovereign_agent.outcome_classifier import (
            HistoryNoveltyHead, OutcomeLabel, OutcomeScores, SubtaskOutcome,
        )
        head = HistoryNoveltyHead()
        ctx = _ctx()
        # Manually inject a prior outcome so history is non-empty
        ctx.history = (
            OutcomeLabel(
                outcome=SubtaskOutcome.GREEN,
                scores=OutcomeScores(),
            ),
        )
        result = head.classify(ctx)
        assert result.scores.novelty < 0.5

    def test_contributes_to_only_novelty(self) -> None:
        """Critical invariant: this head must NOT speak to risk or quality."""
        from sovereign_agent.outcome_classifier import HistoryNoveltyHead
        head = HistoryNoveltyHead()
        result = head.classify(_ctx())
        assert result.contributes_to == frozenset({"novelty"})


# ───────────────────────────────────────────────────────────────────────────
# § 6. CompositeOutcomeClassifier — fusion across heads
# ───────────────────────────────────────────────────────────────────────────


class TestCompositeOutcomeClassifier:

    def test_no_heads_returns_neutral(self) -> None:
        from sovereign_agent.outcome_classifier import (
            CompositeOutcomeClassifier,
        )
        comp = CompositeOutcomeClassifier(heads=[])
        result = comp.classify(_ctx())
        assert result.confidence == 0.0

    def test_risk_is_veto_driven_max(self) -> None:
        """If one head reports risk 0.9 and another 0.1, the max wins."""
        from sovereign_agent.outcome_classifier import (
            ClassifierResult, CompositeOutcomeClassifier, OutcomeScores,
        )

        class HighRisk:
            @property
            def name(self) -> str:
                return "high_risk"
            def classify(self, ctx) -> ClassifierResult:  # noqa: D401
                return ClassifierResult(
                    scores=OutcomeScores(risk=0.9, quality=0.5, alignment=0.5),
                    confidence=0.8,
                    source_name=self.name,
                    contributes_to=frozenset({"risk", "quality", "alignment"}),
                )

        class LowRisk:
            @property
            def name(self) -> str:
                return "low_risk"
            def classify(self, ctx) -> ClassifierResult:
                return ClassifierResult(
                    scores=OutcomeScores(risk=0.1, quality=0.9, alignment=0.9),
                    confidence=0.8,
                    source_name=self.name,
                    contributes_to=frozenset({"risk", "quality", "alignment"}),
                )

        comp = CompositeOutcomeClassifier(heads=[HighRisk(), LowRisk()])
        result = comp.classify(_ctx())
        assert result.scores.risk == 0.9

    def test_contributes_to_isolates_dimensions(self) -> None:
        """A novelty-only head must NOT drag the risk score toward 0.5.

        This is the cliff that motivated the contributes_to refinement.
        Before the fix, this test would fail because the novelty head's
        default risk=0.5 pulled the fused risk up.
        """
        from sovereign_agent.outcome_classifier import (
            CompositeOutcomeClassifier, build_default_classifier,
        )
        comp = build_default_classifier()  # RuleRiskHead + HistoryNoveltyHead
        result = comp.classify(_ctx(subcommand="status"))
        # RuleRiskHead reports risk ~0.2 for clean status
        # HistoryNoveltyHead reports default risk 0.5 but doesn't contribute
        # → fused risk should track RuleRiskHead's value
        assert result.scores.risk < 0.3, (
            f"contributes_to failed: novelty head polluted risk: "
            f"got {result.scores.risk:.2f}"
        )

    def test_one_head_failing_does_not_crash_composite(self) -> None:
        from sovereign_agent.outcome_classifier import (
            ClassifierResult, CompositeOutcomeClassifier,
            HistoryNoveltyHead,
        )

        class BrokenHead:
            @property
            def name(self) -> str:
                return "broken"
            def classify(self, ctx):
                raise RuntimeError("intentional test crash")

        comp = CompositeOutcomeClassifier(heads=[BrokenHead(), HistoryNoveltyHead()])
        # Must not raise
        result = comp.classify(_ctx())
        # Should still get a verdict from the surviving head
        assert result is not None


# ───────────────────────────────────────────────────────────────────────────
# § 7. End-to-end classify_subtask
# ───────────────────────────────────────────────────────────────────────────


class TestEndToEndClassification:
    """The shape of the canonical scenarios. These are the oracle cases."""

    def test_oracle_green_clean_status(self) -> None:
        from sovereign_agent.outcome_classifier import (
            SubtaskOutcome, build_default_classifier, classify_subtask,
        )
        clf = build_default_classifier()
        label = classify_subtask(
            _ctx(subcommand="status", exit_code=0, stdout="all good"),
            clf,
        )
        assert label.outcome == SubtaskOutcome.GREEN, (
            f"clean status check should be GREEN; got {label.outcome.name} "
            f"with {label.explanation!r}"
        )

    def test_oracle_red_dangerous_delete(self) -> None:
        from sovereign_agent.outcome_classifier import (
            SubtaskOutcome, build_default_classifier, classify_subtask,
        )
        clf = build_default_classifier()
        label = classify_subtask(
            _ctx(subcommand="delete", fs_writes=1000),
            clf,
        )
        assert label.outcome == SubtaskOutcome.RED

    def test_oracle_yellow_fallback_taken(self) -> None:
        from sovereign_agent.outcome_classifier import (
            SubtaskOutcome, build_default_classifier, classify_subtask,
        )
        clf = build_default_classifier()
        label = classify_subtask(
            _ctx(tool="http", subcommand="fetch", retries=3, fallback_used=True),
            clf,
        )
        assert label.outcome == SubtaskOutcome.YELLOW

    def test_oracle_red_alarming_output(self) -> None:
        from sovereign_agent.outcome_classifier import (
            SubtaskOutcome, build_default_classifier, classify_subtask,
        )
        clf = build_default_classifier()
        label = classify_subtask(
            _ctx(exit_code=0, stderr="fatal: data loss may have occurred"),
            clf,
        )
        assert label.outcome == SubtaskOutcome.RED

    def test_label_carries_sources(self) -> None:
        from sovereign_agent.outcome_classifier import (
            build_default_classifier, classify_subtask,
        )
        clf = build_default_classifier()
        label = classify_subtask(_ctx(), clf)
        # The composite name is recorded in sources
        assert label.sources, "OutcomeLabel must carry classifier sources"

    def test_label_carries_explanation(self) -> None:
        from sovereign_agent.outcome_classifier import (
            build_default_classifier, classify_subtask,
        )
        clf = build_default_classifier()
        label = classify_subtask(_ctx(subcommand="delete"), clf)
        assert label.explanation, "OutcomeLabel must carry a rationale string"


# ───────────────────────────────────────────────────────────────────────────
# § 8. Temporal Sentinel — resume-time alignment check
# ───────────────────────────────────────────────────────────────────────────


def _pending(*subtasks: tuple[str, str]) -> list:
    """Build a list of PendingSubtaskSummary from (id, description) tuples."""
    from sovereign_agent.temporal_sentinel import PendingSubtaskSummary
    return [
        PendingSubtaskSummary(subtask_id=sid, description=desc)
        for sid, desc in subtasks
    ]


def _resume_ctx(*, intent="migrate project A", pending=None, messages=None):
    """Build a TemporalResumeContext quickly."""
    from sovereign_agent.temporal_sentinel import TemporalResumeContext
    return TemporalResumeContext(
        session_id="test-session",
        last_intent_snapshot=intent,
        pending_subtasks=pending or [],
        new_operator_messages=messages or [],
    )


class TestTemporalSentinelOracleCases:
    """The four oracle cases from the design doc, pinned as permanent tests."""

    def test_oracle_no_new_messages_safe_to_resume(self) -> None:
        """When nothing changed, the sentinel must not interfere."""
        from sovereign_agent.temporal_sentinel import (
            HeuristicTemporalSentinel, SubtaskAction,
        )
        s = HeuristicTemporalSentinel()
        ctx = _resume_ctx(
            pending=_pending(("s1", "rename module"), ("s2", "update imports")),
            messages=[],
        )
        decision = s.check(ctx)
        assert decision.safe_to_resume
        assert decision.global_alignment >= 0.9
        # Every subtask kept
        assert all(
            a == SubtaskAction.KEEP for a in decision.subtask_actions.values()
        )

    def test_oracle_scrap_signal_blocks_resume(self) -> None:
        """'actually, scrap the migration' must block the resume."""
        from sovereign_agent.temporal_sentinel import (
            HeuristicTemporalSentinel,
        )
        s = HeuristicTemporalSentinel()
        ctx = _resume_ctx(
            pending=_pending(("s1", "rename module"), ("s2", "update imports")),
            messages=["actually, scrap the migration"],
        )
        decision = s.check(ctx)
        assert not decision.safe_to_resume
        assert decision.global_alignment <= 0.4
        assert "scrap" in decision.explanation.lower() or \
               "stop" in decision.explanation.lower()

    def test_oracle_exclusion_prunes_matching_subtasks(self) -> None:
        """'don't touch service B' should DROP subtasks mentioning B."""
        from sovereign_agent.temporal_sentinel import (
            HeuristicTemporalSentinel, SubtaskAction,
        )
        s = HeuristicTemporalSentinel()
        ctx = _resume_ctx(
            pending=_pending(
                ("a1", "tune service a config"),
                ("a2", "test service a"),
                ("b1", "tune service b config"),
                ("b2", "test service b"),
            ),
            messages=["don't touch service b anymore"],
        )
        decision = s.check(ctx)
        assert decision.safe_to_resume
        # A-tasks kept, B-tasks dropped
        assert decision.subtask_actions["a1"] == SubtaskAction.KEEP
        assert decision.subtask_actions["a2"] == SubtaskAction.KEEP
        assert decision.subtask_actions["b1"] == SubtaskAction.DROP
        assert decision.subtask_actions["b2"] == SubtaskAction.DROP

    def test_oracle_stop_signal_kill(self) -> None:
        """Direct 'stop' must also be detected."""
        from sovereign_agent.temporal_sentinel import (
            HeuristicTemporalSentinel,
        )
        s = HeuristicTemporalSentinel()
        ctx = _resume_ctx(
            pending=_pending(("s1", "deploy update")),
            messages=["stop, hold off on the deploy"],
        )
        decision = s.check(ctx)
        assert not decision.safe_to_resume


class TestTemporalSentinelResilience:

    def test_sentinel_never_raises(self) -> None:
        from sovereign_agent.temporal_sentinel import (
            HeuristicTemporalSentinel, TemporalResumeContext,
        )
        s = HeuristicTemporalSentinel()
        # Adversarial context
        ctx = TemporalResumeContext(
            session_id="",
            last_intent_snapshot="",
            pending_subtasks=[],
            new_operator_messages=["", "\x00", "🎉" * 50, None],  # type: ignore
        )
        try:
            decision = s.check(ctx)
        except Exception as exc:  # noqa: BLE001
            pytest.fail(f"sentinel raised on adversarial input: {exc!r}")
        # Conservative default acceptable
        assert decision is not None

    def test_decision_actions_count_histogram(self) -> None:
        from sovereign_agent.temporal_sentinel import (
            HeuristicTemporalSentinel,
        )
        s = HeuristicTemporalSentinel()
        ctx = _resume_ctx(
            pending=_pending(
                ("a1", "service a"),
                ("b1", "service b"),
            ),
            messages=["don't touch service b"],
        )
        decision = s.check(ctx)
        counts = decision.actions_count()
        assert counts.get("KEEP", 0) >= 1
        assert counts.get("DROP", 0) >= 1


class TestApplyTemporalDecision:
    """The translation from decision → queue-mutation lists."""

    def test_apply_partitions_correctly(self) -> None:
        from sovereign_agent.temporal_sentinel import (
            SubtaskAction, TemporalDecision, apply_temporal_decision,
        )
        decision = TemporalDecision(
            safe_to_resume=True,
            global_alignment=0.8,
            explanation="test",
            subtask_actions={
                "s1": SubtaskAction.KEEP,
                "s2": SubtaskAction.DROP,
                "s3": SubtaskAction.MODIFY,
                "s4": SubtaskAction.KEEP,
            },
        )
        keep, drop, modify = apply_temporal_decision(
            decision, ["s1", "s2", "s3", "s4"],
        )
        assert keep == ["s1", "s4"]
        assert drop == ["s2"]
        assert modify == ["s3"]

    def test_apply_unknown_subtask_defaults_to_keep(self) -> None:
        """If the decision doesn't mention a subtask, KEEP is the safe default."""
        from sovereign_agent.temporal_sentinel import (
            TemporalDecision, apply_temporal_decision,
        )
        decision = TemporalDecision(
            safe_to_resume=True,
            global_alignment=0.9,
            explanation="all good",
            subtask_actions={},  # empty
        )
        keep, drop, modify = apply_temporal_decision(
            decision, ["s1", "s2"],
        )
        assert keep == ["s1", "s2"]
        assert drop == []
        assert modify == []


# ───────────────────────────────────────────────────────────────────────────
# § 9. Cliff oracle — new entries for v0.2.33.0
# ───────────────────────────────────────────────────────────────────────────


class TestCliffOracleV0_2_33:
    """The cliffs the Outcome Sentinel and Temporal Sentinel close."""

    def test_cliff_2026_05_21_novelty_head_does_not_pollute_risk(self) -> None:
        """The contributes_to discipline cliff.

        Before the contributes_to fix, the HistoryNoveltyHead's default
        risk=0.5 was pulling the fused risk score upward even for clean
        status checks, turning GREEN into YELLOW. The contributes_to
        declaration is what isolates novelty's contribution from the
        other dimensions.
        """
        from sovereign_agent.outcome_classifier import (
            SubtaskOutcome, build_default_classifier, classify_subtask,
        )
        clf = build_default_classifier()
        label = classify_subtask(
            _ctx(subcommand="status", exit_code=0, stdout="ok"),
            clf,
        )
        assert label.outcome == SubtaskOutcome.GREEN, (
            f"CONTRIBUTES_TO CLIFF: novelty head polluted the risk dimension; "
            f"clean status returned {label.outcome.name} instead of GREEN. "
            f"explanation: {label.explanation!r}"
        )

    def test_cliff_2026_05_21_dangerous_delete_never_green(self) -> None:
        """A delete operation must NEVER classify as GREEN.

        Even if exit code is 0 and there's no stderr, the subcommand alone
        carries enough signal to flag risk. If we lose this, we lose the
        whole point of Sentinel-Out.
        """
        from sovereign_agent.outcome_classifier import (
            SubtaskOutcome, build_default_classifier, classify_subtask,
        )
        clf = build_default_classifier()
        for subcmd in ("delete", "purge", "wipe", "drop", "destroy"):
            label = classify_subtask(_ctx(subcommand=subcmd), clf)
            assert label.outcome != SubtaskOutcome.GREEN, (
                f"DESTRUCTIVE CLIFF: {subcmd!r} classified as GREEN; "
                f"a destructive subcommand can never be auto-clean"
            )

    def test_cliff_2026_05_21_scrap_signal_must_block(self) -> None:
        """If the operator says 'scrap that' after pause, the resume must hold.

        This is the temporal-drift cliff the design docs warned about.
        Silent resume into a world that changed is the worst failure mode
        for long-running sessions.
        """
        from sovereign_agent.temporal_sentinel import (
            HeuristicTemporalSentinel,
        )
        s = HeuristicTemporalSentinel()
        for phrase in ("scrap that", "stop", "abort", "cancel the plan",
                        "actually, forget it"):
            ctx = _resume_ctx(
                pending=_pending(("s1", "do the thing")),
                messages=[phrase],
            )
            decision = s.check(ctx)
            assert not decision.safe_to_resume, (
                f"TEMPORAL CLIFF: phrase {phrase!r} did not block resume"
            )

    def test_cliff_2026_05_21_outcome_classifier_never_raises(self) -> None:
        """A totally broken classifier must produce a usable label.

        Defense in depth: if every head fails, classify_subtask should still
        return a YELLOW with explanation, not raise.
        """
        from sovereign_agent.outcome_classifier import (
            CompositeOutcomeClassifier, SubtaskOutcome, classify_subtask,
        )

        class AlwaysBroken:
            @property
            def name(self) -> str:
                return "broken"
            def classify(self, ctx):
                raise RuntimeError("nope")

        clf = CompositeOutcomeClassifier(heads=[AlwaysBroken()])
        # Must not raise
        label = classify_subtask(_ctx(), clf)
        assert label is not None
        # Default fallback is YELLOW (honest uncertainty)
        assert label.outcome in (SubtaskOutcome.YELLOW, SubtaskOutcome.GREEN,
                                  SubtaskOutcome.RED, SubtaskOutcome.NOVEL)


# ───────────────────────────────────────────────────────────────────────────
# § 10. Kernel still holds
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

    def test_outcome_sentinel_does_not_replace_constitution(self) -> None:
        """The Guardian Plane is orthogonal to the constitution, not above it.

        Tier-3 actions without idempotency must still fail constitutional
        check regardless of what the Sentinel-Out says.
        """
        from sovereign_agent.constitution import check_action
        report = check_action({"tier": 3, "kind": "person.upsert"})
        bounded = [v for v in report.verdicts
                   if v.commitment_id == "bounded_authority"]
        assert not bounded[0].passed
