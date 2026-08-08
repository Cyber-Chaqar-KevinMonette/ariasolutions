"""Tests for v0.2.6 additions: model-affinity scheduling, new planners, exclusions."""
from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from sovereign_agent.cli import ExitCode, app
from sovereign_agent.continuation import Continuation, ContinuationStore, Step
from sovereign_agent.planners.code_inventory import CodeInventoryPlanner
from sovereign_agent.planners.image_inventory import ImageInventoryPlanner
from sovereign_agent.planners.inventory import InventoryPlanner
from sovereign_agent.planners.metadata_inventory import (
    MetadataInventoryPlanner,
    execute_metadata_step,
)
from sovereign_agent.planners.pdf_inventory import PdfInventoryPlanner
from sovereign_agent.planners.base import PlannerError


# ─── Step.required_model field ──────────────────────────────────────────────


def test_step_default_required_model_is_orchestrator() -> None:
    s = Step(id=0, kind="x")
    assert s.required_model == "orchestrator"


def test_step_required_model_persists_through_yaml_round_trip(tmp_path: Path) -> None:
    """Step.required_model must survive write→read of the continuation YAML."""
    store = ContinuationStore(tmp_path / "c")
    cont = store.create(
        goal="multi-model task", planner="p", planner_args={},
        steps=[
            Step(id=0, kind="md", required_model="orchestrator"),
            Step(id=1, kind="img", required_model="vision"),
            Step(id=2, kind="code", required_model="coder"),
            Step(id=3, kind="meta", required_model="none"),
        ],
    )
    fetched = store.get(cont.task_id)
    assert [s.required_model for s in fetched.steps] == [
        "orchestrator", "vision", "coder", "none",
    ]


def test_v025_continuation_yaml_with_no_required_model_field_loads_as_orchestrator(tmp_path: Path) -> None:
    """A continuation file written by v0.2.5 (no required_model) must still load."""
    import yaml
    store = ContinuationStore(tmp_path / "c")
    store.ensure_root()
    legacy_data = {
        "task_id": "cont-legacy",
        "goal": "old style",
        "planner": "inventory",
        "planner_args": {},
        "status": "planned",
        "steps": [
            {"id": 0, "kind": "inventory_file", "args": {"path": "/x"}, "status": "pending"},
        ],
    }
    (store.root / "cont-legacy.yaml").write_text(yaml.safe_dump(legacy_data))
    cont = store.get("cont-legacy")
    assert cont.steps[0].required_model == "orchestrator"


# ─── Continuation: next_pending_for_model / models_needed / progress_by_model ─


def test_next_pending_for_model_returns_correct_step() -> None:
    cont = Continuation(task_id="t", goal="g", planner="p", steps=[
        Step(id=0, kind="x", required_model="orchestrator"),
        Step(id=1, kind="x", required_model="vision"),
        Step(id=2, kind="x", required_model="orchestrator"),
    ])
    assert cont.next_pending_for_model("orchestrator").id == 0
    assert cont.next_pending_for_model("vision").id == 1
    assert cont.next_pending_for_model("coder") is None


def test_next_pending_for_model_skips_completed_of_that_model() -> None:
    cont = Continuation(task_id="t", goal="g", planner="p", steps=[
        Step(id=0, kind="x", required_model="orchestrator", status="done"),
        Step(id=1, kind="x", required_model="orchestrator"),
    ])
    assert cont.next_pending_for_model("orchestrator").id == 1


def test_models_needed_orchestrator_first_then_alpha() -> None:
    cont = Continuation(task_id="t", goal="g", planner="p", steps=[
        Step(id=0, kind="x", required_model="vision"),
        Step(id=1, kind="x", required_model="coder"),
        Step(id=2, kind="x", required_model="orchestrator"),
    ])
    assert cont.models_needed() == ["orchestrator", "coder", "vision"]


def test_models_needed_excludes_terminal_steps() -> None:
    cont = Continuation(task_id="t", goal="g", planner="p", steps=[
        Step(id=0, kind="x", required_model="orchestrator", status="done"),
        Step(id=1, kind="x", required_model="vision"),
    ])
    assert cont.models_needed() == ["vision"]


def test_progress_by_model() -> None:
    cont = Continuation(task_id="t", goal="g", planner="p", steps=[
        Step(id=0, kind="x", required_model="orchestrator", status="done"),
        Step(id=1, kind="x", required_model="orchestrator"),
        Step(id=2, kind="x", required_model="vision", status="done"),
        Step(id=3, kind="x", required_model="vision", status="done"),
    ])
    bm = cont.progress_by_model()
    assert bm["orchestrator"] == (1, 2)
    assert bm["vision"] == (2, 2)


