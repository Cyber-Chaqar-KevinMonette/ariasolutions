"""Real behavior tests for aria-review-journal — prove a session produces a
complete, valid, reviewable directory that tells a reviewer what/how/how-to.
"""
from __future__ import annotations

import json

from sovereign_agent.review_journal import (
    build_review,
    collect_actions,
    list_reviews,
    render_how_to_verify,
    render_plan,
    render_readme,
    reviews_root,
    update_index,
)


def _state(session_id="sess-abc", status="complete", goal="Tidy the garden", subtasks=None):
    return {
        "session_id": session_id,
        "goal": goal,
        "mode": "work",
        "status": status,
        "created_at": "2026-07-11T10:00:00Z",
        "updated_at": "2026-07-11T10:30:00Z",
        "pause_reason": None,
        "last_error": None,
        "subtasks": subtasks if subtasks is not None else [
            {"id": "t1", "description": "read the files", "status": "done",
             "required_tier": 1, "result_summary": "found 3 files", "trace_id": "tr1"},
            {"id": "t2", "description": "write the summary", "status": "done",
             "required_tier": 2, "result_summary": "wrote summary.md", "trace_id": "tr2"},
        ],
    }


# ── renderers ────────────────────────────────────────────────────────────
def test_render_plan_counts_done_subtasks():
    plan = render_plan(_state())
    assert plan["subtasks_total"] == 2
    assert plan["subtasks_done"] == 2
    assert plan["goal"] == "Tidy the garden"


def test_readme_has_the_three_sections_kevin_asked_for():
    readme = render_readme(_state(), actions=[])
    assert "## What she did" in readme
    assert "## How she did it" in readme
    assert "## How to inspect it" in readme
    # names the reviewer audience Kevin specified
    assert "Claude" in readme and "human team" in readme.lower()


def test_readme_lists_each_subtask_with_its_result():
    readme = render_readme(_state(), actions=[])
    assert "read the files" in readme and "found 3 files" in readme
    assert "write the summary" in readme and "wrote summary.md" in readme


def test_how_to_verify_gives_concrete_commands():
    hv = render_how_to_verify(_state())
    assert "git" in hv and "pytest" in hv and "floor_check" in hv


def test_error_session_surfaces_the_error():
    st = _state(status="error")
    st["last_error"] = "boom in subtask t2"
    readme = render_readme(st, actions=[])
    assert "boom in subtask t2" in readme


# ── collect_actions ──────────────────────────────────────────────────────
def test_collect_actions_matches_subtask_trace_ids():
    events = [
        {"ts": "t", "flag": "tool-call-d", "trace_id": "tr1", "payload": {}},
        {"ts": "t", "flag": "unrelated-d", "trace_id": "zzz", "payload": {}},
    ]
    actions = collect_actions(_state(), events)
    flags = [a["flag"] for a in actions]
    assert "tool-call-d" in flags
    # unrelated-d has no action hint and a non-matching trace id → excluded
    assert "unrelated-d" not in flags


def test_collect_actions_is_safe_on_junk():
    assert collect_actions(_state(), None) == []
    assert collect_actions(_state(), ["not-a-dict", 42]) == []


# ── build_review (end to end on disk) ────────────────────────────────────
def test_build_review_writes_all_four_artifacts_and_index(tmp_path):
    events = [{"ts": "2026-07-11T10:05:00Z", "flag": "tool-call-d",
               "trace_id": "tr1", "payload": {"tool": "read_session"}}]
    d = build_review(_state(), data_dir=tmp_path, events_records=events)
    assert (d / "README.md").is_file()
    assert (d / "plan.json").is_file()
    assert (d / "actions.jsonl").is_file()
    assert (d / "how-to-verify.md").is_file()
    assert (reviews_root(tmp_path) / "INDEX.md").is_file()
    # plan.json is valid and matches
    plan = json.loads((d / "plan.json").read_text())
    assert plan["session_id"] == "sess-abc"
    # actions.jsonl has the matched action
    lines = (d / "actions.jsonl").read_text().strip().splitlines()
    assert len(lines) == 1 and json.loads(lines[0])["flag"] == "tool-call-d"


def test_index_is_idempotent_by_session_id(tmp_path):
    build_review(_state(status="active"), data_dir=tmp_path)
    build_review(_state(status="complete"), data_dir=tmp_path)  # same id, updated
    index = (reviews_root(tmp_path) / "INDEX.md").read_text()
    # exactly one line for the id, and it reflects the latest status
    assert index.count("`sess-abc`") == 1
    assert "complete" in index


def test_index_lists_multiple_sessions_newest_first(tmp_path):
    build_review(_state(session_id="s1"), data_dir=tmp_path)
    build_review(_state(session_id="s2"), data_dir=tmp_path)
    index = (reviews_root(tmp_path) / "INDEX.md").read_text()
    assert "`s1`" in index and "`s2`" in index
    # s2 was written last → appears above s1
    assert index.index("`s2`") < index.index("`s1`")


def test_list_reviews_returns_written_sessions(tmp_path):
    build_review(_state(session_id="s1"), data_dir=tmp_path)
    build_review(_state(session_id="s2"), data_dir=tmp_path)
    ids = list_reviews(tmp_path)
    assert set(ids) == {"s1", "s2"}


def test_build_review_survives_a_partial_state(tmp_path):
    # A crash-y session with almost nothing set must still produce a dir.
    d = build_review({"session_id": "partial"}, data_dir=tmp_path)
    assert (d / "README.md").is_file()
    assert "partial" in (d / "README.md").read_text()


# ── edge-case depth (full-system-scan hardening, 2026-07-11) ─────────────
def test_path_separator_session_id_is_contained(tmp_path):
    # A hostile/malformed id with ../ must NOT escape the reviews/ dir.
    d = build_review({"session_id": "edge/../weird"}, data_dir=tmp_path)
    # the written dir stays under reviews/, sanitized (no traversal)
    assert reviews_root(tmp_path) in d.parents
    assert ".." not in d.name and "/" not in d.name


def test_messy_subtask_text_renders_without_breaking(tmp_path):
    st = _state(subtasks=[
        {"id": "t1", "description": "do a thing\nwith a newline",
         "status": "done", "required_tier": 1,
         "result_summary": "ok `code` **bold** <script>", "trace_id": "tr1"},
    ])
    st["goal"] = "héllo 世界 <script>"
    d = build_review(st, data_dir=tmp_path)
    assert (d / "README.md").is_file()
    assert json.loads((d / "plan.json").read_text())["subtasks_total"] == 1
