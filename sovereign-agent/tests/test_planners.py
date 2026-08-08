"""Tests for planners and the planner registry. v0.2.5."""
from __future__ import annotations

from pathlib import Path

import pytest

from sovereign_agent.planners import (
    REGISTRY,
    PlannerNotFound,
    get_planner,
    planner_names,
)
from sovereign_agent.planners.base import PlannerError
from sovereign_agent.planners.inventory import InventoryPlanner
from sovereign_agent.planners.read_files import ReadFilesPlanner


# ─── Registry ───────────────────────────────────────────────────────────────


def test_registry_has_known_planners() -> None:
    assert "inventory" in REGISTRY
    assert "read-files" in REGISTRY


def test_get_planner_unknown_raises_with_available() -> None:
    with pytest.raises(PlannerNotFound) as excinfo:
        get_planner("does-not-exist")
    assert "inventory" in str(excinfo.value)
    assert "read-files" in str(excinfo.value)


def test_planner_names_sorted() -> None:
    names = planner_names()
    assert names == sorted(names)
    assert "inventory" in names


# ─── Inventory planner ──────────────────────────────────────────────────────


def _seed_dir(root: Path) -> None:
    (root / "a.md").write_text("alpha")
    (root / "b.md").write_text("beta")
    (root / "ignore.png").write_bytes(b"\x89PNG")
    sub = root / "sub"
    sub.mkdir()
    (sub / "c.md").write_text("gamma")
    (sub / "skip.exe").write_bytes(b"\x00")


def test_inventory_plan_walks_recursively(tmp_path: Path) -> None:
    _seed_dir(tmp_path)
    out = tmp_path / "INVENTORY.txt"
    p = InventoryPlanner()
    result = p.plan(root=str(tmp_path), output=str(out), patterns=["*.md"])
    assert len(result.steps) == 3
    paths = sorted(s.args["path"] for s in result.steps)
    expected = sorted([
        str((tmp_path / "a.md").resolve()),
        str((tmp_path / "b.md").resolve()),
        str((tmp_path / "sub" / "c.md").resolve()),
    ])
    assert paths == expected
    assert result.output_path == str(out.resolve())


def test_inventory_plan_non_recursive(tmp_path: Path) -> None:
    _seed_dir(tmp_path)
    p = InventoryPlanner()
    result = p.plan(
        root=str(tmp_path),
        output=str(tmp_path / "out.txt"),
        patterns=["*.md"],
        recursive=False,
    )
    assert len(result.steps) == 2  # a.md, b.md only


def test_inventory_plan_max_files(tmp_path: Path) -> None:
    _seed_dir(tmp_path)
    p = InventoryPlanner()
    result = p.plan(
        root=str(tmp_path),
        output=str(tmp_path / "out.txt"),
        patterns=["*.md"],
        max_files=2,
    )
    assert len(result.steps) == 2


def test_inventory_plan_missing_root_raises() -> None:
    p = InventoryPlanner()
    with pytest.raises(PlannerError, match="root.*required"):
        p.plan(output="/tmp/x")


def test_inventory_plan_missing_output_raises(tmp_path: Path) -> None:
    p = InventoryPlanner()
    with pytest.raises(PlannerError, match="output.*required"):
        p.plan(root=str(tmp_path))


def test_inventory_plan_nonexistent_root_raises(tmp_path: Path) -> None:
    p = InventoryPlanner()
    with pytest.raises(PlannerError, match="does not exist"):
        p.plan(root=str(tmp_path / "ghost"), output=str(tmp_path / "x"))


def test_inventory_plan_root_must_be_dir(tmp_path: Path) -> None:
    f = tmp_path / "afile.txt"
    f.write_text("x")
    p = InventoryPlanner()
    with pytest.raises(PlannerError, match="must be a directory"):
        p.plan(root=str(f), output=str(tmp_path / "out.txt"))


def test_inventory_plan_no_matches_raises(tmp_path: Path) -> None:
    (tmp_path / "only.png").write_bytes(b"\x89PNG")
    p = InventoryPlanner()
    with pytest.raises(PlannerError, match="no files matched"):
        p.plan(root=str(tmp_path), output=str(tmp_path / "out.txt"), patterns=["*.md"])


def test_inventory_plan_is_deterministic(tmp_path: Path) -> None:
    _seed_dir(tmp_path)
    p = InventoryPlanner()
    out = str(tmp_path / "out.txt")
    r1 = p.plan(root=str(tmp_path), output=out, patterns=["*.md"])
    r2 = p.plan(root=str(tmp_path), output=out, patterns=["*.md"])
    assert [s.args["path"] for s in r1.steps] == [s.args["path"] for s in r2.steps]


def test_inventory_render_step_shape(tmp_path: Path) -> None:
    p = InventoryPlanner()
    _seed_dir(tmp_path)
    result = p.plan(
        root=str(tmp_path),
        output=str(tmp_path / "out.txt"),
        patterns=["*.md"],
    )
    rendered = p.render_step(result.steps[0], {})
    assert "Read the file" in rendered
    assert result.steps[0].args["path"] in rendered
    assert result.steps[0].args["output"] in rendered


# ─── Read-files planner ─────────────────────────────────────────────────────


def test_read_files_plan_basic(tmp_path: Path) -> None:
    _seed_dir(tmp_path)
    p = ReadFilesPlanner()
    result = p.plan(root=str(tmp_path), patterns=["*.md"], tag="test-corpus")
    assert len(result.steps) == 3
    assert all(s.args["tag"] == "test-corpus" for s in result.steps)
    assert result.output_path is None  # this planner doesn't aggregate to a file


def test_read_files_plan_missing_root_raises() -> None:
    p = ReadFilesPlanner()
    with pytest.raises(PlannerError, match="root"):
        p.plan()


def test_read_files_render_step_mentions_path_and_tag(tmp_path: Path) -> None:
    _seed_dir(tmp_path)
    p = ReadFilesPlanner()
    result = p.plan(root=str(tmp_path), patterns=["*.md"], tag="ingest-2026")
    rendered = p.render_step(result.steps[0], {})
    assert result.steps[0].args["path"] in rendered
    assert "ingest-2026" in rendered
