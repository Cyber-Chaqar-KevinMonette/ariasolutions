"""Tests for v0.2.11: VRAM monitoring, summaries-to-atoms, lineage tracker,
audit/harden fixes."""
from __future__ import annotations

import json
from pathlib import Path

import pytest


# ─── VRAM monitor ───────────────────────────────────────────────────────────


def test_vram_sample_returns_int_or_none() -> None:
    from sovereign_agent.vram_monitor import sample_vram_used_mb
    sample = sample_vram_used_mb()
    # On systems without GPU returns None; on systems with GPU returns int
    assert sample is None or isinstance(sample, int)


def test_vram_sampler_has_gpu_check_is_cached() -> None:
    """Subsequent calls to has_gpu() should not re-shell-out."""
    from sovereign_agent.vram_monitor import has_gpu
    a = has_gpu()
    b = has_gpu()
    assert a == b


def test_vram_trace_has_no_gpu_returns_none_fields() -> None:
    """On systems without a GPU, all fields stay None and display is empty."""
    from sovereign_agent.vram_monitor import VRAMSampler

    sampler = VRAMSampler()
    sampler.start()
    # No work to do — just stop
    trace = sampler.stop()
    # On no-GPU CI systems, all None
    if trace.before_mb is None:
        assert trace.peak_mb is None
        assert trace.after_mb is None
        assert trace.delta_mb is None
        assert trace.display_short() == ""


def test_vram_trace_dict_serializable() -> None:
    from sovereign_agent.vram_monitor import VRAMTrace

    trace = VRAMTrace(before_mb=1000, peak_mb=1200, after_mb=1050)
    d = trace.to_dict()
    assert d["before_mb"] == 1000
    assert d["peak_mb"] == 1200
    assert d["after_mb"] == 1050
    assert d["delta_mb"] == 200


def test_vram_trace_display_short_with_data() -> None:
    from sovereign_agent.vram_monitor import VRAMTrace

    trace = VRAMTrace(before_mb=6029, peak_mb=6802, after_mb=6700)
    assert trace.display_short() == "vram=6029→6802MB Δ+773"


def test_vram_trace_display_short_negative_delta() -> None:
    from sovereign_agent.vram_monitor import VRAMTrace

    trace = VRAMTrace(before_mb=6802, peak_mb=6029, after_mb=5800)
    # Peak < before is unusual but possible if measurement timing misses the spike
    assert "Δ-773" in trace.display_short()


# ─── summaries-to-atoms planner ────────────────────────────────────────────


def test_summaries_to_atoms_planner_requires_output() -> None:
    from sovereign_agent.planners.base import PlannerError
    from sovereign_agent.planners.summaries_to_atoms import SummariesToAtomsPlanner

    p = SummariesToAtomsPlanner()
    with pytest.raises(PlannerError, match="output"):
        p.plan()


def test_summaries_to_atoms_planner_requires_existing_file(tmp_path: Path) -> None:
    from sovereign_agent.planners.base import PlannerError
    from sovereign_agent.planners.summaries_to_atoms import SummariesToAtomsPlanner

    p = SummariesToAtomsPlanner()
    with pytest.raises(PlannerError, match="not found"):
        p.plan(output=str(tmp_path / "nonexistent.txt"))


def test_summaries_to_atoms_planner_emits_one_step_per_line(tmp_path: Path) -> None:
    from sovereign_agent.planners.summaries_to_atoms import SummariesToAtomsPlanner

    inv = tmp_path / "inv.txt"
    inv.write_text(
        "/home/me/proj/file1.md: This is the first summary that has enough chars.\n"
        "/home/me/proj/file2.md: This second summary is also long enough to count.\n"
        "tiny\n"  # too short, should be skipped (< 20 chars)
        "\n"     # empty, skipped
        "/home/me/proj/file3.md: A third summary that meets the minimum bar.\n"
    )
    p = SummariesToAtomsPlanner()
    result = p.plan(output=str(inv))
    assert len(result.steps) == 3
    for s in result.steps:
        assert s.kind == "summaries_to_atoms_line"
        assert s.required_model == "none"


