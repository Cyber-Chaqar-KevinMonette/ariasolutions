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


def test_delete_removes_the_row_entirely(rs):
    """delete-inbox-message-d (Kevin, 2026-07-26): "add a delete message
    button" — real removal, distinct from cancel (a soft status change
    that still shows up under closed history)."""
    req = rs.open("note", "throwaway")
    assert rs.delete(req.request_id) is True
    assert rs.get(req.request_id) is None
    assert req.request_id not in {r.request_id for r in rs.list(limit=100)}


def test_delete_unknown_id_returns_false(rs):
    assert rs.delete("not-a-real-id") is False


def test_delete_then_short_id_lookup_also_returns_none(rs):
    req = rs.open("note", "throwaway")
    rs.delete(req.request_id)
    assert rs.get(req.short_id) is None


def test_one_line_has_emoji(rs):
    req = rs.open("approval", "approve me")
    line = req.one_line()
    # font-truth-d — approval icon is the DejaVu-proven flag ⚐
    assert "⚐" in line and "approve me" in line


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
