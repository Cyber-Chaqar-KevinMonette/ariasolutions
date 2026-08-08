"""Tests for the collaboration inbox (requests) and its wiring into runs."""
import pytest

from sovereign_agent.persistence.store import ErebloStore
from sovereign_agent.persistence.projects import ProjectsManager
from sovereign_agent.workflow.agentic_loop import AgenticLoop, PlanStep, StepOutcome
from sovereign_agent.workflow.requests import RequestStore, HumanRequest
from sovereign_agent.workflow.evolving_run import EvolvingAgenticRun


@pytest.fixture
def store(tmp_path):
    return ErebloStore(tmp_path / "atoms.db")


@pytest.fixture
def rs(store):
    return RequestStore(store)


def test_open_and_get(rs):
    req = rs.open("question", "What DB?", body="postgres or sqlite?")
    assert req.status == "open" and req.kind == "question"
    got = rs.get(req.request_id)
    assert got.title == "What DB?" and got.body == "postgres or sqlite?"


def test_short_id_lookup(rs):
    req = rs.open("suggestion", "Use a cache")
    got = rs.get(req.request_id[-6:])      # short id
    assert got is not None and got.request_id == req.request_id


def test_invalid_kind_becomes_note(rs):
    req = rs.open("not_a_kind", "x")
    assert req.kind == "note"


def test_list_open_and_count(rs):
    rs.open("question", "a"); rs.open("blocker", "b")
    assert rs.open_count() == 2
    assert len(rs.list_open()) == 2


def test_answer_then_resolve(rs):
    req = rs.open("question", "ping?")
    a = rs.answer(req.request_id, "pong")
    assert a.status == "answered" and a.answer == "pong" and a.answered_at
    r = rs.resolve(req.request_id)
    assert r.status == "resolved"
    assert rs.open_count() == 0


def test_cancel(rs):
    req = rs.open("note", "nvm")
    c = rs.cancel(req.request_id)
    assert c.status == "cancelled"


def test_answer_missing_returns_none(rs):
    assert rs.answer("nonexistent", "x") is None


def test_one_line_has_emoji(rs):
    req = rs.open("approval", "approve me")
    line = req.one_line()
    assert "🛂" in line and "approve me" in line


# ── wiring: a paused run files a request ──────────────────────────────────


class _Scorer:
    def assess(self, goal, *, context_hint=None, prior_attempts=0):
        class A:
            band = "M2"; suggested_clarifications = []; concerning_dimensions = []
        return A()


class _Planner:
    def __init__(self, steps): self._s = steps
    def plan(self, goal): return list(self._s)


def test_held_step_files_approval_request(tmp_path, store, rs):
    projects = ProjectsManager(store)
    loop = AgenticLoop(projects)
    loop.register_tool_handler("shell", lambda t: StepOutcome(succeeded=True, summary="ok"))
    pid = projects.create_project("t")
    run = EvolvingAgenticRun(
        loop, planner=_Planner([PlanStep("rm things", "", "shell", {"argv": ["rm"]})]),
        scorer=_Scorer(), request_store=rs)
    res = run.execute("risky", pid)   # approve=None → consequential held
    assert res.decision == "paused_for_review"
    opened = rs.list_open()
    assert len(opened) == 1
    assert opened[0].kind == "approval"
    assert "rm things" in opened[0].title


def test_run_without_inbox_still_works(tmp_path, store):
    projects = ProjectsManager(store)
    loop = AgenticLoop(projects)
    loop.register_tool_handler("shell", lambda t: StepOutcome(succeeded=True, summary="ok"))
    pid = projects.create_project("t")
    # no request_store passed → filing is a no-op, run still proceeds
    run = EvolvingAgenticRun(
        loop, planner=_Planner([PlanStep("ls", "", "shell", {"argv": ["ls"]})]),
        scorer=_Scorer())
    res = run.execute("list", pid, approve=lambda s, d: True)
    assert res.decision == "executed"


def test_defer_flag_revisit_reopen(rs):
    req = rs.open("question", "x")
    assert rs.defer(req.request_id).status == "deferred"
    assert rs.flag(req.request_id).status == "needs_attention"
    assert rs.revisit(req.request_id).status == "revisit"
    assert rs.reopen(req.request_id).status == "open"


def test_set_status_rejects_unknown(rs):
    req = rs.open("note", "x")
    with pytest.raises(ValueError):
        rs.set_status(req.request_id, "bogus")


# ── enriched context + scheduling + migration (v0.2.38.0) ──────────────────