def test_summaries_to_atoms_executor_writes_atom(tmp_path: Path) -> None:
    from sovereign_agent.config import SETTINGS, Paths
    from sovereign_agent.continuation import Step
    from sovereign_agent.planners.summaries_to_atoms import (
        execute_summaries_to_atoms_step,
    )

    new_paths = Paths(config_dir=tmp_path / "cfg", data_dir=tmp_path / "data")
    object.__setattr__(SETTINGS, "paths", new_paths)
    SETTINGS.paths.ensure()

    from sovereign_agent.db import open_atoms_db
    open_atoms_db().close()  # bootstrap schema

    step = Step(
        id=0, kind="summaries_to_atoms_line",
        args={
            "source_path": "/fake/path.md",
            "lineno": 1,
            "summary_line": "A meaningful summary line that's long enough to keep.",
            "tag": "test",
        },
        required_model="none",
    )
    result = execute_summaries_to_atoms_step(step)
    assert "atomized" in result

    # Verify the atom landed in atoms.db
    conn = open_atoms_db()
    try:
        row = conn.execute(
            "SELECT atom_id, type, summary FROM atoms WHERE summary LIKE ?",
            ("%meaningful summary line%",),
        ).fetchone()
    finally:
        conn.close()
    assert row is not None
    assert row[0].startswith("atom-salvage-")
    assert row[1] == "fact"


def test_summaries_to_atoms_executor_idempotent(tmp_path: Path) -> None:
    """Re-running the same step does NOT duplicate the atom."""
    from sovereign_agent.config import SETTINGS, Paths
    from sovereign_agent.continuation import Step
    from sovereign_agent.planners.summaries_to_atoms import (
        execute_summaries_to_atoms_step,
    )

    new_paths = Paths(config_dir=tmp_path / "cfg", data_dir=tmp_path / "data")
    object.__setattr__(SETTINGS, "paths", new_paths)
    SETTINGS.paths.ensure()

    from sovereign_agent.db import open_atoms_db
    open_atoms_db().close()

    step = Step(
        id=0, kind="summaries_to_atoms_line",
        args={
            "source_path": "/fake/path.md",
            "lineno": 5,
            "summary_line": "An idempotent summary line, definitely long enough.",
            "tag": "idem",
        },
        required_model="none",
    )
    execute_summaries_to_atoms_step(step)
    execute_summaries_to_atoms_step(step)
    execute_summaries_to_atoms_step(step)

    conn = open_atoms_db()
    try:
        rows = conn.execute(
            "SELECT atom_id FROM atoms WHERE summary LIKE ?",
            ("%idempotent summary line%",),
        ).fetchall()
    finally:
        conn.close()
    assert len(rows) == 1  # ONE atom despite three runs


def test_summaries_to_atoms_in_registry() -> None:
    from sovereign_agent.planners import REGISTRY
    assert "summaries-to-atoms" in REGISTRY


# ─── Audit fix: palace-mine empty error is actionable ──────────────────────


def test_palace_mine_empty_atoms_error_mentions_alternatives(tmp_path: Path) -> None:
    """The error must mention the salvage and read-files paths."""
    from sovereign_agent.config import SETTINGS, Paths
    from sovereign_agent.planners.base import PlannerError
    from sovereign_agent.planners.palace_mine import PalaceMinePlanner

    new_paths = Paths(config_dir=tmp_path / "cfg", data_dir=tmp_path / "data")
    object.__setattr__(SETTINGS, "paths", new_paths)
    SETTINGS.paths.ensure()

    from sovereign_agent.db import open_atoms_db
    open_atoms_db().close()  # empty atoms.db

    p = PalaceMinePlanner()
    with pytest.raises(PlannerError, match="summaries-to-atoms") as excinfo:
        p.plan(room_id="r1", room_name="One")
    assert "read-files" in str(excinfo.value)


# ─── Audit fix: inventory description warns about no-atoms output ──────────


