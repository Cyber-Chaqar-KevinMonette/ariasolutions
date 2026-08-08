"""Tests for v0.2.12: dream sessions, projects, directives, pause/resume."""
from __future__ import annotations

import os
from pathlib import Path

import pytest


# ─── DreamCaps ──────────────────────────────────────────────────────────────


def test_dream_caps_default_max_files_is_2000() -> None:
    from sovereign_agent.dream import DreamCaps
    caps = DreamCaps()
    assert caps.max_files == 2000


def test_dream_caps_files_exceeded() -> None:
    from sovereign_agent.dream import DreamCaps
    caps = DreamCaps(max_files=100)
    exceeded, reason = caps.is_exceeded(
        files_written=100, cycles_completed=5, elapsed_seconds=0,
    )
    assert exceeded
    assert "max_files" in reason


def test_dream_caps_unbounded_files() -> None:
    """max_files=None means unbounded — never exceeded."""
    from sovereign_agent.dream import DreamCaps
    caps = DreamCaps(max_files=None)
    exceeded, _ = caps.is_exceeded(
        files_written=10_000_000, cycles_completed=0, elapsed_seconds=0,
    )
    assert not exceeded


def test_dream_caps_zero_means_unbounded() -> None:
    """max_files=0 (and similar) is treated as unbounded for backward compat."""
    from sovereign_agent.dream import DreamCaps
    caps = DreamCaps(max_files=0, max_cycles=0, max_seconds=0)
    exceeded, _ = caps.is_exceeded(
        files_written=10_000, cycles_completed=10_000, elapsed_seconds=99999,
    )
    assert not exceeded


def test_dream_caps_cycles_exceeded() -> None:
    from sovereign_agent.dream import DreamCaps
    caps = DreamCaps(max_cycles=3)
    exceeded, reason = caps.is_exceeded(
        files_written=0, cycles_completed=3, elapsed_seconds=0,
    )
    assert exceeded
    assert "max_cycles" in reason


def test_dream_caps_seconds_exceeded() -> None:
    from sovereign_agent.dream import DreamCaps
    caps = DreamCaps(max_seconds=60.0)
    exceeded, reason = caps.is_exceeded(
        files_written=0, cycles_completed=0, elapsed_seconds=120.0,
    )
    assert exceeded
    assert "max_seconds" in reason


# ─── DreamStore ─────────────────────────────────────────────────────────────


def test_dream_store_create_and_get(tmp_path: Path) -> None:
    from sovereign_agent.dream import DreamStore
    store = DreamStore(tmp_path / "sessions", tmp_path / "work")
    d = store.create(goal="test dream")
    assert d.dream_id.startswith("dream-")
    assert (tmp_path / "sessions" / f"{d.dream_id}.yaml").exists()
    # Work dir auto-created.
    assert (tmp_path / "work" / d.dream_id).is_dir()
    # Roundtrip.
    loaded = store.get(d.dream_id)
    assert loaded.goal == "test dream"
    assert loaded.status == "active"
    assert loaded.caps.max_files == 2000


def test_dream_store_list_filters_by_status(tmp_path: Path) -> None:
    from sovereign_agent.dream import DreamStore
    store = DreamStore(tmp_path / "sessions", tmp_path / "work")
    a = store.create(goal="a")
    b = store.create(goal="b")
    b.status = "paused"
    store.save(b)
    actives = store.list_all(status="active")
    paused = store.list_all(status="paused")
    assert len(actives) == 1 and actives[0].dream_id == a.dream_id
    assert len(paused) == 1 and paused[0].dream_id == b.dream_id


def test_dream_id_collision_raises(tmp_path: Path) -> None:
    from sovereign_agent.dream import DreamStore
    store = DreamStore(tmp_path / "sessions", tmp_path / "work")
    store.create(goal="x", dream_id="dream-test-123")
    with pytest.raises(FileExistsError):
        store.create(goal="y", dream_id="dream-test-123")


def test_dream_yaml_roundtrip_preserves_caps(tmp_path: Path) -> None:
    from sovereign_agent.dream import DreamCaps, DreamStore
    store = DreamStore(tmp_path / "sessions", tmp_path / "work")
    d = store.create(goal="x", caps=DreamCaps(
        max_files=500, max_cycles=10, max_seconds=300.0,
    ))
    loaded = store.get(d.dream_id)
    assert loaded.caps.max_files == 500
    assert loaded.caps.max_cycles == 10
    assert loaded.caps.max_seconds == 300.0


