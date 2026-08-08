"""Tests for v0.2.8: palace_mining extractors + palace-mine planner."""
from __future__ import annotations

from pathlib import Path

import pytest

from sovereign_agent.continuation import Step
from sovereign_agent.palace import (
    Closet, Entity, Palace, Triple,
)
from sovereign_agent.palace_mining import (
    closet_id_for_atom,
    detect_entities,
    detect_memory_types,
    entity_id_for_name,
    extract_triples,
    mine_atom,
    synthesize_topic,
    triple_id_for,
)
from sovereign_agent.planners.base import PlannerError
from sovereign_agent.planners.palace_mine import (
    PalaceMinePlanner,
    execute_palace_mine_step,
)


# ─── Memory type detection ──────────────────────────────────────────────────


def test_detect_decision_marker() -> None:
    text = "We decided to use Postgres because of full-text search support."
    types = detect_memory_types(text)
    type_names = {t.memory_type for t in types}
    assert "decision" in type_names


def test_detect_preference_marker() -> None:
    text = "I prefer black coffee. Always use the standard brew."
    types = detect_memory_types(text)
    assert "preference" in {t.memory_type for t in types}


def test_detect_milestone_marker() -> None:
    text = "Finally got the OAuth flow working — it works end-to-end."
    types = detect_memory_types(text)
    assert "milestone" in {t.memory_type for t in types}


def test_detect_problem_marker() -> None:
    text = "The CI keeps failing on the integration test. The error is a NoneType."
    types = detect_memory_types(text)
    assert "problem" in {t.memory_type for t in types}


def test_detect_emotional_marker() -> None:
    text = "I'm feeling really proud of how this turned out."
    types = detect_memory_types(text)
    assert "emotional" in {t.memory_type for t in types}


def test_detect_multiple_types_in_one_text() -> None:
    text = "We decided to rewrite. It works now! I'm grateful."
    types = detect_memory_types(text)
    type_names = {t.memory_type for t in types}
    assert {"decision", "milestone", "emotional"} <= type_names


def test_detect_no_markers_returns_empty() -> None:
    text = "The quick brown fox jumps over the lazy dog."
    types = detect_memory_types(text)
    assert types == []


def test_confidence_scales_with_marker_density() -> None:
    sparse = "We decided to ship."  # 1 marker
    dense = (
        "We decided to ship the new architecture. The trade-off was clear, "
        "the strategy made sense, and the framework is the right approach."
    )  # multiple markers
    sparse_conf = detect_memory_types(sparse)[0].confidence
    dense_conf = detect_memory_types(dense)[0].confidence
    assert dense_conf > sparse_conf


# ─── Entity detection ──────────────────────────────────────────────────────


def test_detect_multiword_proper_nouns() -> None:
    text = "I worked on Genesis-Seeds with Milla Jovovich today."
    entities = detect_entities(text)
    assert any("Genesis-Seeds" in e or "Milla Jovovich" in e for e in entities)


def test_detect_skips_stoplist_words() -> None:
    text = "The Quick Brown Fox is amazing. There Are Many Things."
    entities = detect_entities(text)
    # "The Quick Brown Fox" is multiword + capitalized but starts with stoplist.
    # Implementation: stoplist is checked on cleaned (the whole phrase). "Quick Brown Fox" is OK.
    # The point is: bare "The" or "There" alone won't appear.
    assert "The" not in entities
    assert "There" not in entities


def test_detect_named_entity_with_signal() -> None:
    text = "The project Apollo was created by Neil."
    entities = detect_entities(text)
    assert "Apollo" in entities


def test_detect_respects_max_entities() -> None:
    text = " ".join(f"Project {chr(65+i)}{chr(65+i)}" for i in range(30))
    entities = detect_entities(text, max_entities=5)
    assert len(entities) <= 5


def test_detect_empty_text() -> None:
    assert detect_entities("") == []


# ─── Topic synthesis ──────────────────────────────────────────────────────


def test_topic_includes_memory_type_prefix() -> None:
    text = "We decided to use Postgres."
    types = detect_memory_types(text)
    entities = detect_entities(text)
    topic = synthesize_topic(text, memory_types=types, entities=entities)
    assert topic.startswith("[decision]")


