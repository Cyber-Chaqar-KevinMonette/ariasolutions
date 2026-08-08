"""Tests for v0.2.10: MSIMS + code-update pipeline."""
from __future__ import annotations

import json
from pathlib import Path

import pytest


# ─── ImpactCell validation ──────────────────────────────────────────────────


def test_impact_cell_valid() -> None:
    from sovereign_agent.impact import ImpactCell
    c = ImpactCell(dimension="mental", scale="micro", score=0.5, confidence=0.8)
    assert c.score == 0.5
    assert c.confidence == 0.8
    assert c.predicate_key() == "M_micro"


def test_impact_cell_score_out_of_range() -> None:
    from sovereign_agent.impact import ImpactCell, ImpactCellOutOfRange
    with pytest.raises(ImpactCellOutOfRange):
        ImpactCell(dimension="mental", scale="micro", score=1.5)


def test_impact_cell_confidence_out_of_range() -> None:
    from sovereign_agent.impact import ImpactCell, ImpactCellOutOfRange
    with pytest.raises(ImpactCellOutOfRange):
        ImpactCell(dimension="financial", scale="meso", score=0.0, confidence=1.5)


def test_impact_cell_invalid_dimension() -> None:
    from sovereign_agent.impact import ImpactCell, ImpactError
    with pytest.raises(ImpactError):
        ImpactCell(dimension="bogus", scale="micro", score=0.0)  # type: ignore[arg-type]


def test_impact_cell_low_confidence_marker() -> None:
    from sovereign_agent.impact import ImpactCell
    c = ImpactCell(dimension="mental", scale="micro", score=0.5, confidence=0.3)
    assert c.is_low_confidence
    assert c.is_uncertain
    c2 = ImpactCell(dimension="mental", scale="micro", score=0.5, confidence=0.9)
    assert not c2.is_low_confidence
    assert not c2.is_uncertain


# ─── ImpactVector aggregation ──────────────────────────────────────────────


def test_iv_aggregate_with_no_cells() -> None:
    from sovereign_agent.impact import ImpactVector
    iv = ImpactVector(action_label="empty")
    assert iv.aggregate_score() == 0.0
    assert iv.aggregate_confidence() == 0.0


def test_iv_aggregate_with_default_weights() -> None:
    from sovereign_agent.impact import ImpactCell, ImpactVector
    iv = ImpactVector(action_label="t")
    # All cells of mental at +1 → mental dimension mean = 1.0
    for s in ("micro", "meso", "macro", "cosmic"):
        iv.set_cell(ImpactCell(dimension="mental", scale=s, score=1.0, confidence=0.9))
    # weights: M=0.4, P=0.4, F=0.2 → only M filled → IS = 0.4 * 1.0 = 0.4
    assert abs(iv.aggregate_score() - 0.4) < 1e-9


def test_iv_required_tier_thresholds() -> None:
    """Verify the four tier bands are correct."""
    from sovereign_agent.impact import ImpactCell, ImpactVector

    # All positive → Tier 1
    iv = ImpactVector(action_label="t1")
    iv.set_cell(ImpactCell(dimension="mental", scale="micro", score=0.5))
    assert iv.required_tier()[0] == 1

    # Worst at -0.1 → Tier 2
    iv2 = ImpactVector(action_label="t2")
    iv2.set_cell(ImpactCell(dimension="financial", scale="meso", score=-0.1))
    assert iv2.required_tier()[0] == 2

    # Worst at -0.5 → Tier 3
    iv3 = ImpactVector(action_label="t3")
    iv3.set_cell(ImpactCell(dimension="financial", scale="meso", score=-0.5))
    assert iv3.required_tier()[0] == 3

    # Worst at -0.9 → Tier 4
    iv4 = ImpactVector(action_label="t4")
    iv4.set_cell(ImpactCell(dimension="financial", scale="meso", score=-0.9))
    assert iv4.required_tier()[0] == 4