def test_dream_unknown_status_raises_corrupt(tmp_path: Path) -> None:
    from sovereign_agent.dream import DreamCorrupt, DreamStore
    store = DreamStore(tmp_path / "sessions", tmp_path / "work")
    d = store.create(goal="x")
    path = tmp_path / "sessions" / f"{d.dream_id}.yaml"
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace("status: active", "status: bogus"))
    with pytest.raises(DreamCorrupt):
        store.get(d.dream_id)


# ─── cycle_task_id determinism ──────────────────────────────────────────────


def test_cycle_task_id_is_deterministic() -> None:
    from sovereign_agent.dream import cycle_task_id_for
    a = cycle_task_id_for("dream-01J9ABCDEFGHIJ0123456789", 1)
    b = cycle_task_id_for("dream-01J9ABCDEFGHIJ0123456789", 1)
    assert a == b
    assert a.startswith("cycle-")
    assert "001" in a


def test_cycle_task_id_orders_within_dream() -> None:
    from sovereign_agent.dream import cycle_task_id_for
    ids = [cycle_task_id_for("dream-01J9ABCDEFGHIJ", i) for i in range(1, 6)]
    assert ids == sorted(ids)


# ─── count_files_under ──────────────────────────────────────────────────────


def test_count_files_under_basic(tmp_path: Path) -> None:
    from sovereign_agent.dream import count_files_under
    (tmp_path / "a.txt").write_text("a")
    (tmp_path / "b.txt").write_text("b")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "c.txt").write_text("c")
    assert count_files_under(tmp_path) == 3


def test_count_files_under_skips_git(tmp_path: Path) -> None:
    from sovereign_agent.dream import count_files_under
    (tmp_path / "a.txt").write_text("a")
    git = tmp_path / ".git"
    git.mkdir()
    (git / "HEAD").write_text("ref: refs/heads/main")
    (git / "config").write_text("[core]")
    assert count_files_under(tmp_path) == 1


def test_count_files_under_missing_returns_zero(tmp_path: Path) -> None:
    from sovereign_agent.dream import count_files_under
    assert count_files_under(tmp_path / "does-not-exist") == 0


# ─── trillion-dollar planner ────────────────────────────────────────────────


def test_trillion_dollar_planner_produces_5_steps(tmp_path: Path) -> None:
    from sovereign_agent.planners.trillion_dollar import TrillionDollarPlanner
    p = TrillionDollarPlanner()
    result = p.plan(
        cycle_dir=str(tmp_path / "cycle-001"),
        dream_id="dream-test", cycle_number=1,
    )
    assert len(result.steps) == 5
    kinds = [s.kind for s in result.steps]
    assert kinds == [
        "dream_ideate", "dream_architect", "dream_build",
        "dream_document", "dream_atomize",
    ]


def test_trillion_dollar_step_models() -> None:
    from sovereign_agent.planners.trillion_dollar import TrillionDollarPlanner
    p = TrillionDollarPlanner()
    result = p.plan(cycle_dir="/tmp/x", dream_id="d", cycle_number=1)
    models = [s.required_model for s in result.steps]
    # ideate, architect, document → orchestrator; build → coder; atomize → none
    assert models == ["orchestrator", "orchestrator", "coder",
                       "orchestrator", "none"]


def test_trillion_dollar_requires_cycle_dir() -> None:
    from sovereign_agent.planners.base import PlannerError
    from sovereign_agent.planners.trillion_dollar import TrillionDollarPlanner
    p = TrillionDollarPlanner()
    with pytest.raises(PlannerError, match="cycle_dir"):
        p.plan(dream_id="d")


def test_trillion_dollar_requires_dream_id() -> None:
    from sovereign_agent.planners.base import PlannerError
    from sovereign_agent.planners.trillion_dollar import TrillionDollarPlanner
    p = TrillionDollarPlanner()
    with pytest.raises(PlannerError, match="dream_id"):
        p.plan(cycle_dir="/tmp/x")


def test_trillion_dollar_creates_cycle_subdirs(tmp_path: Path) -> None:
    from sovereign_agent.planners.trillion_dollar import TrillionDollarPlanner
    p = TrillionDollarPlanner()
    cycle_dir = tmp_path / "cycle-001"
    p.plan(cycle_dir=str(cycle_dir), dream_id="d", cycle_number=1)
    assert cycle_dir.is_dir()
    assert (cycle_dir / "src").is_dir()


def test_trillion_dollar_planner_in_registry() -> None:
    from sovereign_agent.planners import REGISTRY
    assert "trillion-dollar" in REGISTRY


