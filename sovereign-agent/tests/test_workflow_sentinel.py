"""Tests for workflow_sentinel — the bounded, observing execution monitor.

The load-bearing properties: it transitions correctly, it only ever observes
and advises, and its expansion proposals stay inert drafts.
"""
from __future__ import annotations

import pytest

from sovereign_agent.workflow_sentinel import (
    STATES, SIGNAL_KINDS, WorkflowSentinel, WorkflowSignal,
)


def test_starts_idle():
    assert WorkflowSentinel().state == "idle"


def test_start_then_step_is_watching():
    s = WorkflowSentinel()
    assert s.observe_event("start", "doctor").state == "watching"
    assert s.observe_event("step", "doctor", "checking").state == "watching"


@pytest.mark.parametrize("kind", ["stall", "error", "hesitation"])
def test_trouble_signals_raise_alert(kind):
    s = WorkflowSentinel()
    s.observe_event("start", "wf")
    adv = s.observe_event(kind, "wf", "detail")
    assert adv.state == "alert" and s.state == "alert"


def test_done_moves_to_learning_with_a_lesson():
    s = WorkflowSentinel()
    s.observe_event("start", "wf")
    adv = s.observe_event("done", "wf")
    assert s.state == "learning"
    assert "lesson" in adv.detail.lower()


def test_repeated_pattern_proposes_inert_workflow():
    s = WorkflowSentinel(expand_threshold=3)
    for _ in range(2):
        adv = s.observe_event("pattern", "triage", "triage then fix")
        assert adv.proposal is None  # not yet
    adv = s.observe_event("pattern", "triage", "triage then fix")
    assert s.state == "expanding"
    assert adv.proposal is not None
    assert adv.proposal.status == "proposed"  # INERT — never auto-runnable


def test_proposals_are_deduped_by_pattern():
    s = WorkflowSentinel(expand_threshold=2)
    for _ in range(5):
        s.observe_event("pattern", "x", "same pattern")
    assert len(s.proposals()) == 1  # proposed once, not five times


def test_reset_returns_to_idle():
    s = WorkflowSentinel()
    s.observe_event("start", "wf")
    s.observe_event("stall", "wf")
    s.reset()
    assert s.state == "idle"


def test_unknown_signal_kind_raises():
    s = WorkflowSentinel()
    with pytest.raises(ValueError):
        s.observe(WorkflowSignal(kind="not-a-kind"))


def test_history_is_bounded():
    s = WorkflowSentinel()
    for i in range(200):
        s.observe_event("step", "wf", f"s{i}")
    assert len(s.history()) <= 64  # ring buffer, never hoards


def test_snapshot_and_render_shapes():
    s = WorkflowSentinel()
    s.observe_event("start", "wf")
    snap = s.snapshot()
    assert snap["state"] == "watching" and "signals_seen" in snap
    assert "Workflow Sentinel" in s.render()


def test_sentinel_has_no_execution_surface():
    # It observes + advises; it must expose no method that runs or mutates a workflow.
    forbidden = {"run", "execute", "apply", "launch", "start_workflow", "modify"}
    assert not (forbidden & set(dir(WorkflowSentinel)))


def test_constants():
    assert STATES == ("idle", "watching", "alert", "learning", "expanding")
    assert "pattern" in SIGNAL_KINDS and "stall" in SIGNAL_KINDS