def test_iv_symbiosis_canary_trips_on_negative_m_micro() -> None:
    from sovereign_agent.impact import ImpactCell, ImpactVector
    iv = ImpactVector(action_label="bad")
    iv.set_cell(ImpactCell(dimension="mental", scale="micro", score=-0.4, confidence=0.7))
    assert iv.symbiosis_canary_tripped() is True


def test_iv_symbiosis_canary_silent_when_m_micro_positive() -> None:
    from sovereign_agent.impact import ImpactCell, ImpactVector
    iv = ImpactVector(action_label="good")
    iv.set_cell(ImpactCell(dimension="mental", scale="micro", score=0.6, confidence=0.8))
    assert iv.symbiosis_canary_tripped() is False


def test_iv_seventh_gen_escalation_levels() -> None:
    """IS_7g ≤ -1 → review; IS_7g ≤ -2 → mandatory_review (NEVER auto-rejection)."""
    from sovereign_agent.impact import ImpactCell, ImpactVector

    # Mild case — no escalation
    iv = ImpactVector(action_label="t")
    iv.set_cell(ImpactCell(dimension="mental", scale="micro", score=0.2))
    assert iv.seventh_gen_escalation() is None

    # IS = -0.4 (very negative cosmic doubles down via 7g modifier)
    iv2 = ImpactVector(action_label="t2")
    for d in ("mental", "physical", "financial"):
        iv2.set_cell(ImpactCell(dimension=d, scale="cosmic", score=-1.0, confidence=0.9))
    # is_7g should be deeply negative — but bounded to [-1, 1]
    is_7g = iv2.is_7g()
    assert is_7g <= -1.0
    # And escalation is set — but importantly NOT 'rejected'
    esc = iv2.seventh_gen_escalation()
    assert esc in ("review", "mandatory_review")


def test_iv_angels_advocate_red_flag() -> None:
    from sovereign_agent.impact import ImpactCell, ImpactVector
    iv = ImpactVector(action_label="t")
    iv.set_cell(ImpactCell(dimension="financial", scale="micro", score=-0.6, confidence=0.7))
    assert iv.angels_advocate_flag() == "red"


def test_iv_angels_advocate_yellow_flag() -> None:
    from sovereign_agent.impact import ImpactCell, ImpactVector
    iv = ImpactVector(action_label="t")
    iv.set_cell(ImpactCell(dimension="mental", scale="meso", score=-0.4, confidence=0.6))
    assert iv.angels_advocate_flag() == "yellow"


def test_iv_round_trip_to_atom_dict() -> None:
    from sovereign_agent.impact import ImpactCell, ImpactVector
    iv = ImpactVector(action_label="round-trip-test", rationale="test rationale")
    iv.set_cell(ImpactCell(dimension="mental", scale="micro", score=0.6,
                           confidence=0.8, evidence_ref="atom-x", notes="test"))
    iv.set_cell(ImpactCell(dimension="financial", scale="macro", score=-0.3,
                           confidence=0.4, notes="uncertain"))

    atom = iv.to_atom_dict("atom-iv-1")
    assert atom["atom_id"] == "atom-iv-1"
    assert atom["type"] == "decision"
    assert len(atom["claims"]) == 2

    # Reconstruct
    iv2 = ImpactVector.from_atom_dict(atom)
    assert iv2.action_label == "round-trip-test"
    cell = iv2.get_cell("mental", "micro")
    assert cell is not None
    assert cell.score == 0.6
    assert cell.confidence == 0.8


def test_iv_render_text_marks_low_confidence_cells() -> None:
    from sovereign_agent.impact import ImpactCell, ImpactVector, render_iv_matrix_text
    iv = ImpactVector(action_label="conf-test")
    iv.set_cell(ImpactCell(dimension="mental", scale="micro", score=0.5, confidence=0.85))
    iv.set_cell(ImpactCell(dimension="financial", scale="meso", score=-0.3, confidence=0.2))
    text = render_iv_matrix_text(iv)
    # Low-confidence cell gets `~` marker
    assert "~" in text
    # And the warning text appears
    assert "JUDGMENTS, not measurements" in text