def test_topic_includes_entities_suffix() -> None:
    text = "The Genesis-Seeds project shipped today."
    types = detect_memory_types(text)
    entities = detect_entities(text)
    topic = synthesize_topic(text, memory_types=types, entities=entities)
    assert "Genesis-Seeds" in topic


def test_topic_truncates_long_text() -> None:
    text = "x " * 500  # 1000 chars
    topic = synthesize_topic(text, memory_types=[], entities=[], max_chars=100)
    assert len(topic) <= 105  # allow room for ellipsis


def test_topic_empty_text_handled() -> None:
    topic = synthesize_topic("", memory_types=[], entities=[])
    assert topic == "(empty)"


# ─── Triple extraction ──────────────────────────────────────────────────────


def test_triple_uses_pattern() -> None:
    text = "Sovereign-Agent uses Ollama for inference."
    triples = extract_triples(text)
    found = [(t.subject, t.predicate, t.object) for t in triples]
    assert any(p == "uses" for s, p, o in found)


def test_triple_supersedes_pattern() -> None:
    text = "PalaceV2 supersedes PalaceV1 entirely."
    triples = extract_triples(text)
    assert any(t.predicate == "supersedes" for t in triples)


def test_triple_max_limit() -> None:
    text = " ".join(f"ProjectA{i} uses LibraryB{i}." for i in range(20))
    triples = extract_triples(text, max_triples=3)
    assert len(triples) <= 3


def test_triple_skips_self_reference() -> None:
    text = "Foo uses Foo and Bar uses Bar."
    triples = extract_triples(text)
    for t in triples:
        assert t.subject != t.object


def test_triple_empty_text() -> None:
    assert extract_triples("") == []


# ─── mine_atom (top-level) ─────────────────────────────────────────────────


def test_mine_atom_returns_full_result() -> None:
    text = (
        "We decided to use Postgres for Genesis-Seeds. "
        "It works beautifully. Genesis-Seeds uses Ollama too."
    )
    result = mine_atom("atom-test-1", text)
    assert result.atom_id == "atom-test-1"
    assert "[decision]" in result.topic or "[milestone]" in result.topic
    assert any("Genesis-Seeds" in e for e in result.entities)
    type_names = {m.memory_type for m in result.memory_types}
    assert "decision" in type_names or "milestone" in type_names


def test_mine_atom_empty_input() -> None:
    result = mine_atom("atom-empty", "")
    assert result.atom_id == "atom-empty"
    assert result.entities == []
    assert result.memory_types == []
    assert result.triples == []


# ─── Stable id generation ──────────────────────────────────────────────────


def test_closet_id_is_deterministic() -> None:
    assert closet_id_for_atom("atom-abc") == closet_id_for_atom("atom-abc")
    assert closet_id_for_atom("atom-abc") != closet_id_for_atom("atom-def")


def test_entity_id_is_deterministic() -> None:
    assert entity_id_for_name("Genesis-Seeds") == entity_id_for_name("Genesis-Seeds")
    # Different names → different ids
    assert entity_id_for_name("Genesis-Seeds") != entity_id_for_name("Genesis Seeds")


def test_entity_id_handles_special_chars() -> None:
    eid = entity_id_for_name("PEIG-Brotherhood (main)")
    assert eid.startswith("entity-")
    # No special chars in result
    assert all(c.isalnum() or c == "-" for c in eid)


def test_triple_id_is_deterministic() -> None:
    a = triple_id_for("e-1", "uses", "e-2")
    b = triple_id_for("e-1", "uses", "e-2")
    c = triple_id_for("e-1", "uses", "e-3")
    assert a == b
    assert a != c


# ─── Palace-mine planner ──────────────────────────────────────────────────


def test_palace_mine_planner_requires_room_id() -> None:
    p = PalaceMinePlanner()
    with pytest.raises(PlannerError, match="room_id"):
        p.plan(room_name="X")


def test_palace_mine_planner_requires_room_name() -> None:
    p = PalaceMinePlanner()
    with pytest.raises(PlannerError, match="room_name"):
        p.plan(room_id="r1")