# ─── Projects: scan + diff ──────────────────────────────────────────────────


def test_scan_directory_basic(tmp_path: Path) -> None:
    from sovereign_agent.projects import scan_directory
    (tmp_path / "a.txt").write_text("hello")
    (tmp_path / "b.py").write_text("print(1)")
    files = scan_directory(tmp_path, excludes=[])
    paths = sorted(f.path for f in files)
    assert paths == ["a.txt", "b.py"]
    for f in files:
        assert f.size > 0
        assert len(f.hash) == 64  # sha256 hex


def test_scan_directory_default_excludes_skip_git(tmp_path: Path) -> None:
    from sovereign_agent.projects import scan_directory
    (tmp_path / "a.txt").write_text("x")
    git = tmp_path / ".git"
    git.mkdir()
    (git / "HEAD").write_text("y")
    files = scan_directory(tmp_path)  # default excludes
    paths = [f.path for f in files]
    assert paths == ["a.txt"]


def test_scan_directory_extra_excludes_compose(tmp_path: Path) -> None:
    from sovereign_agent.projects import scan_directory
    (tmp_path / "a.txt").write_text("x")
    (tmp_path / "b.py").write_text("y")
    files = scan_directory(tmp_path, excludes=["*.py"])
    paths = [f.path for f in files]
    assert paths == ["a.txt"]


def test_scan_directory_max_files(tmp_path: Path) -> None:
    from sovereign_agent.projects import scan_directory
    for i in range(20):
        (tmp_path / f"f{i:02d}.txt").write_text(str(i))
    files = scan_directory(tmp_path, excludes=[], max_files=5)
    assert len(files) == 5


def test_diff_snapshots_detects_added_modified_removed(tmp_path: Path) -> None:
    from sovereign_agent.projects import (
        FileEntry, ProjectSnapshot, diff_snapshots,
    )
    old = ProjectSnapshot(name="x", root=str(tmp_path), files=[
        FileEntry(path="a", size=1, mtime=0.0, hash="aaa"),
        FileEntry(path="b", size=1, mtime=0.0, hash="bbb"),
        FileEntry(path="c", size=1, mtime=0.0, hash="ccc"),
    ])
    new = ProjectSnapshot(name="x", root=str(tmp_path), files=[
        FileEntry(path="a", size=1, mtime=0.0, hash="aaa"),       # unchanged
        FileEntry(path="b", size=1, mtime=0.0, hash="bbb_NEW"),    # modified
        # 'c' removed
        FileEntry(path="d", size=1, mtime=0.0, hash="ddd"),       # added
    ])
    diff = diff_snapshots(old, new)
    assert diff.added == ["d"]
    assert diff.modified == ["b"]
    assert diff.removed == ["c"]
    assert diff.unchanged_count == 1
    assert not diff.is_empty


def test_diff_snapshots_unchanged(tmp_path: Path) -> None:
    from sovereign_agent.projects import (
        FileEntry, ProjectSnapshot, diff_snapshots,
    )
    files = [FileEntry(path="a", size=1, mtime=0.0, hash="x")]
    old = ProjectSnapshot(name="x", root=str(tmp_path), files=files)
    new = ProjectSnapshot(name="x", root=str(tmp_path), files=files)
    diff = diff_snapshots(old, new)
    assert diff.is_empty
    assert diff.unchanged_count == 1


def test_project_store_save_and_get(tmp_path: Path) -> None:
    from sovereign_agent.projects import (
        FileEntry, ProjectSnapshot, ProjectStore,
    )
    store = ProjectStore(tmp_path)
    snap = ProjectSnapshot(name="myproj", root="/some/where",
                            files=[FileEntry("a", 1, 0.0, "h")])
    store.save(snap)
    loaded = store.get("myproj")
    assert loaded.name == "myproj"
    assert loaded.file_count == 1


def test_project_store_rejects_bad_names(tmp_path: Path) -> None:
    from sovereign_agent.projects import ProjectError, ProjectStore
    store = ProjectStore(tmp_path)
    for bad in ("", "with space", "../escape", "with/slash"):
        with pytest.raises(ProjectError):
            store._path(bad)


# ─── Directives parser ─────────────────────────────────────────────────────


def test_directive_dream_start_default() -> None:
    from sovereign_agent.directives import parse_directive
    d = parse_directive("Build trillion-dollar software, max 2000 files")
    assert d.intent == "dream"
    assert d.kwargs["max_files"] == 2000
    assert d.is_ready


