"""Tests for v0.2.9: self-reflection loop + MOS canon ingestion."""
from __future__ import annotations

from pathlib import Path

import pytest


# ─── Proposal store ─────────────────────────────────────────────────────────


def test_proposal_create_and_get(tmp_path: Path) -> None:
    from sovereign_agent.proposals import ProposalStore

    store = ProposalStore(tmp_path / "p")
    p = store.create(
        kind="clean",
        title="Test cleanup",
        action={"type": "remove_triple", "triple_id": "t-123"},
        rationale="Triple is orphaned.",
    )
    assert p.id.startswith("prop-")
    assert p.status == "pending"
    fetched = store.get(p.id)
    assert fetched.title == "Test cleanup"
    assert fetched.action["triple_id"] == "t-123"


def test_proposal_invalid_kind_raises(tmp_path: Path) -> None:
    from sovereign_agent.proposals import ProposalError, ProposalStore

    store = ProposalStore(tmp_path / "p")
    with pytest.raises(ProposalError, match="invalid kind"):
        store.create(kind="bogus", title="x", action={})  # type: ignore[arg-type]


def test_proposal_list_filters(tmp_path: Path) -> None:
    from sovereign_agent.proposals import ProposalStore

    store = ProposalStore(tmp_path / "p")
    p1 = store.create(kind="clean", title="A", action={"type": "x"})
    p2 = store.create(kind="insight", title="B", action={"type": "y"})
    p3 = store.create(kind="clean", title="C", action={"type": "z"})

    cleans = store.list_all(kind="clean")
    assert {p.id for p in cleans} == {p1.id, p3.id}

    pending = store.list_all(status="pending")
    assert len(pending) == 3


def test_proposal_approve_signs_with_hmac(tmp_path: Path) -> None:
    from sovereign_agent.proposals import ProposalStore, verify_signature

    secret = b"test-secret-32-bytes-long-12345678"
    store = ProposalStore(tmp_path / "p")
    p = store.create(kind="clean", title="X",
                     action={"type": "remove_triple", "triple_id": "t-1"})
    approved = store.approve(p.id, secret=secret, approved_by="op")
    assert approved.status == "approved"
    assert approved.signature is not None
    assert verify_signature(approved, secret=secret)


def test_proposal_signature_fails_after_action_tamper(tmp_path: Path) -> None:
    """If the action is edited after approval, the signature must NOT verify."""
    from sovereign_agent.proposals import (
        ProposalStore, _atomic_write_yaml, _to_yaml_dict, verify_signature,
    )

    secret = b"k" * 32
    store = ProposalStore(tmp_path / "p")
    p = store.create(kind="clean", title="X",
                     action={"type": "remove_triple", "triple_id": "t-1"})
    store.approve(p.id, secret=secret)

    # Manually edit the YAML to change the action — simulating tamper
    fetched = store.get(p.id)
    fetched.action["triple_id"] = "t-DIFFERENT"
    _atomic_write_yaml(store._path(p.id), _to_yaml_dict(fetched))

    tampered = store.get(p.id)
    assert verify_signature(tampered, secret=secret) is False


def test_proposal_approve_requires_pending_state(tmp_path: Path) -> None:
    from sovereign_agent.proposals import (
        ProposalNotApprovable, ProposalStore,
    )

    secret = b"k" * 32
    store = ProposalStore(tmp_path / "p")
    p = store.create(kind="clean", title="X", action={"type": "remove_triple", "triple_id": "t"})
    store.reject(p.id)
    with pytest.raises(ProposalNotApprovable):
        store.approve(p.id, secret=secret)


def test_proposal_mark_applied_records_rollback(tmp_path: Path) -> None:
    from sovereign_agent.proposals import ProposalStore

    secret = b"k" * 32
    store = ProposalStore(tmp_path / "p")
    p = store.create(kind="clean", title="X", action={"type": "remove_triple", "triple_id": "t-9"})
    store.approve(p.id, secret=secret)
    applied = store.mark_applied(
        p.id,
        result="invalidated triple t-9",
        rollback={"type": "restore_triple", "triple_id": "t-9", "valid_to": None},
    )
    assert applied.status == "applied"
    assert applied.rollback["triple_id"] == "t-9"
    assert applied.applied_at is not None


