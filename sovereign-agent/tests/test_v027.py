"""Tests for v0.2.7 additions: timing observability, internet gating, palace."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from sovereign_agent.continuation import (
    Continuation,
    ContinuationStore,
    Step,
    format_elapsed,
)
from sovereign_agent.palace import (
    Closet,
    Entity,
    Palace,
    Triple,
    TripleConstraintError,
    _cosine,
    open_palace,
)
from sovereign_agent.tools.web_search import (
    _parse_ddg_html,
    _unwrap_ddg_redirect,
    internet_available,
    reset_internet_cache,
)


# ─── Timing observability ──────────────────────────────────────────────────


@pytest.mark.parametrize("seconds, expected", [
    (None, "—"),
    (0.42, "0.42s"),
    (12.7, "12.70s"),
    (59.99, "59.99s"),
    (60, "1m 0s"),
    (90, "1m 30s"),
    (3599, "59m 59s"),
    (3600, "1h 0m 0s"),
    (3725, "1h 2m 5s"),
    (7200, "2h 0m 0s"),
])
def test_format_elapsed(seconds, expected):
    assert format_elapsed(seconds) == expected


def test_step_elapsed_seconds_default_none() -> None:
    s = Step(id=0, kind="x")
    assert s.elapsed_seconds is None


def test_step_elapsed_seconds_persists_through_yaml(tmp_path: Path) -> None:
    store = ContinuationStore(tmp_path / "c")
    cont = store.create(
        goal="t", planner="p", planner_args={},
        steps=[Step(id=0, kind="x", elapsed_seconds=12.345)],
    )
    fetched = store.get(cont.task_id)
    assert fetched.steps[0].elapsed_seconds == 12.345


def test_v026_continuation_with_no_elapsed_seconds_loads(tmp_path: Path) -> None:
    """A v0.2.6 file without elapsed_seconds field must still load (None)."""
    import yaml
    store = ContinuationStore(tmp_path / "c")
    store.ensure_root()
    legacy = {
        "task_id": "cont-old",
        "goal": "g", "planner": "p",
        "status": "planned",
        "steps": [
            {"id": 0, "kind": "x", "status": "pending",
             "required_model": "orchestrator"},
        ],
    }
    (store.root / "cont-old.yaml").write_text(yaml.safe_dump(legacy))
    cont = store.get("cont-old")
    assert cont.steps[0].elapsed_seconds is None


def test_continuation_total_elapsed_sums_correctly() -> None:
    cont = Continuation(task_id="t", goal="g", planner="p", steps=[
        Step(id=0, kind="a", elapsed_seconds=10.5),
        Step(id=1, kind="b", elapsed_seconds=20.5),
        Step(id=2, kind="c", elapsed_seconds=None),
    ])
    assert cont.total_elapsed_seconds == 31.0


def test_continuation_elapsed_by_model() -> None:
    cont = Continuation(task_id="t", goal="g", planner="p", steps=[
        Step(id=0, kind="a", required_model="orchestrator", elapsed_seconds=10),
        Step(id=1, kind="b", required_model="orchestrator", elapsed_seconds=15),
        Step(id=2, kind="c", required_model="vision", elapsed_seconds=30),
        Step(id=3, kind="d", required_model="vision", elapsed_seconds=None),
    ])
    e = cont.elapsed_by_model()
    assert e["orchestrator"] == 25.0
    assert e["vision"] == 30.0


# ─── Internet gating / web_search ───────────────────────────────────────────


def test_internet_off_setting_short_circuits(monkeypatch: pytest.MonkeyPatch) -> None:
    reset_internet_cache()
    monkeypatch.setenv("AGENT_INTERNET", "off")
    assert internet_available() is False


def test_internet_on_setting_short_circuits(monkeypatch: pytest.MonkeyPatch) -> None:
    reset_internet_cache()
    monkeypatch.setenv("AGENT_INTERNET", "on")
    assert internet_available() is True


def test_internet_cache_returns_same_result(monkeypatch: pytest.MonkeyPatch) -> None:
    """Repeated calls should return cached result."""
    reset_internet_cache()
    monkeypatch.setenv("AGENT_INTERNET", "off")
    assert internet_available() is False
    # Even if we change the env, the cache holds.
    monkeypatch.setenv("AGENT_INTERNET", "on")
    assert internet_available() is False  # still cached as False
    reset_internet_cache()
    assert internet_available() is True


def test_unwrap_ddg_redirect_handles_wrapped() -> None:
    wrapped = "/l/?kh=-1&uddg=https%3A%2F%2Fexample.com%2Fpage"
    assert _unwrap_ddg_redirect(wrapped) == "https://example.com/page"


def test_unwrap_ddg_redirect_passes_through_unwrapped() -> None:
    assert _unwrap_ddg_redirect("https://example.com/page") == "https://example.com/page"


def test_parse_ddg_html_extracts_results() -> None:
    """Smoke test the regex parser against a representative HTML fragment."""
    html = """
    <div class="result">
      <a class="result__a" href="/l/?uddg=https%3A%2F%2Fexample.com%2Fa">Title A</a>
      <a class="result__snippet" href="/l/?uddg=https%3A%2F%2Fexample.com%2Fa">Snippet A about things</a>
    </div>
    <div class="result">
      <a class="result__a" href="/l/?uddg=https%3A%2F%2Fexample.com%2Fb">Title B with <b>bold</b></a>
      <a class="result__snippet" href="/l/?uddg=https%3A%2F%2Fexample.com%2Fb">Snippet B</a>
    </div>
    """
    results = _parse_ddg_html(html, max_results=5)
    assert len(results) == 2
    assert results[0]["url"] == "https://example.com/a"
    assert results[0]["title"] == "Title A"
    assert results[0]["snippet"] == "Snippet A about things"
    assert "bold" in results[1]["title"]
    assert "<b>" not in results[1]["title"]


def test_parse_ddg_html_respects_max_results() -> None:
    html = "".join(
        f'<a class="result__a" href="/l/?uddg=https%3A%2F%2Fe.com%2F{i}">T{i}</a>'
        for i in range(10)
    )
    results = _parse_ddg_html(html, max_results=3)
    assert len(results) == 3


def test_parse_ddg_html_skips_non_http_urls() -> None:
    html = (
        '<a class="result__a" href="javascript:alert(1)">bad</a>'
        '<a class="result__a" href="/l/?uddg=https%3A%2F%2Fok.com%2F">good</a>'
    )
    results = _parse_ddg_html(html, max_results=10)
    assert len(results) == 1
    assert results[0]["url"] == "https://ok.com/"


# ─── Palace ────────────────────────────────────────────────────────────────


@pytest.fixture
def palace(tmp_path: Path) -> Palace:
    p = Palace(tmp_path / "palace.db")
    yield p
    p.close()


def test_create_room_round_trip(palace: Palace) -> None:
    room = palace.create_room(
        room_id="room-research",
        name="Research Notes",
        description="long-form research outputs",
        schema={"slots": ["hypothesis", "method", "result"]},
    )
    fetched = palace.get_room("room-research")
    assert fetched.id == room.id
    assert fetched.name == "Research Notes"
    assert fetched.schema == {"slots": ["hypothesis", "method", "result"]}


def test_list_rooms(palace: Palace) -> None:
    palace.create_room(room_id="r1", name="One")
    palace.create_room(room_id="r2", name="Two")
    rooms = palace.list_rooms()
    assert {r.id for r in rooms} == {"r1", "r2"}


def test_add_closet_and_list(palace: Palace) -> None:
    palace.create_room(room_id="r1", name="One")
    closet = Closet(
        id="closet-001", room_id="r1", topic="quantum coherence experiments",
        entities=["quantum", "coherence"], atom_ids=["atom-1", "atom-2"],
        embedding=[0.1, 0.2, 0.3],
    )
    palace.add_closet(closet)
    listed = palace.list_closets(room_id="r1")
    assert len(listed) == 1
    assert listed[0].id == "closet-001"
    assert listed[0].entities == ["quantum", "coherence"]
    assert listed[0].atom_ids == ["atom-1", "atom-2"]
    assert listed[0].embedding == [0.1, 0.2, 0.3]


def test_purge_closets_for_file(palace: Palace) -> None:
    palace.create_room(room_id="r1", name="One")
    for i in range(3):
        palace.add_closet(Closet(
            id=f"closet-{i}", room_id="r1", topic=f"topic {i}",
            entities=[], atom_ids=[], source_file="/tmp/notes.md",
        ))
    palace.add_closet(Closet(
        id="closet-other", room_id="r1", topic="other",
        entities=[], atom_ids=[], source_file="/tmp/other.md",
    ))
    removed = palace.purge_closets_for_file("/tmp/notes.md")
    assert removed == 3
    remaining = palace.list_closets()
    assert len(remaining) == 1
    assert remaining[0].id == "closet-other"


def test_keyword_search_matches_topic(palace: Palace) -> None:
    palace.create_room(room_id="r1", name="One")
    palace.add_closet(Closet(
        id="c1", room_id="r1", topic="quantum coherence in biology",
        entities=["quantum"], atom_ids=["a1"],
    ))
    palace.add_closet(Closet(
        id="c2", room_id="r1", topic="entropy gravity coupling",
        entities=["entropy"], atom_ids=["a2"],
    ))
    hits = palace.search_closets_keyword("quantum")
    assert len(hits) == 1
    assert hits[0].id == "c1"


def test_keyword_search_matches_entity(palace: Palace) -> None:
    palace.create_room(room_id="r1", name="One")
    palace.add_closet(Closet(
        id="c1", room_id="r1", topic="general topic",
        entities=["Genesis-Seeds", "MONETTE"], atom_ids=[],
    ))
    hits = palace.search_closets_keyword("genesis")
    assert len(hits) == 1


def test_semantic_search_orders_by_cosine_similarity(palace: Palace) -> None:
    palace.create_room(room_id="r1", name="One")
    # Create two closets with embeddings close to / far from a query.
    palace.add_closet(Closet(
        id="near", room_id="r1", topic="near",
        entities=[], atom_ids=[],
        embedding=[1.0, 0.0, 0.0],
    ))
    palace.add_closet(Closet(
        id="far", room_id="r1", topic="far",
        entities=[], atom_ids=[],
        embedding=[0.0, 1.0, 0.0],
    ))
    query = [0.9, 0.1, 0.0]
    results = palace.search_closets_semantic(query)
    assert len(results) == 2
    # 'near' should rank first.
    assert results[0][0].id == "near"
    assert results[0][1] > results[1][1]


def test_cosine_function() -> None:
    assert _cosine([1, 0, 0], [1, 0, 0]) == pytest.approx(1.0)
    assert _cosine([1, 0, 0], [0, 1, 0]) == pytest.approx(0.0)
    assert _cosine([1, 0, 0], [-1, 0, 0]) == pytest.approx(-1.0)
    assert _cosine([], [1, 0]) == 0.0  # empty
    assert _cosine([1, 2, 3], [4, 5]) == 0.0  # mismatched length


def test_upsert_entity_creates_then_updates(palace: Palace) -> None:
    e1 = Entity(id="e-max", name="Max", type="person")
    palace.upsert_entity(e1)
    e2 = Entity(id="e-max", name="Maximilian", type="person",
                properties={"role": "researcher"})
    palace.upsert_entity(e2)
    fetched = palace.get_entity("e-max")
    assert fetched.name == "Maximilian"
    assert fetched.properties == {"role": "researcher"}


def test_add_triple_with_object_id(palace: Palace) -> None:
    palace.upsert_entity(Entity(id="e-max", name="Max"))
    palace.upsert_entity(Entity(id="e-alice", name="Alice"))
    triple = Triple(
        id="t-1", subject_id="e-max", predicate="child_of",
        object_id="e-alice", valid_from="2015-04-01",
    )
    palace.add_triple(triple)
    found = palace.query_subject("e-max")
    assert len(found) == 1
    assert found[0].object_id == "e-alice"


def test_add_triple_with_object_literal(palace: Palace) -> None:
    palace.upsert_entity(Entity(id="e-max", name="Max"))
    triple = Triple(
        id="t-1", subject_id="e-max", predicate="loves",
        object_literal="chess",
    )
    palace.add_triple(triple)
    found = palace.query_subject("e-max")
    assert found[0].object_literal == "chess"
    assert found[0].object_id is None


def test_add_triple_without_either_object_raises(palace: Palace) -> None:
    palace.upsert_entity(Entity(id="e-max", name="Max"))
    with pytest.raises(TripleConstraintError):
        palace.add_triple(Triple(
            id="t-1", subject_id="e-max", predicate="loves",
        ))


def test_add_triple_with_both_object_id_and_literal_raises(palace: Palace) -> None:
    palace.upsert_entity(Entity(id="e-max", name="Max"))
    palace.upsert_entity(Entity(id="e-other", name="Other"))
    with pytest.raises(TripleConstraintError):
        palace.add_triple(Triple(
            id="t-1", subject_id="e-max", predicate="loves",
            object_id="e-other", object_literal="also chess",
        ))


def test_query_subject_as_of_filters_temporal(palace: Palace) -> None:
    palace.upsert_entity(Entity(id="e-max", name="Max"))
    palace.add_triple(Triple(
        id="t-old", subject_id="e-max", predicate="lives_in",
        object_literal="Brooklyn",
        valid_from="2020-01-01", valid_to="2024-06-01",
    ))
    palace.add_triple(Triple(
        id="t-new", subject_id="e-max", predicate="lives_in",
        object_literal="Berlin",
        valid_from="2024-06-01",
    ))
    # As of January 2023: should see Brooklyn only
    triples_2023 = palace.query_subject("e-max", as_of="2023-01-15")
    addrs = {t.object_literal for t in triples_2023}
    assert addrs == {"Brooklyn"}
    # As of January 2025: should see Berlin only
    triples_2025 = palace.query_subject("e-max", as_of="2025-01-15")
    addrs = {t.object_literal for t in triples_2025}
    assert addrs == {"Berlin"}
    # No filter: both
    all_triples = palace.query_subject("e-max")
    assert len(all_triples) == 2


def test_invalidate_triple_sets_valid_to(palace: Palace) -> None:
    palace.upsert_entity(Entity(id="e", name="E"))
    palace.add_triple(Triple(
        id="t-1", subject_id="e", predicate="has", object_literal="thing",
    ))
    assert palace.invalidate_triple("t-1", ended="2026-05-01") is True
    triples = palace.query_subject("e", as_of="2026-06-01")
    assert len(triples) == 0  # no longer valid as of that date


def test_palace_stats(palace: Palace) -> None:
    palace.create_room(room_id="r1", name="One")
    palace.add_closet(Closet(id="c1", room_id="r1", topic="t",
                             entities=[], atom_ids=[]))
    palace.upsert_entity(Entity(id="e1", name="E"))
    palace.add_triple(Triple(id="tr1", subject_id="e1",
                             predicate="p", object_literal="o"))
    s = palace.stats()
    assert s["rooms"] == 1
    assert s["closets"] == 1
    assert s["entities"] == 1
    assert s["triples"] == 1
    assert s["active_triples"] == 1


# ─── CLI integration: palace commands ───────────────────────────────────────


from typer.testing import CliRunner
from sovereign_agent.cli import app, ExitCode


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def test_palace_cli_stats_works_on_empty_palace(
    runner: CliRunner, tmp_path: Path
) -> None:
    cfg, data = tmp_path / "cfg", tmp_path / "data"
    runner.invoke(app, ["--config-dir", str(cfg), "--data-dir", str(data), "init"])
    r = runner.invoke(app, [
        "--config-dir", str(cfg), "--data-dir", str(data), "--json",
        "palace", "stats",
    ])
    assert r.exit_code == ExitCode.OK, r.stderr
    import json
    payload = json.loads(r.stdout)
    assert payload["rooms"] == 0
    assert payload["closets"] == 0


def test_palace_cli_create_and_list_rooms(runner: CliRunner, tmp_path: Path) -> None:
    cfg, data = tmp_path / "cfg", tmp_path / "data"
    runner.invoke(app, ["--config-dir", str(cfg), "--data-dir", str(data), "init"])
    r = runner.invoke(app, [
        "--config-dir", str(cfg), "--data-dir", str(data),
        "palace", "create-room", "room-test", "Test Room",
        "--description", "for testing",
    ])
    assert r.exit_code == ExitCode.OK, r.stderr
    r = runner.invoke(app, [
        "--config-dir", str(cfg), "--data-dir", str(data), "--json",
        "palace", "rooms",
    ])
    assert r.exit_code == ExitCode.OK
    import json
    payload = json.loads(r.stdout)
    assert any(r["id"] == "room-test" for r in payload["rooms"])