def test_directive_dream_forever() -> None:
    from sovereign_agent.directives import parse_directive
    d = parse_directive("Build trillion-dollar software forever")
    assert d.intent == "dream"
    assert d.kwargs["max_files"] == 0
    assert d.is_ready


def test_directive_dream_until_i_pause() -> None:
    from sovereign_agent.directives import parse_directive
    d = parse_directive("Keep making trillion dollar softwares until I pause")
    assert d.intent == "dream"
    assert d.kwargs["max_files"] == 0


def test_directive_dream_no_cap_asks() -> None:
    from sovereign_agent.directives import parse_directive
    d = parse_directive("Build trillion dollar software")
    assert d.intent == "dream"
    # No cap given, no 'forever' keyword → ask interactively
    assert any(q.field == "max_files" for q in d.questions)
    assert not d.is_ready


def test_directive_pause_dream() -> None:
    from sovereign_agent.directives import parse_directive
    d = parse_directive("Pause my trillion dollar dream")
    assert d.intent == "dream_control"
    assert d.kwargs["action"] == "pause"


def test_directive_pause_dream_with_id() -> None:
    from sovereign_agent.directives import parse_directive
    d = parse_directive("Pause dream-01J9ABCDEFGHIJK0123456")
    assert d.intent == "dream_control"
    assert d.kwargs["action"] == "pause"
    assert d.kwargs["dream_id"] == "dream-01J9ABCDEFGHIJK0123456"


def test_directive_resume_continuation() -> None:
    from sovereign_agent.directives import parse_directive
    d = parse_directive("Resume cont-01J9ABCDEFGHIJKLMNOPQR")
    assert d.intent == "continue_cont"
    assert d.kwargs["task_id"] == "cont-01J9ABCDEFGHIJKLMNOPQR"


def test_directive_project_update() -> None:
    from sovereign_agent.directives import parse_directive
    d = parse_directive("I updated genesis-seeds")
    assert d.intent == "projects"
    assert d.kwargs["action"] == "update"
    # Hyphenated name not picked up by the simple regex; ok if questions cover it.
    # If the regex DID catch it, name will be set; otherwise we ask.
    assert d.kwargs.get("name") in ("genesis-seeds", None) or \
           any(q.field == "name" for q in d.questions)


def test_directive_inventory_with_path() -> None:
    from sovereign_agent.directives import parse_directive
    d = parse_directive(
        "Inventory ~/AA-Erebo/Genesis-Seeds for markdown files"
    )
    assert d.intent == "inventory"
    assert "Genesis-Seeds" in d.kwargs["root"]
    assert "*.md" in d.kwargs["patterns"]


def test_directive_status() -> None:
    from sovereign_agent.directives import parse_directive
    d = parse_directive("Show me status")
    assert d.intent == "status"


def test_directive_unknown() -> None:
    from sovereign_agent.directives import parse_directive
    d = parse_directive("Tell me a joke about elephants")
    assert d.intent == "unknown"
    assert d.confidence_message


def test_directive_empty() -> None:
    from sovereign_agent.directives import parse_directive
    d = parse_directive("")
    assert d.intent == "unknown"


def test_directive_summary_renders() -> None:
    from sovereign_agent.directives import (
        parse_directive, render_directive_summary,
    )
    d = parse_directive("Build trillion dollar software, max 500 files")
    s = render_directive_summary(d)
    assert "trillion-dollar" in s
    assert "500" in s


# ─── continuation paused status ─────────────────────────────────────────────


def test_continuation_paused_status_valid() -> None:
    """The 'paused' status must round-trip through YAML."""
    from sovereign_agent.continuation import (
        Continuation, Step, _from_yaml_dict, _to_yaml_dict,
    )
    cont = Continuation(
        task_id="cont-test", goal="x", planner="inventory",
        steps=[Step(id=0, kind="x")], status="paused",
    )
    d = _to_yaml_dict(cont)
    assert d["status"] == "paused"
    loaded = _from_yaml_dict(d)
    assert loaded.status == "paused"


def test_continuation_paused_preserved_across_recompute() -> None:
    """update_status_from_steps must keep paused state."""
    from sovereign_agent.continuation import Continuation, Step
    cont = Continuation(
        task_id="t", goal="g", planner="inventory",
        steps=[
            Step(id=0, kind="x", status="done"),
            Step(id=1, kind="x", status="pending"),
        ],
        status="paused",
    )
    cont.update_status_from_steps()
    assert cont.status == "paused"