# ─── Palace scan ────────────────────────────────────────────────────────────


def test_scan_empty_palace_is_empty(tmp_path: Path) -> None:
    from sovereign_agent.palace import Palace
    from sovereign_agent.palace_scan import scan_palace

    p = Palace(tmp_path / "pal.db")
    try:
        u = scan_palace(p)
    finally:
        p.close()
    assert u.is_empty()
    assert u.counts.closets == 0
    assert u.counts.entities == 0


def test_scan_detects_orphan_closet(tmp_path: Path) -> None:
    from sovereign_agent.palace import Closet, Palace
    from sovereign_agent.palace_scan import scan_palace

    p = Palace(tmp_path / "pal.db")
    try:
        p.create_room(room_id="r1", name="One")
        # closet with empty atom_ids
        p.add_closet(Closet(
            id="c-orphan", room_id="r1", topic="t",
            entities=[], atom_ids=[],
        ))
        # non-orphan
        p.add_closet(Closet(
            id="c-ok", room_id="r1", topic="t2",
            entities=[], atom_ids=["atom-1"],
        ))
        u = scan_palace(p)
    finally:
        p.close()
    assert "c-orphan" in u.orphans.orphan_closets
    assert "c-ok" not in u.orphans.orphan_closets


def test_scan_detects_self_referential_triple(tmp_path: Path) -> None:
    from sovereign_agent.palace import Entity, Palace, Triple
    from sovereign_agent.palace_scan import scan_palace

    p = Palace(tmp_path / "pal.db")
    try:
        p.upsert_entity(Entity(id="e1", name="One"))
        p.add_triple(Triple(
            id="t-self", subject_id="e1", predicate="loves", object_id="e1",
        ))
        u = scan_palace(p)
    finally:
        p.close()
    assert "t-self" in u.suspicion.self_referential


def test_scan_detects_low_confidence(tmp_path: Path) -> None:
    from sovereign_agent.palace import Entity, Palace, Triple
    from sovereign_agent.palace_scan import scan_palace

    p = Palace(tmp_path / "pal.db")
    try:
        p.upsert_entity(Entity(id="e1", name="One"))
        p.add_triple(Triple(
            id="t-bad", subject_id="e1", predicate="x",
            object_literal="thing", confidence=0.2,
        ))
        p.add_triple(Triple(
            id="t-ok", subject_id="e1", predicate="x",
            object_literal="thing2", confidence=0.8,
        ))
        u = scan_palace(p)
    finally:
        p.close()
    assert "t-bad" in u.suspicion.low_confidence
    assert "t-ok" not in u.suspicion.low_confidence


def test_render_understanding_markdown_handles_empty(tmp_path: Path) -> None:
    from sovereign_agent.palace import Palace
    from sovereign_agent.palace_scan import render_understanding_markdown, scan_palace

    p = Palace(tmp_path / "pal.db")
    try:
        u = scan_palace(p)
    finally:
        p.close()
    md = render_understanding_markdown(u)
    assert "Palace is empty" in md or "rooms: **0**" in md


# ─── MOS canon ──────────────────────────────────────────────────────────────


def test_mos_canon_has_all_clauses_with_adaptive_framing() -> None:
    from sovereign_agent.mos_canon import (
        ADAPTIVE_FRAMING, ALL_CLAUSES,
    )

    assert len(ALL_CLAUSES) > 10  # we shipped a meaningful subset
    for c in ALL_CLAUSES:
        # Every clause must have leverage + modulation framings
        assert c.leverage, f"clause {c.id} missing leverage"
        assert c.modulation, f"clause {c.id} missing modulation"
        # The adaptive framing string is consistent
        assert c.adaptive_framing() == ADAPTIVE_FRAMING


def test_mos_canon_priority_stack_present() -> None:
    from sovereign_agent.mos_canon import get_clause

    c = get_clause("mos-priority-stack")
    assert c is not None
    assert c.part == "kernel"
    assert "Safety" in c.principle


def test_mos_canon_search_finds_matches() -> None:
    from sovereign_agent.mos_canon import search_clauses

    results = search_clauses("rollback")
    assert any(c.id == "mos-rollback" for c in results)