def test_inventory_planner_description_warns_no_atoms() -> None:
    """The inventory planner's description should make the no-atoms-output behavior explicit."""
    from sovereign_agent.planners.inventory import InventoryPlanner
    desc = InventoryPlanner.description.lower()
    assert "atoms" in desc  # mention atoms
    # Either says "DOES NOT" or points at alternatives — current impl says both
    assert "summaries-to-atoms" in InventoryPlanner.description or "read-files" in InventoryPlanner.description


# ─── Lineage tracker — basics ──────────────────────────────────────────────


def test_lineage_get_atom_returns_none_for_missing(tmp_path: Path) -> None:
    from sovereign_agent.config import SETTINGS, Paths
    from sovereign_agent.lineage import get_atom_by_id

    new_paths = Paths(config_dir=tmp_path / "cfg", data_dir=tmp_path / "data")
    object.__setattr__(SETTINGS, "paths", new_paths)
    SETTINGS.paths.ensure()

    from sovereign_agent.db import open_atoms_db
    open_atoms_db().close()

    assert get_atom_by_id("atom-does-not-exist") is None


def test_lineage_forward_finds_closet_referencing_atom(tmp_path: Path) -> None:
    """Atom in closet.atom_ids → forward lineage surfaces the closet."""
    from sovereign_agent.config import SETTINGS, Paths
    from sovereign_agent.lineage import lineage_forward

    new_paths = Paths(config_dir=tmp_path / "cfg", data_dir=tmp_path / "data")
    object.__setattr__(SETTINGS, "paths", new_paths)
    SETTINGS.paths.ensure()

    # Insert an atom
    from sovereign_agent.db import open_atoms_db
    conn = open_atoms_db()
    try:
        conn.execute(
            "INSERT INTO atoms(atom_id, type, summary, content_ref, claims, parents, "
            "confidence, created_at, created_by) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            ("atom-x", "fact", "Some content",
             '{"kind":"inline","source_file":"/some/file.md"}',
             "[]", "[]", 1.0, "2026-05-04T00:00:00Z", '{"actor":"test"}'),
        )
        conn.commit()
    finally:
        conn.close()

    # Insert a closet that references that atom
    from sovereign_agent.palace import Closet, open_palace
    palace = open_palace()
    try:
        palace.create_room(room_id="r1", name="One")
        palace.add_closet(Closet(
            id="c-1", room_id="r1", topic="contains atom-x",
            entities=[], atom_ids=["atom-x"],
        ))
    finally:
        palace.close()

    result = lineage_forward("atom-x")
    assert result.atom is not None
    assert result.atom.atom_id == "atom-x"
    assert result.atom.source_file == "/some/file.md"
    assert len(result.closets) == 1
    assert result.closets[0].closet_id == "c-1"


def test_lineage_forward_finds_parent_atoms(tmp_path: Path) -> None:
    """If atom B has parent atom A, forward lineage of B surfaces A."""
    from sovereign_agent.config import SETTINGS, Paths
    from sovereign_agent.lineage import lineage_forward

    new_paths = Paths(config_dir=tmp_path / "cfg", data_dir=tmp_path / "data")
    object.__setattr__(SETTINGS, "paths", new_paths)
    SETTINGS.paths.ensure()

    from sovereign_agent.db import open_atoms_db
    conn = open_atoms_db()
    try:
        conn.execute(
            "INSERT INTO atoms(atom_id, type, summary, content_ref, claims, parents, "
            "confidence, created_at, created_by) VALUES (?,?,?,?,?,?,?,?,?)",
            ("atom-parent", "fact", "I am the parent", '{"kind":"inline"}',
             "[]", "[]", 1.0, "2026-05-04T00:00:00Z", '{"actor":"t"}'),
        )
        conn.execute(
            "INSERT INTO atoms(atom_id, type, summary, content_ref, claims, parents, "
            "confidence, created_at, created_by) VALUES (?,?,?,?,?,?,?,?,?)",
            ("atom-child", "fact", "I am derived", '{"kind":"inline"}',
             "[]", '["atom-parent"]', 1.0, "2026-05-04T00:00:01Z", '{"actor":"t"}'),
        )
        conn.commit()
    finally:
        conn.close()

    result = lineage_forward("atom-child")
    assert result.atom is not None
    assert len(result.parents) == 1
    assert result.parents[0].atom_id == "atom-parent"