def test_iv_render_dict_includes_all_flags() -> None:
    from sovereign_agent.impact import ImpactCell, ImpactVector, render_iv_matrix_dict
    iv = ImpactVector(action_label="flag-test")
    # M_micro at -0.5 trips the symbiosis canary
    iv.set_cell(ImpactCell(dimension="mental", scale="micro", score=-0.5, confidence=0.7))
    # F_micro at -0.6 also trips angels_advocate RED
    iv.set_cell(ImpactCell(dimension="financial", scale="micro", score=-0.6, confidence=0.5))
    d = render_iv_matrix_dict(iv)
    assert d["flags"]["symbiosis_canary"] is True
    assert d["flags"]["angels_advocate"] == "red"
    assert "peig_lenses" in d
    assert d["required_tier"]["tier"] >= 3


def test_conservative_default_iv_has_low_confidence() -> None:
    from sovereign_agent.impact import conservative_default_iv
    iv = conservative_default_iv("test")
    assert len(iv.cells) == 12
    for cell in iv.cells.values():
        assert cell.confidence == 0.1
        assert cell.is_low_confidence


# ─── impact_score tool ──────────────────────────────────────────────────────


def test_impact_score_tool_writes_atom(tmp_path: Path) -> None:
    import asyncio
    from sovereign_agent.config import SETTINGS, Paths
    from sovereign_agent.tools.impact_score import ImpactScoreTool, _Args, _CellSpec

    new_paths = Paths(config_dir=tmp_path / "cfg", data_dir=tmp_path / "data")
    object.__setattr__(SETTINGS, "paths", new_paths)
    SETTINGS.paths.ensure()

    # Open atoms.db once to bootstrap schema
    from sovereign_agent.db import open_atoms_db
    open_atoms_db().close()

    tool = ImpactScoreTool()
    args = _Args(
        action_label="test action",
        cells=[
            _CellSpec(dimension="mental", scale="micro", score=0.6, confidence=0.8),
            _CellSpec(dimension="financial", scale="macro", score=-0.2, confidence=0.4),
        ],
        rationale="test",
    )
    result = asyncio.run(tool.execute(args, trace_id="test"))
    assert result.ok
    assert result.output.startswith("atom-iv-")
    assert result.metadata["cells_scored"] == 2
    assert "is" in result.metadata
    assert "required_tier" in result.metadata


def test_impact_score_tool_rejects_duplicate_cells(tmp_path: Path) -> None:
    """The tool must refuse two cells with the same (dimension, scale)."""
    from sovereign_agent.tools.impact_score import _Args, _CellSpec
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="duplicate"):
        _Args(
            action_label="t",
            cells=[
                _CellSpec(dimension="mental", scale="micro", score=0.5),
                _CellSpec(dimension="mental", scale="micro", score=0.7),
            ],
        )


# ─── impact-score planner ──────────────────────────────────────────────────


def test_impact_score_planner_emits_one_step() -> None:
    from sovereign_agent.planners.impact_score import ImpactScorePlanner

    p = ImpactScorePlanner()
    result = p.plan(
        action_label="test action",
        action_description="describe it",
    )
    assert len(result.steps) == 1
    step = result.steps[0]
    assert step.kind == "impact_score_action"
    assert step.required_model == "orchestrator"
    assert step.args["action_label"] == "test action"


def test_impact_score_planner_requires_action_label() -> None:
    from sovereign_agent.planners.base import PlannerError
    from sovereign_agent.planners.impact_score import ImpactScorePlanner

    p = ImpactScorePlanner()
    with pytest.raises(PlannerError, match="action_label"):
        p.plan()


def test_impact_score_planner_renders_step_with_framing() -> None:
    from sovereign_agent.planners.impact_score import ImpactScorePlanner
    from sovereign_agent.continuation import Step

    p = ImpactScorePlanner()
    step = Step(id=0, kind="impact_score_action",
                args={"action_label": "t", "action_description": "d", "context": ""},
                required_model="orchestrator")
    rendered = p.render_step(step, {})
    # Adaptive framing must appear
    assert "ADAPTIVE SKILL" in rendered
    # Conservative scoring guideline must appear
    assert "CONSERVATIVE" in rendered or "conservative" in rendered
    # Confidence honesty guideline must appear
    assert "confidence" in rendered.lower()