def test_mos_canon_clauses_by_part() -> None:
    from sovereign_agent.mos_canon import clauses_by_part

    kernel = clauses_by_part("kernel")
    assert len(kernel) >= 3
    for c in kernel:
        assert c.part == "kernel"


# ─── MOS canon ingest planner + executor ───────────────────────────────────


def test_mos_canon_ingest_planner_emits_step_per_clause(tmp_path: Path) -> None:
    from sovereign_agent.config import SETTINGS, Paths
    from sovereign_agent.mos_canon import ALL_CLAUSES
    from sovereign_agent.planners.mos_canon_ingest import MOSCanonIngestPlanner

    new_paths = Paths(config_dir=tmp_path / "cfg", data_dir=tmp_path / "data")
    object.__setattr__(SETTINGS, "paths", new_paths)
    SETTINGS.paths.ensure()

    p = MOSCanonIngestPlanner()
    result = p.plan()
    assert len(result.steps) == len(ALL_CLAUSES)
    for s in result.steps:
        assert s.kind == "mos_canon_ingest_clause"
        assert s.required_model == "none"


def test_mos_canon_ingest_executor_writes_room_and_clauses(tmp_path: Path) -> None:
    from sovereign_agent.config import SETTINGS, Paths
    from sovereign_agent.continuation import Step
    from sovereign_agent.mos_canon import ALL_CLAUSES
    from sovereign_agent.palace import open_palace
    from sovereign_agent.planners.mos_canon_ingest import (
        execute_mos_canon_ingest_step,
    )

    new_paths = Paths(config_dir=tmp_path / "cfg", data_dir=tmp_path / "data")
    object.__setattr__(SETTINGS, "paths", new_paths)
    SETTINGS.paths.ensure()

    # Ingest first clause
    first = ALL_CLAUSES[0]
    step = Step(
        id=0, kind="mos_canon_ingest_clause",
        args={"clause_id": first.id}, required_model="none",
    )
    line = execute_mos_canon_ingest_step(step)
    assert first.id in line

    # Verify room and closet exist
    p = open_palace()
    try:
        room = p.get_room("room-mos-canon")
        assert room.name == "Unified MOS Canon (Adaptive)"
        assert "ADAPTIVE SKILL" in room.description
        closets = p.list_closets(room_id="room-mos-canon")
        assert any(f"closet-mos-{first.id}" == c.id for c in closets)
        # The clause-as-entity exists with framing in properties
        ent = p.get_entity(f"entity-mos-{first.id}")
        assert ent is not None
        assert "ADAPTIVE SKILL" in ent.properties.get("framing", "")
    finally:
        p.close()


def test_mos_canon_ingest_idempotent(tmp_path: Path) -> None:
    from sovereign_agent.config import SETTINGS, Paths
    from sovereign_agent.continuation import Step
    from sovereign_agent.mos_canon import ALL_CLAUSES
    from sovereign_agent.palace import open_palace
    from sovereign_agent.planners.mos_canon_ingest import (
        execute_mos_canon_ingest_step,
    )

    new_paths = Paths(config_dir=tmp_path / "cfg", data_dir=tmp_path / "data")
    object.__setattr__(SETTINGS, "paths", new_paths)
    SETTINGS.paths.ensure()

    first = ALL_CLAUSES[0]
    step = Step(id=0, kind="mos_canon_ingest_clause",
                args={"clause_id": first.id}, required_model="none")
    execute_mos_canon_ingest_step(step)
    execute_mos_canon_ingest_step(step)
    execute_mos_canon_ingest_step(step)

    p = open_palace()
    try:
        closets = p.list_closets(room_id="room-mos-canon")
        # Only one closet for this clause despite three runs
        matching = [c for c in closets if c.id == f"closet-mos-{first.id}"]
        assert len(matching) == 1
    finally:
        p.close()


# ─── Palace clean planner ──────────────────────────────────────────────────