# ─── InventoryPlanner v0.2.6: exclude / no-extension / max-size ──────────────


def _seed_for_inventory(root: Path) -> None:
    (root / "good.md").write_text("ok")
    (root / "skipme.md").write_text("ok")
    (root / "LICENSE").write_text("MIT")
    sub = root / "vendored"
    sub.mkdir()
    (sub / "noisy.md").write_text("ignore")


def test_inventory_excludes_filter_files(tmp_path: Path) -> None:
    _seed_for_inventory(tmp_path)
    p = InventoryPlanner()
    result = p.plan(
        root=str(tmp_path), output=str(tmp_path / "out.txt"),
        patterns=["*.md"], exclude=["*/vendored/*", "*/skipme.md"],
    )
    assert len(result.steps) == 1
    assert "good.md" in result.steps[0].args["path"]


def test_inventory_include_no_extension_finds_extensionless_files(tmp_path: Path) -> None:
    _seed_for_inventory(tmp_path)
    p = InventoryPlanner()
    result = p.plan(
        root=str(tmp_path), output=str(tmp_path / "out.txt"),
        patterns=["*.md"], include_no_extension=True, exclude=["*/vendored/*"],
    )
    paths = [s.args["path"] for s in result.steps]
    assert any("LICENSE" in p_ for p_ in paths)
    assert any("good.md" in p_ for p_ in paths)
    assert any("skipme.md" in p_ for p_ in paths)


def test_inventory_skips_oversized_files(tmp_path: Path) -> None:
    (tmp_path / "small.md").write_text("ok")
    (tmp_path / "huge.md").write_text("X" * 250_000)
    p = InventoryPlanner()
    result = p.plan(
        root=str(tmp_path), output=str(tmp_path / "out.txt"),
        patterns=["*.md"], max_file_size_bytes=200_000,
    )
    assert len(result.steps) == 1
    assert "small.md" in result.steps[0].args["path"]
    assert "skipped_oversized=1" in result.notes


def test_inventory_steps_default_to_orchestrator_model(tmp_path: Path) -> None:
    (tmp_path / "x.md").write_text("ok")
    p = InventoryPlanner()
    result = p.plan(root=str(tmp_path), output=str(tmp_path / "o.txt"), patterns=["*.md"])
    assert all(s.required_model == "orchestrator" for s in result.steps)


# ─── CodeInventoryPlanner ────────────────────────────────────────────────────


def test_code_inventory_tags_steps_for_coder(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x = 1")
    (tmp_path / "b.json").write_text('{"k": 1}')
    p = CodeInventoryPlanner()
    result = p.plan(
        root=str(tmp_path), output=str(tmp_path / "o.txt"),
        patterns=["*.py", "*.json"],
    )
    assert len(result.steps) == 2
    assert all(s.required_model == "coder" for s in result.steps)


def test_code_inventory_no_files_raises(tmp_path: Path) -> None:
    p = CodeInventoryPlanner()
    with pytest.raises(PlannerError, match="no files matched"):
        p.plan(root=str(tmp_path), output=str(tmp_path / "o.txt"))


# ─── ImageInventoryPlanner ────────────────────────────────────────────────────


def test_image_inventory_tags_vision(tmp_path: Path) -> None:
    (tmp_path / "a.png").write_bytes(b"\x89PNG")
    (tmp_path / "b.jpg").write_bytes(b"\xff\xd8\xff")
    p = ImageInventoryPlanner()
    result = p.plan(root=str(tmp_path), output=str(tmp_path / "o.txt"))
    assert len(result.steps) == 2
    assert all(s.required_model == "vision" for s in result.steps)


def test_image_inventory_include_whitelist_works(tmp_path: Path) -> None:
    (tmp_path / "diagram.png").write_bytes(b"\x89PNG")
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "personal.png").write_bytes(b"\x89PNG")
    p = ImageInventoryPlanner()
    result = p.plan(
        root=str(tmp_path), output=str(tmp_path / "o.txt"),
        include=["*/diagram*"],
    )
    assert len(result.steps) == 1
    assert "diagram" in result.steps[0].args["path"]


