"""Tests for drafts.py and planners/marketing_brief.py — v0.2.15.3."""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest


# ── drafts ──────────────────────────────────────────────────────────────────


def test_drafts_archive_creates_zip_and_sidecar(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_DATA", str(tmp_path / "data"))
    # Force re-import so SETTINGS reads the patched env var
    import importlib, sovereign_agent.drafts as d
    importlib.reload(d)

    src = tmp_path / "proj"
    src.mkdir()
    (src / "README.md").write_text("# hello\n", encoding="utf-8")
    (src / "main.py").write_text("print('hi')\n", encoding="utf-8")
    sub = src / "data"
    sub.mkdir()
    (sub / "values.txt").write_text("alpha\nbeta\n", encoding="utf-8")

    rec = d.archive_project(
        "My Project", src,
        label="v0.2.15.3", notes="first archive",
    )

    assert rec.zip_path.exists()
    assert rec.sidecar_path.exists()
    assert rec.file_count == 3
    assert rec.bytes_total > 0
    assert len(rec.sha256) == 64                  # sha256 hex
    assert rec.title == "My Project"
    assert rec.label == "v0.2.15.3"
    assert rec.notes == "first archive"

    # Sidecar JSON round-trips
    side = json.loads(rec.sidecar_path.read_text())
    assert side["id"] == rec.id
    assert side["file_count"] == 3
    assert side["sha256"] == rec.sha256

    # Zip is valid and contains what we expect
    with zipfile.ZipFile(rec.zip_path) as z:
        names = sorted(z.namelist())
    assert "README.md" in names
    assert "main.py" in names
    assert "data/values.txt" in names


def test_drafts_archive_respects_excludes(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_DATA", str(tmp_path / "data"))
    import importlib, sovereign_agent.drafts as d
    importlib.reload(d)

    src = tmp_path / "proj"
    src.mkdir()
    (src / "keep.py").write_text("yes")
    (src / "skip.pyc").write_text("no")
    (src / "build").mkdir()
    (src / "build" / "artifact.bin").write_text("nope")

    rec = d.archive_project(
        "Excluded", src,
        exclude_patterns=["*.pyc", "build/*"],
    )

    with zipfile.ZipFile(rec.zip_path) as z:
        names = z.namelist()
    assert "keep.py" in names
    assert "skip.pyc" not in names
    assert "build/artifact.bin" not in names


def test_drafts_list_returns_newest_first(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_DATA", str(tmp_path / "data"))
    import importlib, time, sovereign_agent.drafts as d
    importlib.reload(d)

    src = tmp_path / "proj"
    src.mkdir()
    (src / "f.txt").write_text("x")

    r1 = d.archive_project("First", src)
    # Sleep so the second draft has a different timestamp in its id
    time.sleep(1.1)
    r2 = d.archive_project("Second", src)

    rows = d.list_drafts()
    assert len(rows) == 2
    assert rows[0].id == r2.id     # newest first
    assert rows[1].id == r1.id


def test_drafts_show_returns_none_for_unknown_id(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_DATA", str(tmp_path / "data"))
    import importlib, sovereign_agent.drafts as d
    importlib.reload(d)
    assert d.show_draft("not-a-real-id") is None


def test_drafts_archive_raises_on_missing_source(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_DATA", str(tmp_path / "data"))
    import importlib, sovereign_agent.drafts as d
    importlib.reload(d)
    with pytest.raises(FileNotFoundError):
        d.archive_project("Ghost", tmp_path / "does-not-exist")


def test_drafts_archive_handles_single_file(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_DATA", str(tmp_path / "data"))
    import importlib, sovereign_agent.drafts as d
    importlib.reload(d)

    f = tmp_path / "lonely.md"
    f.write_text("# alone\n")
    rec = d.archive_project("Lonely Doc", f)
    assert rec.file_count == 1
    with zipfile.ZipFile(rec.zip_path) as z:
        assert z.namelist() == ["lonely.md"]


# ── marketing brief planner ─────────────────────────────────────────────────


def test_marketing_brief_plan_emits_five_sections():
    from sovereign_agent.planners import get_planner
    p = get_planner("marketing-brief")
    plan = p.plan(product="Sovereign Agent", output="/tmp/brief.md")
    assert plan.goal.startswith("Marketing brief for")
    assert len(plan.steps) == 5
    sections = [s.args["section"] for s in plan.steps]
    assert sections == [
        "positioning", "audience", "messaging",
        "channel-copy", "distribution-plan",
    ]


def test_marketing_brief_plan_requires_product():
    from sovereign_agent.planners import get_planner
    from sovereign_agent.planners.base import PlannerError
    p = get_planner("marketing-brief")
    with pytest.raises(PlannerError, match="product"):
        p.plan(output="/tmp/brief.md")


def test_marketing_brief_plan_requires_output():
    from sovereign_agent.planners import get_planner
    from sovereign_agent.planners.base import PlannerError
    p = get_planner("marketing-brief")
    with pytest.raises(PlannerError, match="output"):
        p.plan(product="X")


def test_marketing_brief_skip_drops_sections():
    from sovereign_agent.planners import get_planner
    p = get_planner("marketing-brief")
    plan = p.plan(
        product="X", output="/tmp/x.md",
        skip=["distribution-plan", "messaging"],
    )
    assert len(plan.steps) == 3
    sections = [s.args["section"] for s in plan.steps]
    assert "distribution-plan" not in sections
    assert "messaging" not in sections


def test_marketing_brief_render_step_includes_context():
    from sovereign_agent.planners import get_planner
    p = get_planner("marketing-brief")
    plan = p.plan(
        product="Sovereign Agent v0.2.15.3",
        output="/tmp/x.md",
        tone="warm operator",
        audience="founders running local LLMs",
        highlights=["auditable", "no cloud"],
    )
    rendered = p.render_step(plan.steps[0], {})
    assert "Sovereign Agent v0.2.15.3" in rendered
    assert "warm operator" in rendered
    assert "founders running local LLMs" in rendered
    assert "auditable" in rendered
    assert "positioning" in rendered.lower()
    assert "markdown" in rendered.lower()


def test_marketing_brief_in_registry():
    from sovereign_agent.planners import REGISTRY, planner_names
    assert "marketing-brief" in REGISTRY
    assert "marketing-brief" in planner_names()