def test_palace_clean_proposes_for_self_referential_triples(tmp_path: Path) -> None:
    from sovereign_agent.config import SETTINGS, Paths
    from sovereign_agent.continuation import Step
    from sovereign_agent.palace import Closet, Entity, open_palace, Triple
    from sovereign_agent.planners.palace_clean import (
        PalaceCleanPlanner, execute_palace_clean_step,
    )
    from sovereign_agent.proposals import open_store

    new_paths = Paths(config_dir=tmp_path / "cfg", data_dir=tmp_path / "data")
    object.__setattr__(SETTINGS, "paths", new_paths)
    SETTINGS.paths.ensure()

    # Set up a palace with a self-referential triple AND at least one valid closet
    # so it isn't "empty"
    p = open_palace()
    try:
        p.create_room(room_id="r1", name="One")
        p.add_closet(Closet(
            id="c-1", room_id="r1", topic="real",
            entities=[], atom_ids=["a-1"],
        ))
        p.upsert_entity(Entity(id="e-self", name="self"))
        p.add_triple(Triple(
            id="t-self", subject_id="e-self", predicate="x",
            object_id="e-self",
        ))
    finally:
        p.close()

    # Plan: should emit one step for the self-ref triple
    planner = PalaceCleanPlanner()
    result = planner.plan()
    assert len(result.steps) >= 1
    self_ref_step = next(
        (s for s in result.steps if "t-self" in s.args["title"]),
        None,
    )
    assert self_ref_step is not None
    assert self_ref_step.required_model == "none"

    # Execute: writes a proposal
    line = execute_palace_clean_step(self_ref_step)
    assert "proposal" in line

    store = open_store()
    proposals = store.list_all(status="pending", kind="clean")
    assert any("t-self" in p.title for p in proposals)


# ─── Palace apply: end-to-end approve → apply flow ─────────────────────────


def test_palace_apply_refuses_unapproved_proposal(tmp_path: Path) -> None:
    from sovereign_agent.config import SETTINGS, Paths
    from sovereign_agent.continuation import Step
    from sovereign_agent.planners.palace_apply import execute_palace_apply_step
    from sovereign_agent.proposals import (
        ProposalNotApprovable, open_store,
    )

    new_paths = Paths(config_dir=tmp_path / "cfg", data_dir=tmp_path / "data")
    object.__setattr__(SETTINGS, "paths", new_paths)
    SETTINGS.paths.ensure()

    store = open_store()
    p = store.create(
        kind="clean", title="X",
        action={"type": "remove_triple", "triple_id": "t-x"},
    )
    step = Step(id=0, kind="palace_apply_proposal",
                args={"proposal_id": p.id}, required_model="none")
    with pytest.raises(ProposalNotApprovable):
        execute_palace_apply_step(step)


def test_palace_apply_full_round_trip_clean_remove_triple(tmp_path: Path) -> None:
    """End-to-end: create proposal → approve → apply → palace mutated."""
    from sovereign_agent.approval import _load_or_create_secret
    from sovereign_agent.config import SETTINGS, Paths
    from sovereign_agent.continuation import Step
    from sovereign_agent.palace import Entity, open_palace, Triple
    from sovereign_agent.planners.palace_apply import execute_palace_apply_step
    from sovereign_agent.proposals import open_store

    new_paths = Paths(config_dir=tmp_path / "cfg", data_dir=tmp_path / "data")
    object.__setattr__(SETTINGS, "paths", new_paths)
    SETTINGS.paths.ensure()

    # Set up: a triple to remove
    palace = open_palace()
    try:
        palace.upsert_entity(Entity(id="e-1", name="One"))
        palace.add_triple(Triple(
            id="t-toremove", subject_id="e-1", predicate="loves",
            object_literal="thing",
        ))
    finally:
        palace.close()

    # Create + approve a proposal to invalidate it
    store = open_store()
    p = store.create(
        kind="clean", title="Remove t-toremove",
        action={"type": "remove_triple", "triple_id": "t-toremove"},
    )
    secret = _load_or_create_secret()
    store.approve(p.id, secret=secret)

    # Execute the apply step
    step = Step(id=0, kind="palace_apply_proposal",
                args={"proposal_id": p.id}, required_model="none")
    line = execute_palace_apply_step(step)
    assert "applied" in line

    # Verify: triple is invalidated, proposal status is applied, rollback recorded
    palace = open_palace()
    try:
        # Triple still exists but valid_to is set
        triples = palace.query_subject("e-1", as_of="2099-01-01")
        # Future query: triple should NOT appear because valid_to is set
        assert not any(t.id == "t-toremove" for t in triples)
    finally:
        palace.close()

    final = store.get(p.id)
    assert final.status == "applied"
    assert final.rollback is not None
    assert final.rollback["type"] == "restore_triple"