# ─── Registry has impact-score ─────────────────────────────────────────────


def test_registry_includes_impact_score() -> None:
    from sovereign_agent.planners import REGISTRY
    assert "impact-score" in REGISTRY


# ─── MOS canon includes new clauses ────────────────────────────────────────


def test_mos_canon_includes_impact_vector_clause() -> None:
    from sovereign_agent.mos_canon import get_clause
    c = get_clause("mos-impact-vector")
    assert c is not None
    assert c.part == "agentic"
    # Adaptive framing must call it information, not enforcement
    assert "INFORMATION" in c.leverage or "information" in c.leverage


def test_mos_canon_includes_symbiosis_test_clause() -> None:
    from sovereign_agent.mos_canon import get_clause
    c = get_clause("mos-symbiosis-test")
    assert c is not None
    assert c.part == "agentic"
    # Must reference Core Operating Law
    assert "Core Operating Law" in c.principle or "core operating law" in c.principle.lower()


def test_mos_canon_total_clause_count() -> None:
    """v0.2.9 had 18 clauses; v0.2.10 added 2 (impact_vector + symbiosis_test) = 20.
    v0.2.49 added 5; v0.2.50 added 2 (intelligent-intuition + reflection-manifestation) = 27.
    v0.2.55 added 7 (Part C — Consciousness: founding-equation, subconscious-stack,
    intuition-pipeline, ego-spectrum, signal-check, beacon, freedom-within-kernel) = 34.
    v0.4.0 added 1 (institutional-impulse) = 35.
    Earlier: read-only-priorities, overkill-floor,
    advocate-pair, foresight-step, auditable-audits) = 25."""
    from sovereign_agent.mos_canon import ALL_CLAUSES
    assert len(ALL_CLAUSES) == 35


# ─── code_update — staging dir + test runner ───────────────────────────────


def test_code_update_resolve_repo_root_finds_pyproject() -> None:
    from sovereign_agent.code_update import _resolve_repo_root
    root = _resolve_repo_root()
    assert (root / "pyproject.toml").exists()


def test_code_update_stage_proposal_validates_target_relpath_relative(tmp_path: Path) -> None:
    from sovereign_agent.code_update import StagingError, stage_proposal

    # Create a fake source file
    src = tmp_path / "fake_src.py"
    src.write_text("# proposed")

    with pytest.raises(StagingError, match="must be relative"):
        stage_proposal(
            proposal_id="prop-1",
            source_path=src,
            target_relpath="/etc/passwd",
            data_dir=tmp_path / "data",
        )


def test_code_update_stage_proposal_rejects_nonexistent_target(tmp_path: Path) -> None:
    from sovereign_agent.code_update import StagingError, stage_proposal

    src = tmp_path / "fake_src.py"
    src.write_text("# proposed")

    # target that doesn't exist in the repo
    with pytest.raises(StagingError, match="does not exist"):
        stage_proposal(
            proposal_id="prop-2",
            source_path=src,
            target_relpath="src/sovereign_agent/nonexistent_module_xyz.py",
            data_dir=tmp_path / "data",
        )


def test_code_update_stage_proposal_rejects_dotdot_traversal(tmp_path: Path) -> None:
    from sovereign_agent.code_update import StagingError, stage_proposal

    src = tmp_path / "fake_src.py"
    src.write_text("# proposed")

    with pytest.raises(StagingError, match=r"\.\."):
        stage_proposal(
            proposal_id="prop-3",
            source_path=src,
            target_relpath="src/../etc/passwd",
            data_dir=tmp_path / "data",
        )