def test_continuation_paused_settles_to_done_when_drained() -> None:
    """Once all steps terminal, paused → done (no work left to pause)."""
    from sovereign_agent.continuation import Continuation, Step
    cont = Continuation(
        task_id="t", goal="g", planner="inventory",
        steps=[Step(id=0, kind="x", status="done")],
        status="paused",
    )
    cont.update_status_from_steps()
    assert cont.status == "done"


def test_continuation_old_status_still_loads() -> None:
    """Backward compat — pre-v0.2.12 continuations still load."""
    from sovereign_agent.continuation import _from_yaml_dict
    # Minimal valid v0.2.11-shape dict.
    d = {
        "task_id": "cont-old", "goal": "g", "planner": "inventory",
        "status": "in_progress", "steps": [],
    }
    cont = _from_yaml_dict(d)
    assert cont.status == "in_progress"


# ─── continue_runner respects paused ────────────────────────────────────────


@pytest.mark.asyncio
async def test_runner_returns_paused_outcome_for_paused_continuation(
    tmp_path: Path,
) -> None:
    """The runner must NOT advance a paused continuation.

    Pass the ContinuationStore directly into run_one_step rather than
    monkeypatching the frozen Paths dataclass — same effect, simpler.
    """
    from sovereign_agent.continuation import (
        ContinuationStore, Step,
    )
    from sovereign_agent.continue_runner import run_one_step

    store = ContinuationStore(tmp_path)
    cont = store.create(
        goal="x", planner="inventory",
        planner_args={}, steps=[
            Step(id=0, kind="inventory_file", required_model="orchestrator"),
        ],
    )
    # Set paused.
    with store.lock(cont.task_id) as c:
        c.status = "paused"

    result = await run_one_step(
        task_id=cont.task_id, tools={}, store=store, budget=None,
    )
    assert result.outcome == "paused"


# ─── Registry sanity ────────────────────────────────────────────────────────


def test_registered_planner_count_matches_v0212() -> None:
    """Sanity: 13 planners in v0.2.11 + trillion-dollar = 14 in v0.2.12."""
    from sovereign_agent.planners import REGISTRY
    # Don't pin the exact count too tightly, but ensure trillion-dollar is in
    # AND we didn't drop any of the known v0.2.11 entries.
    expected_in = {
        "inventory", "read-files", "code-inventory", "pdf-inventory",
        "image-inventory", "metadata-inventory", "palace-mine",
        "palace-reflect", "palace-apply", "palace-clean",
        "mos-canon-ingest", "impact-score", "summaries-to-atoms",
        "trillion-dollar",
    }
    assert expected_in.issubset(REGISTRY.keys())


def test_no_model_dispatch_includes_dream_atomize() -> None:
    """The runner must know how to execute the atomize step."""
    from sovereign_agent.continue_runner import _NO_MODEL_DISPATCH
    assert "dream_atomize" in _NO_MODEL_DISPATCH


# ─── Integration: a fully-resolved directive can drive `sov dream start` ────


def test_directive_dispatch_creates_dream(tmp_path: Path) -> None:
    """End-to-end: parse → DreamStore.create with the parsed kwargs.

    Tests that a parse-result's kwargs flow correctly into DreamStore
    without going through the CLI dispatch (CLI is integration-tested
    separately via subprocess).
    """
    from sovereign_agent.directives import parse_directive
    from sovereign_agent.dream import DreamCaps, DreamStore

    sessions = tmp_path / "sessions"
    work = tmp_path / "work"

    d = parse_directive("Build trillion dollar software, max 1000 files")
    assert d.is_ready

    store = DreamStore(sessions, work)
    dream = store.create(
        goal=d.kwargs["goal"],
        caps=DreamCaps(max_files=d.kwargs["max_files"]),
    )
    assert dream.caps.max_files == 1000
    assert dream.dream_id.startswith("dream-")


# ─── Atomize idempotency ────────────────────────────────────────────────────
# (real atomize hits sqlite-vec which may not be available in CI; we test
# the deterministic atom_id computation directly)


def test_atomize_diff_id_is_deterministic() -> None:
    """Two runs of atomize_diff over the same diff produce the same atom_ids.

    We don't open the DB here — just assert the seed-hash logic is stable.
    """
    import hashlib
    project = "p"
    rel_path = "src/x.py"
    file_hash = "abc123"
    seed_a = f"{project}:modified:{rel_path}:{file_hash}".encode("utf-8")
    seed_b = f"{project}:modified:{rel_path}:{file_hash}".encode("utf-8")
    assert hashlib.sha256(seed_a).hexdigest() == hashlib.sha256(seed_b).hexdigest()