def test_palace_apply_refuses_tampered_proposal(tmp_path: Path) -> None:
    """If signature doesn't verify, apply must fail-loud."""
    from sovereign_agent.approval import _load_or_create_secret
    from sovereign_agent.config import SETTINGS, Paths
    from sovereign_agent.continuation import Step
    from sovereign_agent.palace import Entity, open_palace, Triple
    from sovereign_agent.planners.palace_apply import execute_palace_apply_step
    from sovereign_agent.proposals import (
        _atomic_write_yaml, _to_yaml_dict, open_store,
    )

    new_paths = Paths(config_dir=tmp_path / "cfg", data_dir=tmp_path / "data")
    object.__setattr__(SETTINGS, "paths", new_paths)
    SETTINGS.paths.ensure()

    palace = open_palace()
    try:
        palace.upsert_entity(Entity(id="e-1", name="One"))
        palace.add_triple(Triple(
            id="t-real", subject_id="e-1", predicate="x",
            object_literal="ok",
        ))
        palace.add_triple(Triple(
            id="t-bystander", subject_id="e-1", predicate="x",
            object_literal="other",
        ))
    finally:
        palace.close()

    store = open_store()
    p = store.create(
        kind="clean", title="Remove t-real",
        action={"type": "remove_triple", "triple_id": "t-real"},
    )
    secret = _load_or_create_secret()
    store.approve(p.id, secret=secret)

    # Tamper: change the action AFTER approval
    fetched = store.get(p.id)
    fetched.action["triple_id"] = "t-bystander"
    _atomic_write_yaml(store._path(p.id), _to_yaml_dict(fetched))

    step = Step(id=0, kind="palace_apply_proposal",
                args={"proposal_id": p.id}, required_model="none")
    with pytest.raises(ValueError, match="signature"):
        execute_palace_apply_step(step)

    # Both triples must still be active — t-bystander not invalidated
    palace = open_palace()
    try:
        triples = palace.query_subject("e-1", as_of="2099-01-01")
        ids = {t.id for t in triples}
        assert "t-bystander" in ids
    finally:
        palace.close()

    final = store.get(p.id)
    assert final.status == "failed"


# ─── Registry has the v0.2.9 planners ──────────────────────────────────────


def test_registry_includes_all_v029_planners() -> None:
    from sovereign_agent.planners import REGISTRY
    for name in (
        "palace-reflect", "palace-apply", "palace-clean", "mos-canon-ingest",
    ):
        assert name in REGISTRY


# ─── CLI integration ───────────────────────────────────────────────────────


from typer.testing import CliRunner
from sovereign_agent.cli import app, ExitCode


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def test_cli_palace_understanding_works_on_empty(runner: CliRunner, tmp_path: Path) -> None:
    cfg, data = tmp_path / "cfg", tmp_path / "data"
    runner.invoke(app, ["--config-dir", str(cfg), "--data-dir", str(data), "init"])
    r = runner.invoke(app, [
        "--config-dir", str(cfg), "--data-dir", str(data), "--json",
        "palace", "understanding",
    ])
    assert r.exit_code == ExitCode.OK
    import json
    payload = json.loads(r.stdout)
    assert payload["ok"] is True
    assert "understanding" in payload


def test_cli_proposals_list_empty(runner: CliRunner, tmp_path: Path) -> None:
    cfg, data = tmp_path / "cfg", tmp_path / "data"
    runner.invoke(app, ["--config-dir", str(cfg), "--data-dir", str(data), "init"])
    r = runner.invoke(app, [
        "--config-dir", str(cfg), "--data-dir", str(data), "--json",
        "proposals", "list",
    ])
    assert r.exit_code == ExitCode.OK
    import json
    payload = json.loads(r.stdout)
    assert payload["proposals"] == []