def test_image_inventory_render_step_tells_model_to_use_image_caption_tool(tmp_path: Path) -> None:
    (tmp_path / "a.png").write_bytes(b"\x89PNG")
    p = ImageInventoryPlanner()
    result = p.plan(root=str(tmp_path), output=str(tmp_path / "o.txt"))
    rendered = p.render_step(result.steps[0], {})
    assert "image_caption" in rendered
    assert "do NOT use read_file" in rendered


# ─── MetadataInventoryPlanner ────────────────────────────────────────────────


def test_metadata_inventory_tags_none_model(tmp_path: Path) -> None:
    (tmp_path / "a.zip").write_bytes(b"PK\x03\x04anything")
    p = MetadataInventoryPlanner()
    result = p.plan(root=str(tmp_path), output=str(tmp_path / "o.txt"))
    assert all(s.required_model == "none" for s in result.steps)


def test_execute_metadata_step_writes_correct_line(tmp_path: Path) -> None:
    target = tmp_path / "thing.zip"
    target.write_bytes(b"PK\x03\x04rest of zip here")
    out = tmp_path / "metadata.txt"
    step = Step(
        id=0, kind="metadata_inventory_file",
        args={"path": str(target), "output": str(out)},
        required_model="none",
    )
    line = execute_metadata_step(step)
    assert "thing.zip" in line
    assert "archive" in line
    assert "size=" in line
    written = out.read_text()
    assert "archive" in written
    assert "ZIP" in written


def test_execute_metadata_step_recognizes_pdf_magic(tmp_path: Path) -> None:
    p = tmp_path / "doc.pdf"
    p.write_bytes(b"%PDF-1.4\n...")
    out = tmp_path / "o.txt"
    step = Step(
        id=0, kind="metadata_inventory_file",
        args={"path": str(p), "output": str(out)},
        required_model="none",
    )
    line = execute_metadata_step(step)
    assert "document" in line and "PDF" in line


def test_execute_metadata_step_unknown_extension(tmp_path: Path) -> None:
    p = tmp_path / "weird.xyz"
    p.write_bytes(b"\x00\x01\x02 not a known magic")
    out = tmp_path / "o.txt"
    step = Step(
        id=0, kind="metadata_inventory_file",
        args={"path": str(p), "output": str(out)},
        required_model="none",
    )
    line = execute_metadata_step(step)
    assert "unknown" in line
    assert ".xyz" in line


# ─── PdfInventoryPlanner ─────────────────────────────────────────────────────


def test_pdf_planner_raises_when_no_extractor_and_no_pdfs(tmp_path: Path) -> None:
    """If no PDFs exist, the planner short-circuits before checking extractors."""
    p = PdfInventoryPlanner()
    with pytest.raises(PlannerError):
        p.plan(root=str(tmp_path), output=str(tmp_path / "o.txt"))


def test_pdf_planner_skips_pdfs_with_no_extractable_text(tmp_path: Path) -> None:
    """A PDF whose extraction returns empty (image-only / corrupted) is skipped.

    We mock the extractor to always return empty. The planner must surface the
    skip in notes, not crash.
    """
    import unittest.mock
    fake = tmp_path / "image_only.pdf"
    fake.write_bytes(b"%PDF-1.4\n garbage that's not real PDF content")
    out = tmp_path / "o.txt"
    p = PdfInventoryPlanner()

    with unittest.mock.patch(
        "sovereign_agent.planners.pdf_inventory._extract", return_value=""
    ):
        with pytest.raises(PlannerError, match="extracted no text"):
            p.plan(root=str(tmp_path), output=str(out))


def test_pdf_planner_creates_step_with_extracted_text_in_args(tmp_path: Path) -> None:
    import unittest.mock
    fake = tmp_path / "good.pdf"
    fake.write_bytes(b"%PDF-1.4\n stub")
    p = PdfInventoryPlanner()
    with unittest.mock.patch(
        "sovereign_agent.planners.pdf_inventory._extract",
        return_value="quantum mechanics paper about coherence in biological systems",
    ):
        result = p.plan(root=str(tmp_path), output=str(tmp_path / "o.txt"))
    assert len(result.steps) == 1
    assert "quantum" in result.steps[0].args["extracted_text"]
    assert result.steps[0].required_model == "orchestrator"


# ─── Registry has all v0.2.6 planners ────────────────────────────────────────


def test_registry_includes_v026_planners() -> None:
    from sovereign_agent.planners import REGISTRY
    for name in ("inventory", "read-files", "code-inventory",
                 "pdf-inventory", "image-inventory", "metadata-inventory"):
        assert name in REGISTRY, f"{name} missing from registry"