def test_open_with_context_roundtrip(rs):
    r = rs.open("research", "Investigate perf", body="bench it",
                rationale="suspect O(n^2)", revisit_when="after refactor",
                priority="high", estimate="~2h", tags=["perf", "parser"])
    g = rs.get(r.request_id)
    assert g.rationale == "suspect O(n^2)"
    assert g.revisit_when == "after refactor"
    assert g.priority == "high"
    assert g.estimate == "~2h"
    assert g.tags == ["perf", "parser"]
    assert "why: suspect O(n^2)" in g.context_lines()


def test_tags_normalized_and_deduped(rs):
    r = rs.open("note", "x", tags=["#a", "a", " b ", "b", "c"])
    assert r.tags == ["a", "b", "c"]


def test_invalid_priority_defaults_to_normal(rs):
    assert rs.open("note", "x", priority="SUPER").priority == "normal"


def test_update_context_partial(rs):
    r = rs.open("note", "x", rationale="old", priority="low")
    rs.update_context(r.request_id, rationale="new")   # only why changes
    g = rs.get(r.request_id)
    assert g.rationale == "new" and g.priority == "low"
    with pytest.raises(ValueError):
        rs.update_context(r.request_id, priority="bogus")


def test_next_open_is_most_urgent(rs):
    rs.open("note", "low", priority="low")
    rs.open("note", "normal")
    rs.open("blocker", "urgent", priority="urgent")
    assert rs.next_open().title == "urgent"


def test_defer_captures_why_and_when(rs):
    r = rs.open("decision", "park me")
    rs.defer(r.request_id, why="need data", when="next week")
    g = rs.get(r.request_id)
    assert g.status == "deferred"
    assert g.rationale == "need data" and g.revisit_when == "next week"


def test_parked_and_due(rs):
    import datetime as _dt
    past = (_dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=1)).isoformat()
    future = (_dt.datetime.now(_dt.timezone.utc) + _dt.timedelta(days=2)).isoformat()
    a = rs.open("decision", "due one")
    rs.defer(a.request_id, when_at=past)
    b = rs.open("decision", "later one")
    rs.revisit(b.request_id, when_at=future)
    titles = {r.title for r in rs.parked()}
    assert {"due one", "later one"} <= titles
    due_titles = {r.title for r in rs.due()}
    assert due_titles == {"due one"}      # only the past one is due


def test_bad_revisit_at_never_crashes(rs):
    r = rs.open("note", "x", revisit_at="not-a-date")
    rs.defer(r.request_id)
    assert rs.get(r.request_id).is_due is False
    assert rs.due() == []


def test_reopen_parked(rs):
    r = rs.open("note", "x")
    rs.defer(r.request_id)
    assert rs.reopen(r.request_id).status == "open"


def test_list_filters_by_kind_and_tag(rs):
    rs.open("research", "r1", tags=["web"])
    rs.open("question", "q1", tags=["web"])
    rs.open("question", "q2", tags=["local"])
    assert {r.title for r in rs.list(kind="research")} == {"r1"}
    assert {r.title for r in rs.list(tag="web")} == {"r1", "q1"}


def test_migration_adds_columns_to_legacy_table(tmp_path):
    """The critical edge case: an existing v0.2.36 table (no context columns)
    must gain them without losing data, and the migration must be idempotent."""
    from sovereign_agent.persistence.store import ErebloStore
    store = ErebloStore(tmp_path / "legacy.db")
    # old 10-column schema + a legacy row
    store.execute("""CREATE TABLE human_requests (
        request_id TEXT PRIMARY KEY, kind TEXT NOT NULL, title TEXT NOT NULL,
        body TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'open',
        created_at TEXT NOT NULL, answered_at TEXT NOT NULL DEFAULT '',
        answer TEXT NOT NULL DEFAULT '', workflow_id TEXT NOT NULL DEFAULT '',
        tags_json TEXT NOT NULL DEFAULT '[]')""")
    store.execute(
        "INSERT INTO human_requests(request_id,kind,title,created_at) VALUES(?,?,?,?)",
        ("01LEGACY0000000000000001", "question", "legacy", "2026-01-01T00:00:00+00:00"))

    from sovereign_agent.workflow.requests import RequestStore
    rs = RequestStore(store)                       # migrates
    cols = {r["name"] for r in store.query_all("PRAGMA table_info(human_requests)")}
    for c in ("rationale", "revisit_when", "revisit_at", "priority", "estimate"):
        assert c in cols
    legacy = rs.get("000001")
    assert legacy is not None and legacy.title == "legacy"
    assert legacy.priority == "normal" and legacy.tags == []
    # idempotent re-open
    RequestStore(store)
    # and the migrated store works normally
    r = rs.open("note", "new", priority="high")
    assert rs.get(r.request_id).priority == "high"