def test_palace_mine_planner_no_atoms_raises(monkeypatch, tmp_path: Path) -> None:
    """When atoms.db is empty, planner raises a clear error."""
    # Point everything at a tmp dir
    from sovereign_agent.config import SETTINGS, Paths
    new_paths = Paths(config_dir=tmp_path / "cfg", data_dir=tmp_path / "data")
    object.__setattr__(SETTINGS, "paths", new_paths)
    SETTINGS.paths.ensure()

    # Create empty atoms.db via the normal path
    from sovereign_agent.db import open_atoms_db
    conn = open_atoms_db()
    conn.close()

    p = PalaceMinePlanner()
    with pytest.raises(PlannerError, match="no atoms to mine"):
        p.plan(room_id="r1", room_name="One")


def test_palace_mine_planner_creates_steps_for_atoms(
    monkeypatch, tmp_path: Path,
) -> None:
    """Plan walks atoms.db and emits one step per HEAD atom."""
    from sovereign_agent.config import SETTINGS, Paths
    new_paths = Paths(config_dir=tmp_path / "cfg", data_dir=tmp_path / "data")
    object.__setattr__(SETTINGS, "paths", new_paths)
    SETTINGS.paths.ensure()

    from sovereign_agent.db import open_atoms_db
    conn = open_atoms_db()
    try:
        # Insert 3 atoms — one is superseded, should be skipped
        for i in range(3):
            conn.execute(
                "INSERT INTO atoms(atom_id, type, summary, content_ref, claims, "
                "parents, confidence, created_at, created_by, superseded_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    f"atom-{i}", "fact",
                    f"summary {i}: We decided to use Postgres.",
                    '{"kind": "inline"}', "[]", "[]",
                    1.0, "2026-05-01T00:00:00Z", '{"actor": "test"}',
                    None if i < 2 else "2026-05-02T00:00:00Z",  # last one superseded
                ),
            )
    finally:
        conn.close()

    p = PalaceMinePlanner()
    result = p.plan(room_id="r1", room_name="One")
    # Only HEAD atoms (2 of 3)
    assert len(result.steps) == 2
    assert all(s.kind == "palace_mine_atom" for s in result.steps)
    assert all(s.required_model == "none" for s in result.steps)
    assert all(s.args["room_id"] == "r1" for s in result.steps)


def test_execute_palace_mine_step_writes_to_palace(tmp_path: Path) -> None:
    """End-to-end: run the executor on a real atom, see closet+triples land."""
    from sovereign_agent.config import SETTINGS, Paths
    new_paths = Paths(config_dir=tmp_path / "cfg", data_dir=tmp_path / "data")
    object.__setattr__(SETTINGS, "paths", new_paths)
    SETTINGS.paths.ensure()

    # Insert a real atom
    from sovereign_agent.db import open_atoms_db
    conn = open_atoms_db()
    try:
        conn.execute(
            "INSERT INTO atoms(atom_id, type, summary, content_ref, claims, "
            "parents, confidence, created_at, created_by) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "atom-research-1", "fact",
                "We decided to ship Genesis-Seeds. "
                "It works beautifully. Genesis-Seeds uses Ollama.",
                '{"kind": "inline"}', "[]", "[]",
                1.0, "2026-05-01T00:00:00Z", '{"actor": "test"}',
            ),
        )
    finally:
        conn.close()

    # Create the room first (the planner does this; we replicate for unit test)
    from sovereign_agent.palace import open_palace
    p = open_palace()
    try:
        p.create_room(room_id="r1", name="One")
    finally:
        p.close()

    # Execute
    step = Step(
        id=0, kind="palace_mine_atom",
        args={"atom_id": "atom-research-1", "room_id": "r1"},
        required_model="none",
    )
    result_line = execute_palace_mine_step(step)
    assert "atom-research-1" in result_line
    assert "closet=" in result_line

    # Verify palace has the closet + entities + at least one triple
    p = open_palace()
    try:
        closets = p.list_closets(room_id="r1")
        assert len(closets) == 1
        c = closets[0]
        assert c.atom_ids == ["atom-research-1"]
        assert len(c.entities) > 0  # "Genesis-Seeds" should be detected

        stats = p.stats()
        assert stats["closets"] == 1
        assert stats["entities"] >= 1
    finally:
        p.close()