def test_cli_proposal_write_shows_in_list(runner: CliRunner, tmp_path: Path) -> None:
    """The proposal_write tool — exercised via the store API since the tool
    needs an async runtime — produces a proposal that 'proposals list' sees.
    """
    from sovereign_agent.config import SETTINGS, Paths
    from sovereign_agent.proposals import ProposalStore

    cfg, data = tmp_path / "cfg", tmp_path / "data"
    new_paths = Paths(config_dir=cfg, data_dir=data)
    object.__setattr__(SETTINGS, "paths", new_paths)
    SETTINGS.paths.ensure()

    runner.invoke(app, ["--config-dir", str(cfg), "--data-dir", str(data), "init"])
    store = ProposalStore(SETTINGS.paths.proposals_dir)
    store.create(
        kind="insight", title="Genesis-Seeds is dense",
        action={"type": "record", "text": "Worth a dedicated room."},
    )
    r = runner.invoke(app, [
        "--config-dir", str(cfg), "--data-dir", str(data), "--json",
        "proposals", "list",
    ])
    assert r.exit_code == ExitCode.OK
    import json
    payload = json.loads(r.stdout)
    assert len(payload["proposals"]) == 1
    assert "Genesis-Seeds" in payload["proposals"][0]["title"]


def test_cli_proposals_show_renders_full_detail(runner: CliRunner, tmp_path: Path) -> None:
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
        "--config-dir", str(cfg), "--data-dir", str(data), "--json",
        "proposals", "show", p.id,
    ])
    assert r.exit_code == ExitCode.OK
    import json
    payload = json.loads(r.stdout)
    assert payload["proposal"]["id"] == p.id


def test_cli_proposals_approve_signs_proposal(runner: CliRunner, tmp_path: Path) -> None:
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
        "--config-dir", str(cfg), "--data-dir", str(data), "--json",
        "proposals", "approve", p.id, "--yes",
    ])
    assert r.exit_code == ExitCode.OK
    final = store.get(p.id)
    assert final.status == "approved"
    assert final.signature is not None


# ─── proposal_write tool ───────────────────────────────────────────────────


def test_proposal_write_tool_validates_action_type(tmp_path: Path) -> None:
    """Tool must refuse unsupported (kind, action.type) pairs."""
    import asyncio
    from sovereign_agent.config import SETTINGS, Paths
    from sovereign_agent.tools.proposal_write import ProposalWriteTool, _Args

    new_paths = Paths(config_dir=tmp_path / "cfg", data_dir=tmp_path / "data")
    object.__setattr__(SETTINGS, "paths", new_paths)
    SETTINGS.paths.ensure()

    tool = ProposalWriteTool()
    args = _Args(kind="clean", title="x",
                 action={"type": "FAKE_ACTION", "x": 1})
    result = asyncio.run(tool.execute(args, trace_id="test"))
    assert result.ok is False
    assert "unsupported" in result.error


def test_proposal_write_tool_creates_proposal(tmp_path: Path) -> None:
    import asyncio
    from sovereign_agent.config import SETTINGS, Paths
    from sovereign_agent.proposals import open_store
    from sovereign_agent.tools.proposal_write import ProposalWriteTool, _Args

    new_paths = Paths(config_dir=tmp_path / "cfg", data_dir=tmp_path / "data")
    object.__setattr__(SETTINGS, "paths", new_paths)
    SETTINGS.paths.ensure()

    tool = ProposalWriteTool()
    args = _Args(
        kind="clean", title="Real one",
        rationale="Triple is bad",
        action={"type": "remove_triple", "triple_id": "t-bad"},
    )
    result = asyncio.run(tool.execute(args, trace_id="test"))
    assert result.ok is True
    assert result.output.startswith("prop-")

    store = open_store()
    p = store.get(result.output)
    assert p.title == "Real one"
    assert p.action["triple_id"] == "t-bad"


# ─── format_elapsed sanity (v0.2.7+) regression ────────────────────────────


def test_format_elapsed_still_works_unchanged() -> None:
    from sovereign_agent.continuation import format_elapsed
    assert format_elapsed(3725) == "1h 2m 5s"
    assert format_elapsed(None) == "—"