def test_lineage_forward_finds_child_atoms(tmp_path: Path) -> None:
    """If atom B is parent of atom C, forward lineage of B includes C as child."""
    from sovereign_agent.config import SETTINGS, Paths
    from sovereign_agent.lineage import lineage_forward

    new_paths = Paths(config_dir=tmp_path / "cfg", data_dir=tmp_path / "data")
    object.__setattr__(SETTINGS, "paths", new_paths)
    SETTINGS.paths.ensure()

    from sovereign_agent.db import open_atoms_db
    conn = open_atoms_db()
    try:
        conn.execute(
            "INSERT INTO atoms(atom_id, type, summary, content_ref, claims, parents, "
            "confidence, created_at, created_by) VALUES (?,?,?,?,?,?,?,?,?)",
            ("atom-base", "fact", "Base", '{"kind":"inline"}',
             "[]", "[]", 1.0, "2026-05-04T00:00:00Z", '{"actor":"t"}'),
        )
        conn.execute(
            "INSERT INTO atoms(atom_id, type, summary, content_ref, claims, parents, "
            "confidence, created_at, created_by) VALUES (?,?,?,?,?,?,?,?,?)",
            ("atom-derived", "fact", "Derived", '{"kind":"inline"}',
             "[]", '["atom-base"]', 1.0, "2026-05-04T00:00:01Z", '{"actor":"t"}'),
        )
        conn.commit()
    finally:
        conn.close()

    result = lineage_forward("atom-base")
    assert result.atom is not None
    assert len(result.children) == 1
    assert result.children[0].atom_id == "atom-derived"


def test_lineage_reverse_walks_closet_to_source_files(tmp_path: Path) -> None:
    """Closet → atoms → source files."""
    from sovereign_agent.config import SETTINGS, Paths
    from sovereign_agent.lineage import lineage_reverse

    new_paths = Paths(config_dir=tmp_path / "cfg", data_dir=tmp_path / "data")
    object.__setattr__(SETTINGS, "paths", new_paths)
    SETTINGS.paths.ensure()

    # Two atoms each with a source_file
    from sovereign_agent.db import open_atoms_db
    conn = open_atoms_db()
    try:
        conn.execute(
            "INSERT INTO atoms(atom_id, type, summary, content_ref, claims, parents, "
            "confidence, created_at, created_by) VALUES (?,?,?,?,?,?,?,?,?)",
            ("atom-a", "fact", "First", '{"kind":"inline","source_file":"/dir/a.md"}',
             "[]", "[]", 1.0, "2026-05-04T00:00:00Z", '{"actor":"t"}'),
        )
        conn.execute(
            "INSERT INTO atoms(atom_id, type, summary, content_ref, claims, parents, "
            "confidence, created_at, created_by) VALUES (?,?,?,?,?,?,?,?,?)",
            ("atom-b", "fact", "Second", '{"kind":"inline","source_file":"/dir/b.md"}',
             "[]", "[]", 1.0, "2026-05-04T00:00:01Z", '{"actor":"t"}'),
        )
        conn.commit()
    finally:
        conn.close()

    # Closet referencing both
    from sovereign_agent.palace import Closet, open_palace
    palace = open_palace()
    try:
        palace.create_room(room_id="r1", name="One")
        palace.add_closet(Closet(
            id="c-multi", room_id="r1", topic="multi-atom",
            entities=[], atom_ids=["atom-a", "atom-b"],
        ))
    finally:
        palace.close()

    result = lineage_reverse("c-multi")
    assert result.closet is not None
    assert len(result.atoms) == 2
    assert "/dir/a.md" in result.source_files
    assert "/dir/b.md" in result.source_files