def test_execute_palace_mine_step_idempotent(tmp_path: Path) -> None:
    """Re-mining the same atom doesn't duplicate closets or entities.

    Deterministic ids + INSERT OR REPLACE = re-running is safe.
    """
    from sovereign_agent.config import SETTINGS, Paths
    new_paths = Paths(config_dir=tmp_path / "cfg", data_dir=tmp_path / "data")
    object.__setattr__(SETTINGS, "paths", new_paths)
    SETTINGS.paths.ensure()

    from sovereign_agent.db import open_atoms_db
    conn = open_atoms_db()
    try:
        conn.execute(
            "INSERT INTO atoms(atom_id, type, summary, content_ref, claims, "
            "parents, confidence, created_at, created_by) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "atom-x", "fact", "Genesis-Seeds is the project.",
                '{"kind": "inline"}', "[]", "[]",
                1.0, "2026-05-01T00:00:00Z", '{"actor": "test"}',
            ),
        )
    finally:
        conn.close()

    from sovereign_agent.palace import open_palace
    p = open_palace()
    try:
        p.create_room(room_id="r1", name="One")
    finally:
        p.close()

    step = Step(
        id=0, kind="palace_mine_atom",
        args={"atom_id": "atom-x", "room_id": "r1"},
        required_model="none",
    )
    execute_palace_mine_step(step)
    execute_palace_mine_step(step)  # again
    execute_palace_mine_step(step)  # again

    p = open_palace()
    try:
        stats = p.stats()
        # One atom, mined three times → still one closet
        assert stats["closets"] == 1
    finally:
        p.close()


def test_execute_palace_mine_step_atom_missing_raises(tmp_path: Path) -> None:
    from sovereign_agent.config import SETTINGS, Paths
    new_paths = Paths(config_dir=tmp_path / "cfg", data_dir=tmp_path / "data")
    object.__setattr__(SETTINGS, "paths", new_paths)
    SETTINGS.paths.ensure()

    from sovereign_agent.db import open_atoms_db
    conn = open_atoms_db()
    conn.close()

    from sovereign_agent.palace import open_palace
    p = open_palace()
    try:
        p.create_room(room_id="r1", name="One")
    finally:
        p.close()

    step = Step(
        id=0, kind="palace_mine_atom",
        args={"atom_id": "atom-doesnt-exist", "room_id": "r1"},
        required_model="none",
    )
    with pytest.raises(ValueError, match="not found"):
        execute_palace_mine_step(step)


# ─── Registry has the new planner ──────────────────────────────────────────


def test_registry_includes_palace_mine() -> None:
    from sovereign_agent.planners import REGISTRY
    assert "palace-mine" in REGISTRY


# ─── CLI integration ──────────────────────────────────────────────────────


from typer.testing import CliRunner
from sovereign_agent.cli import app, ExitCode


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def test_cli_plan_palace_mine_help(runner: CliRunner) -> None:
    """The new flags should show up in plan --help."""
    r = runner.invoke(app, ["plan", "--help"])
    assert r.exit_code == ExitCode.OK
    assert "--room-id" in r.stdout
    assert "--room-name" in r.stdout


def test_cli_plan_palace_mine_no_atoms(runner: CliRunner, tmp_path: Path) -> None:
    """Planning palace-mine with no atoms returns USAGE error."""
    cfg, data = tmp_path / "cfg", tmp_path / "data"
    runner.invoke(app, ["--config-dir", str(cfg), "--data-dir", str(data), "init"])

    r = runner.invoke(app, [
        "--config-dir", str(cfg), "--data-dir", str(data),
        "plan", "palace-mine",
        "--room-id", "r1", "--room-name", "One",
    ])
    assert r.exit_code == ExitCode.USAGE
    assert "no atoms" in r.stderr.lower() or "no atoms" in r.stdout.lower()


def test_cli_plan_palace_mine_lists_in_planners(runner: CliRunner) -> None:
    """palace-mine should appear in the planners listing."""
    r = runner.invoke(app, ["--json", "plan"])
    assert r.exit_code == ExitCode.OK
    import json
    payload = json.loads(r.stdout)
    names = {p["name"] for p in payload["planners"]}
    assert "palace-mine" in names