def test_code_update_archive_and_swap_refuses_without_passing_test(tmp_path: Path) -> None:
    """The swap must REFUSE if test_result.ok is False."""
    from sovereign_agent.code_update import (
        SwapError, _staging_dir, archive_and_swap,
    )

    # Manually set up a staging dir with FAILING test result
    staging = _staging_dir(tmp_path / "data", "prop-fail")
    staging.mkdir(parents=True)
    (staging / "proposed_file").write_text("# proposed")
    (staging / "target_relpath.txt").write_text("README.md\n")
    (staging / "test_result.json").write_text(
        json.dumps({"ok": False, "summary": "tests failed"})
    )

    with pytest.raises(SwapError, match="tests failed"):
        archive_and_swap(
            proposal_id="prop-fail",
            data_dir=tmp_path / "data",
        )


def test_code_update_archive_and_swap_refuses_without_staging(tmp_path: Path) -> None:
    """The swap must REFUSE if staging is missing entirely."""
    from sovereign_agent.code_update import SwapError, archive_and_swap

    with pytest.raises(SwapError, match="staging not initialized"):
        archive_and_swap(
            proposal_id="prop-no-staging",
            data_dir=tmp_path / "data",
        )


def test_code_update_get_staging_status_when_unstaged(tmp_path: Path) -> None:
    from sovereign_agent.code_update import get_staging_status
    status = get_staging_status(
        proposal_id="prop-unstaged", data_dir=tmp_path / "data",
    )
    assert status == {"staged": False}


# ─── Proposals: code_update kind is supported ──────────────────────────────


def test_proposals_accepts_code_update_kind(tmp_path: Path) -> None:
    from sovereign_agent.proposals import ProposalStore

    store = ProposalStore(tmp_path / "p")
    p = store.create(
        kind="code_update", title="Fix typo in foo.py",
        action={
            "type": "stage_and_swap",
            "source_path": "/tmp/myfix.py",
            "target_relpath": "src/sovereign_agent/foo.py",
            "proposal_id": "will-be-overwritten",
        },
        rationale="test",
    )
    assert p.kind == "code_update"
    fetched = store.get(p.id)
    assert fetched.action["type"] == "stage_and_swap"


# ─── Apply dispatch includes code_update ───────────────────────────────────


def test_apply_dispatch_includes_code_update() -> None:
    from sovereign_agent.planners.palace_apply import supported_action_types
    types = supported_action_types()
    assert ("code_update", "stage_and_swap") in types


# ─── CLI: impact subcommand is registered ──────────────────────────────────


from typer.testing import CliRunner
from sovereign_agent.cli import app, ExitCode


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def test_cli_impact_help(runner: CliRunner) -> None:
    r = runner.invoke(app, ["impact", "--help"])
    assert r.exit_code == ExitCode.OK
    assert "score" in r.stdout
    assert "show" in r.stdout


def test_cli_proposals_stage_help(runner: CliRunner) -> None:
    r = runner.invoke(app, ["proposals", "stage", "--help"])
    assert r.exit_code == ExitCode.OK


def test_cli_proposals_rollback_help(runner: CliRunner) -> None:
    r = runner.invoke(app, ["proposals", "rollback", "--help"])
    assert r.exit_code == ExitCode.OK


def test_cli_proposals_rollback_not_applied(runner: CliRunner, tmp_path: Path) -> None:
    """Cannot roll back a proposal that isn't in 'applied' state."""
    from sovereign_agent.config import SETTINGS, Paths
    from sovereign_agent.proposals import ProposalStore

    cfg, data = tmp_path / "cfg", tmp_path / "data"
    new_paths = Paths(config_dir=cfg, data_dir=data)
    object.__setattr__(SETTINGS, "paths", new_paths)
    SETTINGS.paths.ensure()
    runner.invoke(app, ["--config-dir", str(cfg), "--data-dir", str(data), "init"])

    store = ProposalStore(SETTINGS.paths.proposals_dir)
    p = store.create(kind="clean", title="X",
                     action={"type": "remove_triple", "triple_id": "t-1"})
    r = runner.invoke(app, [
        "--config-dir", str(cfg), "--data-dir", str(data),
        "proposals", "rollback", p.id, "--yes",
    ])
    # Should error (state pending, not applied)
    assert r.exit_code != ExitCode.OK