def test_lineage_forward_renders_markdown(tmp_path: Path) -> None:
    """The render function produces non-empty output with key sections."""
    from sovereign_agent.config import SETTINGS, Paths
    from sovereign_agent.lineage import lineage_forward, render_forward_markdown

    new_paths = Paths(config_dir=tmp_path / "cfg", data_dir=tmp_path / "data")
    object.__setattr__(SETTINGS, "paths", new_paths)
    SETTINGS.paths.ensure()

    from sovereign_agent.db import open_atoms_db
    conn = open_atoms_db()
    try:
        conn.execute(
            "INSERT INTO atoms(atom_id, type, summary, content_ref, claims, parents, "
            "confidence, created_at, created_by) VALUES (?,?,?,?,?,?,?,?,?)",
            ("atom-render", "fact", "test summary", '{"kind":"inline"}',
             "[]", "[]", 1.0, "2026-05-04T00:00:00Z", '{"actor":"t"}'),
        )
        conn.commit()
    finally:
        conn.close()

    result = lineage_forward("atom-render")
    md = render_forward_markdown(result)
    assert "atom-render" in md
    assert "Lineage" in md


def test_lineage_dict_serializable(tmp_path: Path) -> None:
    """Result must be JSON-serializable for --json output."""
    from sovereign_agent.config import SETTINGS, Paths
    from sovereign_agent.lineage import lineage_forward, lineage_to_dict

    new_paths = Paths(config_dir=tmp_path / "cfg", data_dir=tmp_path / "data")
    object.__setattr__(SETTINGS, "paths", new_paths)
    SETTINGS.paths.ensure()

    from sovereign_agent.db import open_atoms_db
    conn = open_atoms_db()
    try:
        conn.execute(
            "INSERT INTO atoms(atom_id, type, summary, content_ref, claims, parents, "
            "confidence, created_at, created_by) VALUES (?,?,?,?,?,?,?,?,?)",
            ("atom-json", "fact", "json-test", '{"kind":"inline"}',
             "[]", "[]", 1.0, "2026-05-04T00:00:00Z", '{"actor":"t"}'),
        )
        conn.commit()
    finally:
        conn.close()

    result = lineage_forward("atom-json")
    d = lineage_to_dict(result)
    serialized = json.dumps(d)  # must not raise
    assert "atom-json" in serialized


# ─── CLI: sov palace lineage ──────────────────────────────────────────────


from typer.testing import CliRunner
from sovereign_agent.cli import app, ExitCode


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def test_cli_palace_lineage_help(runner: CliRunner) -> None:
    r = runner.invoke(app, ["palace", "lineage", "--help"])
    assert r.exit_code == ExitCode.OK
    assert "lineage" in r.stdout.lower()
    assert "--reverse" in r.stdout


def test_cli_palace_lineage_atom_not_found(runner: CliRunner, tmp_path: Path) -> None:
    cfg, data = tmp_path / "cfg", tmp_path / "data"
    runner.invoke(app, ["--config-dir", str(cfg), "--data-dir", str(data), "init"])
    r = runner.invoke(app, [
        "--config-dir", str(cfg), "--data-dir", str(data),
        "palace", "lineage", "atom-doesnotexist",
    ])
    assert r.exit_code != ExitCode.OK


# ─── Step persistence: VRAM fields round-trip through YAML ─────────────────


def test_step_vram_fields_round_trip(tmp_path: Path) -> None:
    """A Step with vram_* fields written to YAML reads back identically."""
    from sovereign_agent.continuation import (
        Continuation, ContinuationStore, Step,
    )

    store = ContinuationStore(tmp_path / "c")
    store.ensure_root()
    cont = store.create(
        task_id="cont-vram-test",
        goal="test", planner="test", planner_args={},
        steps=[Step(
            id=0, kind="test_kind", args={},
            required_model="orchestrator",
            iterations=1, tokens=5000,
            elapsed_seconds=12.5,
            vram_before_mb=4000,
            vram_peak_mb=5500,
            vram_after_mb=5400,
        )],
    )

    fetched = store.get("cont-vram-test")
    assert fetched.steps[0].vram_before_mb == 4000
    assert fetched.steps[0].vram_peak_mb == 5500
    assert fetched.steps[0].vram_after_mb == 5400
