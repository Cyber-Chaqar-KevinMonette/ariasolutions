"""Tests for agent_session — the persistent multi-step agent loop.

Coverage:
  • parsers: parse_proposals, parse_result_summary
  • SessionStore: save/load/list/atomic-write/corruption-detection
  • check_subtask_authority: all three states across modes
  • new_session: defaults, explicit subtasks, cap enforcement
  • run_session: drain, PROTOCOL-ZERO halt, operator interrupt, budget exceeded
  • queue growth via NEXT_SUBTASK proposals, with the queue-full cap
  • approve_subtask / skip_subtask / halt_session
  • round-trip: write → kill → reload → resume (the resume contract)
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from sovereign_agent import protocol_zero
from sovereign_agent.agent_session import (
    AuthorityCheck,
    SessionError,
    SessionResult,
    SessionState,
    SessionStore,
    Subtask,
    _SUBTASK_PROPOSAL_RE,
    approve_subtask,
    check_subtask_authority,
    halt_session,
    new_session,
    parse_proposals,
    parse_result_summary,
    run_session,
    skip_subtask,
)
from sovereign_agent.loop import LoopResult
from sovereign_agent.modes import Mode, RunBudget


# ─────────────────────────────────────────────────────────────────────────
# parse_proposals
# ─────────────────────────────────────────────────────────────────────────


class TestParseProposals:
    def test_extracts_default_tier_when_omitted(self):
        text = "RESULT: did the thing\nNEXT_SUBTASK: read the next file"
        proposals = parse_proposals(text)
        assert proposals == [("read the next file", 1)]

    def test_extracts_explicit_tier(self):
        text = "NEXT_SUBTASK[tier=0]: list the directory"
        proposals = parse_proposals(text)
        assert proposals == [("list the directory", 0)]

    def test_multiple_proposals_in_source_order(self):
        text = (
            "RESULT: explored the tree\n"
            "NEXT_SUBTASK[tier=0]: read A\n"
            "NEXT_SUBTASK[tier=1]: write B\n"
            "NEXT_SUBTASK[tier=2]: move C\n"
        )
        proposals = parse_proposals(text)
        assert proposals == [
            ("read A", 0),
            ("write B", 1),
            ("move C", 2),
        ]

    def test_empty_text_returns_empty(self):
        assert parse_proposals("") == []
        assert parse_proposals(None) == []  # type: ignore[arg-type]

    def test_no_proposals_returns_empty(self):
        assert parse_proposals("just a plain message") == []

    def test_invalid_tier_raises(self):
        with pytest.raises(SessionError, match="invalid tier"):
            parse_proposals("NEXT_SUBTASK[tier=9]: too high")

    def test_negative_tier_raises(self):
        # The regex is `\d+` so a negative number won't even match — it
        # gets read as no-tier with a default of 1, and the description
        # becomes "-1]: …". This documents that behavior so it doesn't
        # silently drift.
        text = "NEXT_SUBTASK[tier=-1]: ignored"
        proposals = parse_proposals(text)
        # The regex's tier group requires digits; the [tier=-1] is text
        # not matching, so the whole `NEXT_SUBTASK[tier=-1]:` becomes
        # "NEXT_SUBTASK" not matching → no proposal extracted.
        # If this expectation ever fails, the regex was changed and the
        # negative-tier story needs a redesign.
        assert proposals == []

    def test_trims_whitespace(self):
        text = "NEXT_SUBTASK[tier=1]:    spaces around    "
        assert parse_proposals(text) == [("spaces around", 1)]


# ─────────────────────────────────────────────────────────────────────────
# parse_result_summary
# ─────────────────────────────────────────────────────────────────────────


class TestParseResultSummary:
    def test_extracts_result_line(self):
        text = "RESULT: did the thing\nNEXT_SUBTASK[tier=1]: do next"
        assert parse_result_summary(text) == "did the thing"

    def test_falls_back_to_truncated_text_when_no_result_line(self):
        text = "I worked on this for a while and figured out the answer."
        summary = parse_result_summary(text)
        # No RESULT: → fallback to first 200 chars, stripped
        assert summary == text

    def test_fallback_strips_proposal_lines(self):
        text = (
            "Found three files.\n"
            "NEXT_SUBTASK[tier=0]: read A\n"
            "Done with discovery."
        )
        summary = parse_result_summary(text)
        # The proposal line should be removed from the fallback summary
        assert "NEXT_SUBTASK" not in summary
        assert "Found three files" in summary
        assert "Done with discovery" in summary

    def test_truncates_to_max_chars(self):
        text = "RESULT: " + ("x" * 1000)
        summary = parse_result_summary(text, max_chars=100)
        assert len(summary) == 100

    def test_empty_input_returns_empty(self):
        assert parse_result_summary("") == ""
        assert parse_result_summary(None) == ""  # type: ignore[arg-type]


# ─────────────────────────────────────────────────────────────────────────
# SessionStore
# ─────────────────────────────────────────────────────────────────────────


class TestSessionStore:
    def test_save_then_load_round_trip(self, tmp_path: Path):
        store = SessionStore(root=tmp_path)
        state = SessionState(
            session_id="sess_test_001",
            goal="test goal",
            mode="oneshot",
            subtasks=[Subtask(id="st_a", description="first")],
        )
        store.save(state)

        loaded = store.load("sess_test_001")
        assert loaded.session_id == "sess_test_001"
        assert loaded.goal == "test goal"
        assert len(loaded.subtasks) == 1
        assert loaded.subtasks[0].id == "st_a"

    def test_save_is_atomic(self, tmp_path: Path):
        """The tmp file must not coexist with the target after save."""
        store = SessionStore(root=tmp_path)
        state = SessionState(session_id="sess_atom", goal="g", mode="oneshot")
        store.save(state)
        # No leftover tmp file
        assert not (tmp_path / "sess_atom.json.tmp").exists()
        assert (tmp_path / "sess_atom.json").exists()

    def test_load_nonexistent_raises(self, tmp_path: Path):
        store = SessionStore(root=tmp_path)
        with pytest.raises(SessionError, match="not found"):
            store.load("does_not_exist")

    def test_load_corrupt_raises(self, tmp_path: Path):
        store = SessionStore(root=tmp_path)
        (tmp_path / "sess_corrupt.json").write_text("{not valid json")
        with pytest.raises(SessionError, match="corrupt"):
            store.load("sess_corrupt")

    def test_path_traversal_rejected(self, tmp_path: Path):
        store = SessionStore(root=tmp_path)
        # The defense should catch any path-injecting session_id
        with pytest.raises(SessionError, match="invalid session_id"):
            store.path_for("../../../etc/passwd")
        with pytest.raises(SessionError, match="invalid session_id"):
            store.path_for(".hidden")

    def test_list_all_sorts_descending(self, tmp_path: Path):
        store = SessionStore(root=tmp_path)
        store.save(SessionState(session_id="sess_a", goal="a", mode="oneshot"))
        store.save(SessionState(session_id="sess_b", goal="b", mode="oneshot"))
        store.save(SessionState(session_id="sess_c", goal="c", mode="oneshot"))
        listed = store.list_all()
        ids = [s.session_id for s in listed]
        # Sorted reverse (descending) by filename
        assert ids == ["sess_c", "sess_b", "sess_a"]

    def test_list_all_filters_by_status(self, tmp_path: Path):
        store = SessionStore(root=tmp_path)
        store.save(SessionState(session_id="sess_a", goal="a",
                                mode="oneshot", status="complete"))
        store.save(SessionState(session_id="sess_b", goal="b",
                                mode="oneshot", status="paused"))
        store.save(SessionState(session_id="sess_c", goal="c",
                                mode="oneshot", status="complete"))
        completes = store.list_all(status="complete")
        assert {s.session_id for s in completes} == {"sess_a", "sess_c"}

    def test_list_skips_corrupt_files(self, tmp_path: Path):
        store = SessionStore(root=tmp_path)
        store.save(SessionState(session_id="sess_good", goal="g", mode="oneshot"))
        (tmp_path / "sess_bad.json").write_text("{nope")
        listed = store.list_all()
        assert [s.session_id for s in listed] == ["sess_good"]


# ─────────────────────────────────────────────────────────────────────────
# check_subtask_authority
# ─────────────────────────────────────────────────────────────────────────


class TestCheckSubtaskAuthority:
    def test_tier_0_always_allowed(self):
        st = Subtask(id="st_a", description="read", required_tier=0)
        for mode in Mode:
            result = check_subtask_authority(st, mode)
            assert result.allowed is True, f"failed for mode {mode}"

    def test_tier_1_allowed_in_all_modes(self):
        st = Subtask(id="st_a", description="write", required_tier=1)
        for mode in Mode:
            result = check_subtask_authority(st, mode)
            assert result.allowed is True

    def test_tier_2_requires_operator_in_oneshot(self):
        st = Subtask(id="st_a", description="move", required_tier=2)
        result = check_subtask_authority(st, Mode.ONESHOT)
        assert result.allowed is False
        assert result.requires_operator is True
        assert "operator confirmation" in result.reason

    def test_tier_2_rejected_in_busy(self):
        """BUSY mode caps at tier 1 — tier-2 work must hard-reject."""
        st = Subtask(id="st_a", description="move", required_tier=2)
        result = check_subtask_authority(st, Mode.BUSY)
        assert result.allowed is False
        assert result.requires_operator is False
        assert "cannot run in this mode" in result.reason

    def test_tier_3_requires_operator_in_oneshot(self):
        st = Subtask(id="st_a", description="push", required_tier=3)
        result = check_subtask_authority(st, Mode.ONESHOT)
        assert result.allowed is False
        assert result.requires_operator is True


# ─────────────────────────────────────────────────────────────────────────
# new_session
# ─────────────────────────────────────────────────────────────────────────


class TestNewSession:
    def test_defaults_to_single_subtask_from_goal(self, tmp_path: Path):
        store = SessionStore(root=tmp_path)
        state = new_session(goal="do X", mode=Mode.ONESHOT, store=store)
        assert len(state.subtasks) == 1
        assert state.subtasks[0].description == "do X"
        assert state.subtasks[0].required_tier == 1
        assert state.subtasks[0].status == "pending"

    def test_accepts_explicit_subtasks(self, tmp_path: Path):
        store = SessionStore(root=tmp_path)
        explicit = [
            Subtask(id="st_a", description="first", required_tier=0),
            Subtask(id="st_b", description="second", required_tier=1),
        ]
        state = new_session(
            goal="overall goal", mode=Mode.ONESHOT,
            initial_subtasks=explicit, store=store,
        )
        assert len(state.subtasks) == 2
        assert [s.description for s in state.subtasks] == ["first", "second"]

    def test_rejects_initial_subtasks_exceeding_max(self, tmp_path: Path):
        store = SessionStore(root=tmp_path)
        too_many = [Subtask(id=f"st_{i}", description=f"task {i}")
                    for i in range(60)]
        with pytest.raises(SessionError, match="exceeds max_subtasks"):
            new_session(goal="g", mode=Mode.ONESHOT,
                        initial_subtasks=too_many, max_subtasks=50, store=store)

    def test_persists_to_disk(self, tmp_path: Path):
        store = SessionStore(root=tmp_path)
        state = new_session(goal="g", mode=Mode.ONESHOT, store=store)
        loaded = store.load(state.session_id)
        assert loaded.goal == "g"


# ─────────────────────────────────────────────────────────────────────────
# run_session — execution paths
# ─────────────────────────────────────────────────────────────────────────


@pytest.fixture
def make_loop_stub():
    """Returns a callable that produces a fake agent_loop.

    The fake records its calls and returns a configured LoopResult. Tests
    can override the per-call behavior via a list of LoopResult objects.
    """
    def _factory(results: list[LoopResult]):
        calls: list[dict[str, Any]] = []
        idx = {"i": 0}

        async def fake(*, goal, mode, budget, tools, **kwargs):
            calls.append({"goal": goal, "mode": mode})
            i = idx["i"]
            idx["i"] = i + 1
            if i >= len(results):
                return LoopResult(ok=True, final_message="RESULT: done",
                                  reason="complete", iterations=1, tokens_used=10)
            return results[i]

        return fake, calls

    return _factory


@pytest.fixture(autouse=True)
def _reset_protocol_zero():
    """PROTOCOL-ZERO is process-global. Always disarm before/after a test."""
    protocol_zero.disarm()
    yield
    protocol_zero.disarm()


class TestRunSessionDrain:
    def test_single_subtask_settles_complete(self, tmp_path, make_loop_stub):
        store = SessionStore(root=tmp_path)
        state = new_session(goal="do X", mode=Mode.ONESHOT, store=store)

        fake_loop, calls = make_loop_stub([
            LoopResult(ok=True, final_message="RESULT: did X",
                       reason="complete", iterations=3, tokens_used=120),
        ])

        with patch("sovereign_agent.agent_session.agent_loop", fake_loop):
            result = asyncio.run(run_session(
                session_id=state.session_id, tools={}, store=store,
            ))

        assert result.status == "complete"
        assert result.completed_subtasks == 1
        assert result.total_subtasks == 1
        assert result.total_iterations == 3
        assert result.total_tokens == 120
        assert len(calls) == 1

        # State on disk reflects the completion
        reloaded = store.load(state.session_id)
        assert reloaded.status == "complete"
        assert reloaded.subtasks[0].status == "done"
        assert reloaded.subtasks[0].result_summary == "did X"

    def test_queue_grows_from_proposals(self, tmp_path, make_loop_stub):
        store = SessionStore(root=tmp_path)
        state = new_session(goal="parent", mode=Mode.ONESHOT, store=store)

        fake_loop, _ = make_loop_stub([
            # First subtask proposes two new subtasks
            LoopResult(
                ok=True,
                final_message=(
                    "RESULT: discovered subwork\n"
                    "NEXT_SUBTASK[tier=0]: child A\n"
                    "NEXT_SUBTASK[tier=1]: child B\n"
                ),
                reason="complete", iterations=2, tokens_used=80,
            ),
            # Children complete without proposing more
            LoopResult(ok=True, final_message="RESULT: A done",
                       reason="complete", iterations=1, tokens_used=40),
            LoopResult(ok=True, final_message="RESULT: B done",
                       reason="complete", iterations=1, tokens_used=40),
        ])

        with patch("sovereign_agent.agent_session.agent_loop", fake_loop):
            result = asyncio.run(run_session(
                session_id=state.session_id, tools={}, store=store,
            ))

        assert result.status == "complete"
        reloaded = store.load(state.session_id)
        assert len(reloaded.subtasks) == 3
        # The children should reference the parent
        children = [s for s in reloaded.subtasks if s.parent_id is not None]
        assert len(children) == 2
        assert all(s.status == "done" for s in reloaded.subtasks)

    def test_queue_growth_respects_max_subtasks(self, tmp_path, make_loop_stub):
        store = SessionStore(root=tmp_path)
        # max=3 means 1 initial + room for 2 children, no more
        state = new_session(goal="parent", mode=Mode.ONESHOT,
                            max_subtasks=3, store=store)

        proposals_text = (
            "RESULT: greedy\n"
            "NEXT_SUBTASK[tier=0]: child A\n"
            "NEXT_SUBTASK[tier=0]: child B\n"
            "NEXT_SUBTASK[tier=0]: child C (should be dropped)\n"
            "NEXT_SUBTASK[tier=0]: child D (should be dropped)\n"
        )
        fake_loop, _ = make_loop_stub([
            LoopResult(ok=True, final_message=proposals_text,
                       reason="complete", iterations=1, tokens_used=50),
            LoopResult(ok=True, final_message="RESULT: A",
                       reason="complete", iterations=1, tokens_used=10),
            LoopResult(ok=True, final_message="RESULT: B",
                       reason="complete", iterations=1, tokens_used=10),
        ])

        with patch("sovereign_agent.agent_session.agent_loop", fake_loop):
            asyncio.run(run_session(
                session_id=state.session_id, tools={}, store=store,
            ))

        reloaded = store.load(state.session_id)
        # max_subtasks=3 → 1 parent + 2 children, C and D dropped
        assert len(reloaded.subtasks) == 3
        descriptions = [s.description for s in reloaded.subtasks]
        assert "child C (should be dropped)" not in descriptions
        assert "child D (should be dropped)" not in descriptions


class TestRunSessionGates:
    def test_protocol_zero_armed_halts_immediately(self, tmp_path, make_loop_stub):
        store = SessionStore(root=tmp_path)
        state = new_session(goal="do X", mode=Mode.ONESHOT, store=store)

        protocol_zero.arm("test-halt")

        fake_loop, calls = make_loop_stub([])  # should never be called

        with patch("sovereign_agent.agent_session.agent_loop", fake_loop):
            result = asyncio.run(run_session(
                session_id=state.session_id, tools={}, store=store,
            ))

        assert result.status == "halted"
        assert len(calls) == 0
        reloaded = store.load(state.session_id)
        assert reloaded.status == "halted"
        assert reloaded.pause_reason == "protocol_zero"

    def test_tier_2_subtask_pauses_for_operator(self, tmp_path, make_loop_stub):
        store = SessionStore(root=tmp_path)
        state = new_session(
            goal="g", mode=Mode.ONESHOT,
            initial_subtasks=[
                Subtask(id="st_a", description="move file", required_tier=2),
            ],
            store=store,
        )

        fake_loop, calls = make_loop_stub([])  # should never be called

        with patch("sovereign_agent.agent_session.agent_loop", fake_loop):
            result = asyncio.run(run_session(
                session_id=state.session_id, tools={}, store=store,
            ))

        assert result.status == "paused"
        assert "awaiting_approval" in (result.pause_reason or "")
        assert len(calls) == 0

    def test_tier_2_subtask_in_busy_mode_blocked(self, tmp_path, make_loop_stub):
        store = SessionStore(root=tmp_path)
        state = new_session(
            goal="g", mode=Mode.BUSY,
            initial_subtasks=[
                Subtask(id="st_a", description="move", required_tier=2),
                Subtask(id="st_b", description="read", required_tier=0),
            ],
            store=store,
        )

        fake_loop, calls = make_loop_stub([
            LoopResult(ok=True, final_message="RESULT: read",
                       reason="complete", iterations=1, tokens_used=10),
        ])

        with patch("sovereign_agent.agent_session.agent_loop", fake_loop):
            result = asyncio.run(run_session(
                session_id=state.session_id, tools={}, store=store,
            ))

        # The first (tier-2) subtask is hard-blocked; the second runs
        assert result.status == "complete"
        reloaded = store.load(state.session_id)
        assert reloaded.subtasks[0].status == "blocked"
        assert reloaded.subtasks[1].status == "done"
        assert len(calls) == 1

    def test_session_budget_caps_total_iterations(self, tmp_path, make_loop_stub):
        store = SessionStore(root=tmp_path)
        # Three subtasks, each "uses" 10 iterations — total cap is 20
        state = new_session(
            goal="g", mode=Mode.ONESHOT,
            initial_subtasks=[
                Subtask(id=f"st_{i}", description=f"t{i}", required_tier=1)
                for i in range(3)
            ],
            store=store,
        )

        fake_loop, calls = make_loop_stub([
            LoopResult(ok=True, final_message=f"RESULT: t{i}",
                       reason="complete", iterations=10, tokens_used=100)
            for i in range(3)
        ])

        session_budget = RunBudget(max_iterations=20, max_wall_seconds=7200,
                                   max_tokens=10_000_000)

        with patch("sovereign_agent.agent_session.agent_loop", fake_loop):
            result = asyncio.run(run_session(
                session_id=state.session_id, tools={}, store=store,
                budget=session_budget,
            ))

        # Should stop after 2 subtasks (20 iter > 20 cap on the *next* check)
        assert result.status == "budget"
        assert result.completed_subtasks == 2


class TestRunSessionInterrupt:
    def test_operator_interrupt_pauses(self, tmp_path, make_loop_stub):
        """When interrupts.checkpoint returns True, the session pauses."""
        store = SessionStore(root=tmp_path)
        state = new_session(
            goal="g", mode=Mode.ONESHOT,
            initial_subtasks=[
                Subtask(id="st_a", description="a", required_tier=1),
                Subtask(id="st_b", description="b", required_tier=1),
            ],
            store=store,
        )

        fake_loop, calls = make_loop_stub([
            LoopResult(ok=True, final_message="RESULT: a",
                       reason="complete", iterations=1, tokens_used=10),
        ])

        # The first iteration's checkpoint returns False (proceed); after
        # the first subtask completes the next checkpoint returns True.
        checkpoint_calls = {"n": 0}

        def fake_checkpoint(continuation_id=None):  # noqa: ARG001
            checkpoint_calls["n"] += 1
            return checkpoint_calls["n"] > 1  # pause on second call

        with patch("sovereign_agent.agent_session.agent_loop", fake_loop), \
             patch("sovereign_agent.agent_session.interrupt_checkpoint",
                   fake_checkpoint):
            result = asyncio.run(run_session(
                session_id=state.session_id, tools={}, store=store,
            ))

        assert result.status == "paused"
        assert result.pause_reason == "operator_interrupt"
        assert result.completed_subtasks == 1


class TestApproveSkipHalt:
    def test_approve_subtask_lowers_tier_and_reactivates(self, tmp_path):
        store = SessionStore(root=tmp_path)
        state = new_session(
            goal="g", mode=Mode.ONESHOT,
            initial_subtasks=[
                Subtask(id="st_a", description="risky", required_tier=2),
            ],
            store=store,
        )
        # Simulate a paused session
        state.status = "paused"
        state.pause_reason = "awaiting_approval:st_a"
        store.save(state)

        updated = approve_subtask(state.session_id, "st_a", store=store)
        assert updated.subtasks[0].required_tier == 1
        assert updated.subtasks[0].status == "pending"
        assert updated.status == "active"
        assert updated.pause_reason is None

    def test_skip_subtask_marks_skipped(self, tmp_path):
        store = SessionStore(root=tmp_path)
        state = new_session(
            goal="g", mode=Mode.ONESHOT,
            initial_subtasks=[
                Subtask(id="st_a", description="risky", required_tier=2),
            ],
            store=store,
        )

        updated = skip_subtask(state.session_id, "st_a",
                               reason="too risky", store=store)
        assert updated.subtasks[0].status == "skipped"
        assert "too risky" in updated.subtasks[0].result_summary

    def test_skip_nonexistent_subtask_raises(self, tmp_path):
        store = SessionStore(root=tmp_path)
        state = new_session(goal="g", mode=Mode.ONESHOT, store=store)
        with pytest.raises(SessionError, match="subtask not found"):
            skip_subtask(state.session_id, "st_nope", store=store)

    def test_halt_session_marks_halted(self, tmp_path):
        store = SessionStore(root=tmp_path)
        state = new_session(goal="g", mode=Mode.ONESHOT, store=store)
        updated = halt_session(state.session_id, reason="operator request",
                               store=store)
        assert updated.status == "halted"
        assert updated.pause_reason == "operator request"


class TestResumeContract:
    """The resume contract: a paused session can be loaded later and run
    to completion as if the pause never happened. State must survive a
    full process boundary — simulated here by writing, freeing the in-memory
    state, and reading from disk."""

    def test_paused_session_resumes_at_pending_subtask(
        self, tmp_path, make_loop_stub
    ):
        store = SessionStore(root=tmp_path)

        # Build a state as if a session paused after completing 1 of 3 subtasks
        state = new_session(
            goal="g", mode=Mode.ONESHOT,
            initial_subtasks=[
                Subtask(id="st_a", description="A", required_tier=1,
                        status="done", result_summary="A done"),
                Subtask(id="st_b", description="B", required_tier=1),
                Subtask(id="st_c", description="C", required_tier=1),
            ],
            store=store,
        )
        state.status = "paused"
        state.pause_reason = "operator_interrupt"
        state.total_iterations = 5
        state.total_tokens = 200
        store.save(state)

        # Drop in-memory state, simulating a process restart
        sid = state.session_id
        del state

        fake_loop, calls = make_loop_stub([
            LoopResult(ok=True, final_message="RESULT: B",
                       reason="complete", iterations=2, tokens_used=80),
            LoopResult(ok=True, final_message="RESULT: C",
                       reason="complete", iterations=2, tokens_used=80),
        ])

        with patch("sovereign_agent.agent_session.agent_loop", fake_loop):
            result = asyncio.run(run_session(
                session_id=sid, tools={}, store=store,
            ))

        assert result.status == "complete"
        assert result.completed_subtasks == 3
        # Resume accumulated on the prior totals
        assert result.total_iterations == 5 + 2 + 2
        assert result.total_tokens == 200 + 80 + 80
        # The agent_loop was only called for the two pending subtasks
        assert len(calls) == 2


# ─────────────────────────────────────────────────────────────────────────
# SessionState — derived helpers
# ─────────────────────────────────────────────────────────────────────────


class TestSessionStateHelpers:
    def test_next_pending_returns_first_pending(self):
        state = SessionState(session_id="s", goal="g", mode="oneshot",
                             subtasks=[
                                 Subtask(id="a", description="a", status="done"),
                                 Subtask(id="b", description="b", status="pending"),
                                 Subtask(id="c", description="c", status="pending"),
                             ])
        nxt = state.next_pending()
        assert nxt is not None
        assert nxt.id == "b"

    def test_next_pending_none_when_drained(self):
        state = SessionState(session_id="s", goal="g", mode="oneshot",
                             subtasks=[
                                 Subtask(id="a", description="a", status="done"),
                                 Subtask(id="b", description="b", status="skipped"),
                             ])
        assert state.next_pending() is None

    def test_progress_counts_terminal_states(self):
        state = SessionState(session_id="s", goal="g", mode="oneshot",
                             subtasks=[
                                 Subtask(id="a", description="a", status="done"),
                                 Subtask(id="b", description="b", status="skipped"),
                                 Subtask(id="c", description="c", status="blocked"),
                                 Subtask(id="d", description="d", status="pending"),
                             ])
        done, total = state.progress()
        # done + skipped count; blocked does not (it's a sticky problem state)
        assert done == 2
        assert total == 4

    def test_is_drained_when_no_active(self):
        state = SessionState(session_id="s", goal="g", mode="oneshot",
                             subtasks=[
                                 Subtask(id="a", description="a", status="done"),
                                 Subtask(id="b", description="b", status="blocked"),
                             ])
        assert state.is_drained() is True

    def test_completed_summary_truncates_oldest(self):
        long_desc = "x" * 1000
        state = SessionState(session_id="s", goal="g", mode="oneshot",
                             subtasks=[
                                 Subtask(id=f"st_{i}",
                                         description=f"{long_desc} {i}",
                                         status="done",
                                         result_summary=f"sum {i}")
                                 for i in range(10)
                             ])
        summary = state.completed_summary_for_prompt(max_chars=500)
        assert len(summary) <= 600   # 500 + the "elided" header
        assert "elided" in summary
