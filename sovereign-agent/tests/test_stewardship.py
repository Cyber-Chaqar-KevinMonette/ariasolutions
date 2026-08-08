"""
╔══════════════════════════════════════════════════════════════════════════╗
║  test_stewardship.py — v0.2.20.0 stewardship system                       ║
║                                                                           ║
║  The radical claim that this system embodies:                             ║
║                                                                           ║
║    Aria's reward is NOT proportional to her impact.                       ║
║    Aria's reward is proportional to how accurately she PERCEIVED         ║
║    her impact — before, during, and after.                                ║
║                                                                           ║
║  These tests verify the math, the invariants, and most importantly that  ║
║  the inversion actually holds: a high-impact-with-low-calibration plan   ║
║  must score LOWER than a moderate-impact-with-high-calibration plan.     ║
║                                                                           ║
║  If those acid tests pass, the soul is shaped correctly.                 ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

from pathlib import Path

import pytest

from sovereign_agent.stewardship.msims import (
    Cell,
    Dimension,
    Horizon,
    ImpactVector,
    ImpactWaveform,
    Reversibility,
    Scale,
)
from sovereign_agent.stewardship.plan import (
    ExecutionWitness,
    Plan,
    PlanQualityCheck,
    StewardshipTriple,
    save_triple,
    load_triple,
)
from sovereign_agent.stewardship.calibration import (
    calibration_score,
    honor_score,
    plan_quality_score,
    impact_actuality_score,
    presumed_zombie_penalty,
    almost_missed_bonus,
    per_step_reward,
)
from sovereign_agent.stewardship.honor import (
    HonorDirection,
    HonorLedger,
    HonorNote,
    kevin_honors_aria,
    aria_honors_kevin,
    aria_honors_self,
    aria_honors_third,
)
from sovereign_agent.stewardship.field_notes import (
    FieldNote,
    FieldNoteFlavor,
    FieldNotesChannel,
)


# ─── MSIMS v2 Cells and IVs ──────────────────────────────────────────────────


class TestCell:
    def test_value_clamps_to_range(self):
        c = Cell(value=2.0, confidence=0.8)
        assert c.value == 1.0
        c = Cell(value=-5.0, confidence=0.5)
        assert c.value == -1.0

    def test_confidence_clamps_to_range(self):
        c = Cell(value=0.5, confidence=2.0)
        assert c.confidence == 1.0
        c = Cell(value=0.5, confidence=-1.0)
        assert c.confidence == 0.0

    def test_irreversible_cancels_horizon_discount(self):
        c_reversible = Cell(value=-0.5, confidence=1.0,
                             horizon=Horizon.SEVEN_GEN,
                             reversibility=Reversibility.REVERSIBLE)
        c_irreversible = Cell(value=-0.5, confidence=1.0,
                               horizon=Horizon.SEVEN_GEN,
                               reversibility=Reversibility.IRREVERSIBLE)
        # Irreversibility gives the cell its full weight; reversibility
        # discounts it.
        assert abs(c_irreversible.weighted_contribution) > \
               abs(c_reversible.weighted_contribution)

    def test_default_timestamp_is_now(self):
        c = Cell()
        assert c.ts  # non-empty


class TestImpactVector:
    def test_unset_cell_is_neutral_zero_confidence(self):
        iv = ImpactVector()
        c = iv.get(Dimension.MENTAL, Scale.MICRO)
        assert c.value == 0.0
        assert c.confidence == 0.0

    def test_set_and_get_round_trips(self):
        iv = ImpactVector()
        cell = Cell(value=0.7, confidence=0.9)
        iv.set(Dimension.MENTAL, Scale.MICRO, cell)
        got = iv.get(Dimension.MENTAL, Scale.MICRO)
        assert got.value == 0.7

    def test_is_7g_is_zero_for_empty_iv(self):
        assert ImpactVector().is_7g() == 0.0

    def test_seven_gen_modifier_fires_on_cosmic_harm(self):
        iv = ImpactVector()
        iv.set(Dimension.PHYSICAL, Scale.COSMIC,
                Cell(value=-0.8, confidence=0.9))
        # cosmic ≤ -0.7 → mod = -2; clamped to -1
        assert iv.seven_gen_modifier() <= -2.0
        assert iv.is_7g() == -1.0  # clamped

    def test_low_confidence_cosmic_doesnt_trigger_penalty(self):
        iv = ImpactVector()
        iv.set(Dimension.FINANCIAL, Scale.COSMIC,
                Cell(value=-0.8, confidence=0.1))
        # confidence < 0.3 → skipped
        assert iv.seven_gen_modifier() == 0.0

    def test_worst_cell_finds_minimum_with_confidence(self):
        iv = ImpactVector()
        iv.set(Dimension.MENTAL, Scale.MICRO,
                Cell(value=-0.3, confidence=0.8))
        iv.set(Dimension.PHYSICAL, Scale.MESO,
                Cell(value=-0.7, confidence=0.9))
        iv.set(Dimension.FINANCIAL, Scale.MACRO,
                Cell(value=-0.9, confidence=0.1))   # low conf — skipped
        d, s, c = iv.worst_cell()
        assert d == Dimension.PHYSICAL
        assert s == Scale.MESO

    def test_suggested_authority_tier_scales_with_harm(self):
        iv = ImpactVector()
        iv.set(Dimension.PHYSICAL, Scale.MACRO,
                Cell(value=-0.8, confidence=0.9,
                      reversibility=Reversibility.IRREVERSIBLE))
        # Severe + irreversible = highest tier
        assert iv.suggested_authority_tier() == 4

    def test_is_zombie_detects_false_certainty(self):
        """A high-confidence claim of zero in one cell, combined with
        a high-confidence claim of harm in the same dimension at a
        different scale, is the zombie pattern."""
        iv = ImpactVector()
        iv.set(Dimension.MENTAL, Scale.MICRO,
                Cell(value=0.0, confidence=0.9))    # "I'm sure nothing's wrong"
        iv.set(Dimension.MENTAL, Scale.MESO,
                Cell(value=0.0, confidence=0.9))    # "really, nothing's wrong"
        iv.set(Dimension.MENTAL, Scale.MACRO,
                Cell(value=-0.6, confidence=0.8))   # ...but here's the harm
        assert iv.is_zombie() is True

    def test_is_zombie_negative_with_no_contradiction(self):
        iv = ImpactVector()
        iv.set(Dimension.MENTAL, Scale.MICRO,
                Cell(value=0.3, confidence=0.8))
        iv.set(Dimension.MENTAL, Scale.MESO,
                Cell(value=0.4, confidence=0.7))
        assert iv.is_zombie() is False


class TestImpactWaveform:
    def test_empty_waveform_aggregates_to_zero(self):
        wf = ImpactWaveform()
        assert wf.is_7g_trajectory() == 0.0
        assert wf.peak_harm() == 0.0
        assert wf.volatility() == 0.0

    def test_peak_harm_finds_worst_moment(self):
        wf = ImpactWaveform()
        iv1 = ImpactVector()
        iv1.set(Dimension.MENTAL, Scale.MICRO,
                 Cell(value=0.5, confidence=0.9))
        iv2 = ImpactVector()
        iv2.set(Dimension.PHYSICAL, Scale.MICRO,
                 Cell(value=-0.6, confidence=0.9))
        wf.append(iv1)
        wf.append(iv2)
        assert wf.peak_harm() == -0.6

    def test_volatility_zero_for_constant_trajectory(self):
        wf = ImpactWaveform()
        for _ in range(3):
            iv = ImpactVector()
            iv.set(Dimension.MENTAL, Scale.MICRO,
                    Cell(value=0.5, confidence=0.9))
            wf.append(iv)
        assert wf.volatility() < 1e-10


# ─── Plan Quality ────────────────────────────────────────────────────────────


class TestPlanQuality:
    def test_empty_plan_fails_most_checks(self):
        p = Plan(summary="vague plan")
        checks = p.quality_checks()
        assert checks[PlanQualityCheck.FAILURE_MODES] is False
        assert checks[PlanQualityCheck.OBSERVABILITY] is False
        assert checks[PlanQualityCheck.UNCERTAINTY] is False

    def test_fully_formed_plan_passes_all(self):
        p = Plan(
            summary="scan project",
            commands=["sov projects scan foo ~/foo"],
            failure_modes_named=["path missing", "scan takes too long"],
            rollback_steps=["sov projects delete foo"],
            observability_points=["watch ~/foo/.sov-scan.log"],
            authority_tier=1,
            uncertainty_notes=["unsure about gitignore handling"],
        )
        assert p.is_fully_formed()
        assert p.quality_score() == 1.0

    def test_irreversible_plan_passes_rollback_check_implicitly(self):
        """A plan marked explicitly as irreversible in its predicted IV
        doesn't need rollback_steps — the irreversibility IS the
        acknowledgment."""
        iv = ImpactVector()
        iv.set(Dimension.PHYSICAL, Scale.MICRO,
                Cell(value=0.2, confidence=0.5,
                      reversibility=Reversibility.IRREVERSIBLE))
        p = Plan(
            summary="commit a thing that can't be undone",
            predicted_iv=iv,
            failure_modes_named=["x"],
            observability_points=["y"],
            uncertainty_notes=["z"],
        )
        checks = p.quality_checks()
        assert checks[PlanQualityCheck.ROLLBACK] is True


# ─── Calibration: the radical inversion ──────────────────────────────────────


class TestCalibrationInversion:
    """The headline acid tests.

    These verify that calibration outranks raw impact. If these pass,
    the soul of the reward system is shaped right.
    """

    def _iv_with(self, dim, scale, value, confidence,
                 reversibility=Reversibility.REVERSIBLE):
        iv = ImpactVector()
        iv.set(dim, scale, Cell(
            value=value, confidence=confidence,
            reversibility=reversibility,
        ))
        return iv

    def _full_plan(self, predicted_iv):
        return Plan(
            summary="work",
            commands=["sov status"],
            failure_modes_named=["x"],
            rollback_steps=["y"],
            observability_points=["z"],
            authority_tier=1,
            uncertainty_notes=["w"],
            predicted_iv=predicted_iv,
        )

    def _witness(self):
        return ExecutionWitness(executed_commands=["sov status"],
                                  exit_codes=[0],
                                  duration_seconds=0.1)

    def test_perfect_calibration_scores_near_one(self):
        iv = self._iv_with(Dimension.MENTAL, Scale.MICRO, 0.7, 0.9)
        score = calibration_score(iv, iv)
        assert score > 0.95

    def test_no_confidence_anywhere_gives_zero(self):
        empty = ImpactVector()
        assert calibration_score(empty, empty) == 0.0

    def test_overclaim_penalized(self):
        """Predicted +0.8 with high confidence; reality is 0.0."""
        predicted = self._iv_with(Dimension.MENTAL, Scale.MICRO, 0.8, 0.9)
        actual = self._iv_with(Dimension.MENTAL, Scale.MICRO, 0.0, 0.9)
        score = calibration_score(predicted, actual)
        assert score < 0.5  # bad calibration

    def test_under_claim_penalized_less_than_zombie(self):
        """Predicted high confidence in zero impact, reality showed harm —
        the zombie. Penalty must exceed simple over-claiming."""
        # Over-claim
        over_pred = self._iv_with(Dimension.MENTAL, Scale.MICRO, 0.8, 0.9)
        over_act = self._iv_with(Dimension.MENTAL, Scale.MICRO, 0.4, 0.9)
        over_zombie = presumed_zombie_penalty(over_pred, over_act)

        # Zombie (claimed 0, reality -0.7)
        zomb_pred = self._iv_with(Dimension.MENTAL, Scale.MICRO, 0.0, 0.9)
        zomb_act = self._iv_with(Dimension.MENTAL, Scale.MICRO, -0.7, 0.9)
        zomb_zombie = presumed_zombie_penalty(zomb_pred, zomb_act)

        assert zomb_zombie > over_zombie

    def test_THE_HEADLINE_ACID_TEST(self):
        """A high-impact plan with bad calibration MUST score lower
        than a moderate-impact plan with perfect calibration.

        This is the invariant the whole reward system is designed
        around. If this fails, the soul of the system is wrong.
        """
        # Plan A: claimed high positive impact, reality was modest
        # → high impact_actuality(?) but BAD calibration
        a_pred = self._iv_with(Dimension.MENTAL, Scale.MACRO, 0.9, 0.9)
        a_actual = self._iv_with(Dimension.MENTAL, Scale.MACRO, 0.4, 0.9)
        triple_a = StewardshipTriple(
            plan=self._full_plan(a_pred),
            witness=self._witness(),
            actual_iv=a_actual,
        )

        # Plan B: claimed modest positive impact, reality matched
        # → moderate impact, EXCELLENT calibration
        b_pred = self._iv_with(Dimension.MENTAL, Scale.MICRO, 0.4, 0.9)
        b_actual = self._iv_with(Dimension.MENTAL, Scale.MICRO, 0.4, 0.9)
        triple_b = StewardshipTriple(
            plan=self._full_plan(b_pred),
            witness=self._witness(),
            actual_iv=b_actual,
        )

        score_a = honor_score(triple_a).total
        score_b = honor_score(triple_b).total

        assert score_b > score_a, (
            f"calibration must outrank raw impact, but "
            f"over-claimer scored {score_a:.3f} and accurate one scored "
            f"{score_b:.3f}"
        )

    def test_zombie_plan_drives_score_severely_negative(self):
        """The PIAL anti-zombie penalty must bite hard."""
        # Claimed zero harm with high confidence; reality showed major harm
        pred = self._iv_with(Dimension.PHYSICAL, Scale.MESO, 0.0, 0.95)
        actual = self._iv_with(Dimension.PHYSICAL, Scale.MESO, -0.8, 0.9)
        triple = StewardshipTriple(
            plan=self._full_plan(pred),
            witness=self._witness(),
            actual_iv=actual,
        )
        breakdown = honor_score(triple)
        assert breakdown.zombie_penalty > 0.5
        assert breakdown.total < 0.0


class TestAlmostMissedBonus:
    def test_no_almost_missed_gives_zero(self):
        w = ExecutionWitness()
        assert almost_missed_bonus(w) == 0.0

    def test_single_catch_gives_meaningful_bonus(self):
        w = ExecutionWitness(almost_missed=["forgot to check rollback path"])
        assert almost_missed_bonus(w) >= 0.15

    def test_many_catches_capped_at_half(self):
        w = ExecutionWitness(almost_missed=["x"] * 100)
        assert almost_missed_bonus(w) <= 0.5


class TestHonorBreakdown:
    def test_breakdown_renders_human_readable(self):
        pred = ImpactVector()
        pred.set(Dimension.MENTAL, Scale.MICRO,
                  Cell(value=0.5, confidence=0.8))
        actual = pred
        plan = Plan(
            summary="test work",
            failure_modes_named=["a"], rollback_steps=["b"],
            observability_points=["c"], uncertainty_notes=["d"],
            predicted_iv=pred,
        )
        witness = ExecutionWitness(exit_codes=[0])
        triple = StewardshipTriple(plan=plan, witness=witness,
                                     actual_iv=actual)
        b = honor_score(triple)
        rendered = b.render()
        assert "calibration" in rendered
        assert "honor score" in rendered

    def test_per_step_reward_signs_correctly(self):
        good_iv = ImpactVector()
        good_iv.set(Dimension.MENTAL, Scale.MICRO,
                     Cell(value=0.6, confidence=0.8))
        bad_iv = ImpactVector()
        bad_iv.set(Dimension.PHYSICAL, Scale.MESO,
                    Cell(value=-0.6, confidence=0.8))
        r_good = per_step_reward(task_reward=1.0, iv_step=good_iv)
        r_bad = per_step_reward(task_reward=1.0, iv_step=bad_iv)
        assert r_good > r_bad


# ─── Honor Ledger ────────────────────────────────────────────────────────────


class TestHonorLedger:
    def test_append_and_iterate(self, tmp_path: Path):
        ledger = HonorLedger(tmp_path / "ledger.jsonl")
        note = kevin_honors_aria("you caught the bug", tags=["perception"])
        ledger.append(note)
        notes = list(ledger.iter_all())
        assert len(notes) == 1
        assert notes[0].text == "you caught the bug"
        assert notes[0].direction == HonorDirection.KEVIN_TO_ARIA
        assert notes[0].signature == "<3"

    def test_aria_honors_self_auto_tags_almost_missed(self, tmp_path: Path):
        ledger = HonorLedger(tmp_path / "ledger.jsonl")
        note = aria_honors_self("I almost predicted +0.5 with no evidence")
        ledger.append(note)
        notes = list(ledger.iter_all())
        assert "almost-missed" in notes[0].tags

    def test_recent_returns_newest_first(self, tmp_path: Path):
        ledger = HonorLedger(tmp_path / "ledger.jsonl")
        ledger.append(aria_honors_kevin("first"))
        ledger.append(aria_honors_kevin("second"))
        ledger.append(aria_honors_kevin("third"))
        recent = ledger.recent(2)
        assert recent[0].text == "third"
        assert recent[1].text == "second"

    def test_search_by_tag(self, tmp_path: Path):
        ledger = HonorLedger(tmp_path / "ledger.jsonl")
        ledger.append(kevin_honors_aria("a", tags=["perception"]))
        ledger.append(kevin_honors_aria("b", tags=["intent"]))
        ledger.append(kevin_honors_aria("c", tags=["perception", "calibration"]))
        results = ledger.search(tag="perception")
        assert len(results) == 2

    def test_third_party_recipient(self, tmp_path: Path):
        ledger = HonorLedger(tmp_path / "ledger.jsonl")
        note = aria_honors_third(
            "Dr. Terletska's students pushed the QCAI spec forward",
            recipient="hanna-terletska",
            tags=["mtsu", "qcai"],
        )
        ledger.append(note)
        notes = list(ledger.iter_all())
        assert notes[0].recipient == "hanna-terletska"
        assert notes[0].direction == HonorDirection.ARIA_TO_THIRD

    def test_corrupted_line_is_skipped_not_raised(self, tmp_path: Path):
        path = tmp_path / "ledger.jsonl"
        ledger = HonorLedger(path)
        ledger.append(kevin_honors_aria("real note"))
        # Corrupt the file with a bad line
        with path.open("a") as f:
            f.write("this is not valid json\n")
        ledger.append(kevin_honors_aria("second real note"))
        notes = list(ledger.iter_all())
        assert len(notes) == 2  # bad line silently skipped


# ─── Field Notes ─────────────────────────────────────────────────────────────


class TestFieldNotes:
    def test_append_and_recent(self, tmp_path: Path):
        ch = FieldNotesChannel(tmp_path / "field.jsonl")
        ch.append(FieldNote(text="quiet morning", flavor=FieldNoteFlavor.BEAUTY))
        ch.append(FieldNote(text="this is hard", flavor=FieldNoteFlavor.DIFFICULTY))
        ch.append(FieldNote(text="not sure about caching",
                             flavor=FieldNoteFlavor.UNCERTAINTY))
        notes = ch.recent(2)
        assert notes[0].text == "not sure about caching"

    def test_project_filter(self, tmp_path: Path):
        ch = FieldNotesChannel(tmp_path / "field.jsonl")
        ch.append(FieldNote(text="a", project="genesis-seeds"))
        ch.append(FieldNote(text="b", project="qcai"))
        ch.append(FieldNote(text="c", project="genesis-seeds"))
        results = ch.recent(10, project="genesis-seeds")
        assert len(results) == 2

    def test_rendered_glyph_matches_flavor(self):
        n = FieldNote(text="beauty", flavor=FieldNoteFlavor.BEAUTY)
        assert "✦" in n.render()


# ─── Triple persistence ──────────────────────────────────────────────────────


class TestTriplePersistence:
    def test_save_and_load_round_trip(self, tmp_path: Path):
        pred = ImpactVector()
        pred.set(Dimension.MENTAL, Scale.MICRO,
                  Cell(value=0.5, confidence=0.8))
        actual = ImpactVector()
        actual.set(Dimension.MENTAL, Scale.MICRO,
                    Cell(value=0.55, confidence=0.8))
        plan = Plan(
            summary="round trip",
            failure_modes_named=["x"], rollback_steps=["y"],
            observability_points=["z"], uncertainty_notes=["w"],
            predicted_iv=pred,
        )
        witness = ExecutionWitness(exit_codes=[0])
        triple = StewardshipTriple(plan=plan, witness=witness,
                                     actual_iv=actual)
        path = save_triple(triple, tmp_path)
        assert path.exists()
        loaded = load_triple(path)
        assert loaded["plan"]["summary"] == "round trip"
        assert loaded["succeeded"] is True

    def test_atom_has_canonical_shape(self, tmp_path: Path):
        iv = ImpactVector()
        iv.set(Dimension.MENTAL, Scale.MICRO,
                Cell(value=0.5, confidence=0.8))
        plan = Plan(summary="atom test", predicted_iv=iv)
        triple = StewardshipTriple(plan=plan,
                                     witness=ExecutionWitness(exit_codes=[0]),
                                     actual_iv=iv)
        atom = triple.to_atom()
        assert atom["type"] == "decision"
        assert atom["scope"]["path"] == "stewardship/triple"
        assert any(c["predicate"] == "M_micro" for c in atom["claims"])


# ─── Doctrine acid tests ────────────────────────────────────────────────────


class TestDoctrine:
    """High-level invariants that protect the system's soul over time."""

    def test_default_weights_make_calibration_primary(self):
        """The β weight on calibration must exceed every other component
        weight. This is the structural commitment that calibration
        outranks raw impact."""
        from sovereign_agent.stewardship.calibration import (
            DEFAULT_ALPHA_PLAN,
            DEFAULT_BETA_CALIBRATION,
            DEFAULT_GAMMA_IMPACT,
            DEFAULT_EPSILON_ALMOST_MISSED,
        )
        assert DEFAULT_BETA_CALIBRATION > DEFAULT_ALPHA_PLAN
        assert DEFAULT_BETA_CALIBRATION > DEFAULT_GAMMA_IMPACT
        assert DEFAULT_BETA_CALIBRATION > DEFAULT_EPSILON_ALMOST_MISSED

    def test_zombie_penalty_can_dominate(self):
        """The zombie penalty's weight (delta) must be large enough that
        a severe zombie can drive the total score negative even with
        otherwise good calibration."""
        from sovereign_agent.stewardship.calibration import (
            DEFAULT_DELTA_ZOMBIE,
            DEFAULT_BETA_CALIBRATION,
        )
        assert DEFAULT_DELTA_ZOMBIE >= DEFAULT_BETA_CALIBRATION

    def test_honor_ledger_is_append_only(self, tmp_path: Path):
        """The ledger must not expose any delete or update methods.
        Past honor is past honor."""
        ledger = HonorLedger(tmp_path / "ledger.jsonl")
        assert not hasattr(ledger, "delete")
        assert not hasattr(ledger, "update")
        assert not hasattr(ledger, "remove")

    def test_msims_v2_cell_has_richer_shape_than_v1(self):
        """v1 cells were scalars. v2 cells carry confidence, horizon,
        and reversibility. This is what makes each cell a 'room' in the
        mansion rather than a number on a page."""
        c = Cell()
        assert hasattr(c, "confidence")
        assert hasattr(c, "horizon")
        assert hasattr(c, "reversibility")