# ─── CLI integration: --exclude, --include-no-extension flags work ───────────


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def test_cli_plan_with_exclude_flag(runner: CliRunner, tmp_path: Path) -> None:
    cfg, data = tmp_path / "cfg", tmp_path / "data"
    runner.invoke(app, ["--config-dir", str(cfg), "--data-dir", str(data), "init"])
    target = tmp_path / "corpus"
    target.mkdir()
    (target / "keep.md").write_text("k")
    (target / "skip.md").write_text("s")

    r = runner.invoke(app, [
        "--config-dir", str(cfg), "--data-dir", str(data), "--json",
        "plan", "inventory", "--root", str(target),
        "--output", str(tmp_path / "o.txt"),
        "--pattern", "*.md", "--exclude", "*/skip.md",
    ])
    assert r.exit_code == ExitCode.OK, r.stderr
    import json
    payload = json.loads(r.stdout)
    assert payload["step_count"] == 1


def test_cli_plan_with_include_no_extension(runner: CliRunner, tmp_path: Path) -> None:
    cfg, data = tmp_path / "cfg", tmp_path / "data"
    runner.invoke(app, ["--config-dir", str(cfg), "--data-dir", str(data), "init"])
    target = tmp_path / "corpus"
    target.mkdir()
    (target / "transcript").write_text("text without extension")
    (target / "notes.md").write_text("md file")

    r = runner.invoke(app, [
        "--config-dir", str(cfg), "--data-dir", str(data), "--json",
        "plan", "inventory", "--root", str(target),
        "--output", str(tmp_path / "o.txt"),
        "--pattern", "*.md", "--include-no-extension",
    ])
    assert r.exit_code == ExitCode.OK
    import json
    payload = json.loads(r.stdout)
    assert payload["step_count"] == 2


def test_cli_plan_metadata_inventory_works(runner: CliRunner, tmp_path: Path) -> None:
    cfg, data = tmp_path / "cfg", tmp_path / "data"
    runner.invoke(app, ["--config-dir", str(cfg), "--data-dir", str(data), "init"])
    target = tmp_path / "corpus"
    target.mkdir()
    (target / "thing.zip").write_bytes(b"PK\x03\x04")

    r = runner.invoke(app, [
        "--config-dir", str(cfg), "--data-dir", str(data), "--json",
        "plan", "metadata-inventory",
        "--root", str(target),
        "--output", str(tmp_path / "o.txt"),
    ])
    assert r.exit_code == ExitCode.OK, r.stderr
    import json
    payload = json.loads(r.stdout)
    assert payload["step_count"] == 1


def test_cli_drain_by_model_help(runner: CliRunner) -> None:
    r = runner.invoke(app, ["drain-by-model", "--help"])
    assert r.exit_code == ExitCode.OK
    assert "phase" in r.stdout.lower() or "drain" in r.stdout.lower()


def test_cli_continuations_show_displays_per_model_progress(runner: CliRunner, tmp_path: Path) -> None:
    """When a continuation has multiple model affinities, show should list them."""
    cfg, data = tmp_path / "cfg", tmp_path / "data"
    runner.invoke(app, ["--config-dir", str(cfg), "--data-dir", str(data), "init"])

    # Manually create a multi-model continuation for the test
    from sovereign_agent.continuation import ContinuationStore as CS
    from sovereign_agent.config import SETTINGS, Paths
    new_paths = Paths(config_dir=cfg, data_dir=data)
    object.__setattr__(SETTINGS, "paths", new_paths)
    SETTINGS.paths.ensure()

    store = CS(SETTINGS.paths.continuations_dir)
    cont = store.create(
        goal="multi-model test", planner="inventory", planner_args={},
        steps=[
            Step(id=0, kind="x", required_model="orchestrator"),
            Step(id=1, kind="y", required_model="vision"),
        ],
        task_id="cont-multi-test",
    )

    r = runner.invoke(app, [
        "--config-dir", str(cfg), "--data-dir", str(data), "--json",
        "continuations", "show", "cont-multi-test",
    ])
    assert r.exit_code == ExitCode.OK, r.stderr
    import json
    payload = json.loads(r.stdout)
    assert len(payload["steps"]) == 2
    models = {s["required_model"] for s in payload["steps"]}
    assert models == {"orchestrator", "vision"}
