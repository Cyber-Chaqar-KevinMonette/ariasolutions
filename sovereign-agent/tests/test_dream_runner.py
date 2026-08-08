"""Tests for dream_runner resilience at failure paths (M78).

Tests use minimal mock DreamStore/ContinuationStore to avoid filesystem
dependencies. Each test drives advance_dream() with controlled state.

Coverage targets: dream_runner.py terminal status checks, EC-DREAM-006
idle detection, HARD_CAP_CYCLES enforcement, _finalize_cycle idempotency,
continuation loss recovery, cap exhaustion.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from unittest import mock

import pytest

from sovereign_agent.dream import (
    CycleEntry,
    DreamCaps,
    DreamNotFound,
    DreamSession,
    DreamStore,
    HARD_CAP_CYCLES,
    new_dream_id,
)
from sovereign_agent.dream_runner import DreamAdvanceResult, advance_dream
from sovereign_agent.health import IDLE_ATOM_THRESHOLD, IDLE_CYCLE_WINDOW


# ── Helpers ───────────────────────────────────────────────────────────────────


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _make_dream(
    status: str = "active",
    cycles_completed: int = 0,
    cycles: list | None = None,
    current_cycle_task_id: str | None = None,
    work_dir: str = "/tmp/dream-work",
) -> DreamSession:
    dream_id = new_dream_id()
    return DreamSession(
        dream_id=dream_id,
        goal="test dream goal",
        caps=DreamCaps(),
        status=status,
        created_at=_now(),
        updated_at=_now(),
        cycles_completed=cycles_completed,
        files_written=0,
        elapsed_seconds=0.0,
        current_cycle_task_id=current_cycle_task_id,
        cycles=cycles or [],
        projects=[],
        work_dir=work_dir,
        notes="",
    )


class _FakeDreamStore:
    """In-memory DreamStore. Stores one dream by id."""

    def __init__(self, dream: DreamSession):
        self._dream = dream
        self.saved = []

    def get(self, dream_id: str) -> DreamSession:
        if dream_id != self._dream.dream_id:
            raise DreamNotFound(dream_id)
        return self._dream

    def save(self, dream: DreamSession) -> None:
        self._dream = dream
        self.saved.append(dream.status)

    def ensure_root(self) -> None:
        pass


class _FakeContStore:
    """In-memory ContinuationStore. Returns None for unknown task ids."""

    def __init__(self, continuations: dict | None = None):
        self._conts = continuations or {}

    def get(self, task_id: str):
        if task_id not in self._conts:
            raise FileNotFoundError(f"continuation {task_id} not found")
        return self._conts[task_id]

    def create(self, **kwargs) -> None:
        pass


class _FakeCont:
    """Minimal continuation object."""

    def __init__(self, status: str = "active", drained: bool = False, task_id: str = ""):
        self.status = status
        self._drained = drained
        self.task_id = task_id or "cycle-test-done"
        self.total_elapsed_seconds = 0.0

    def is_drained(self) -> bool:
        return self._drained


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_advance_dream_not_found(tmp_path):
    """advance_dream with invalid dream_id → DreamNotFound propagates."""
    dream = _make_dream()
    store = _FakeDreamStore(dream)
    cont_store = _FakeContStore()

    with pytest.raises(DreamNotFound):
        advance_dream(
            dream_id="dream-DOESNOTEXIST",
            tools={},
            store=store,
            cont_store=cont_store,
        )


def test_advance_paused_dream_returns_early(tmp_path):
    """Dream with status='paused' → step_outcome='dream_paused', no further work."""
    dream = _make_dream(status="paused")
    store = _FakeDreamStore(dream)
    cont_store = _FakeContStore()

    result = advance_dream(
        dream_id=dream.dream_id,
        tools={},
        store=store,
        cont_store=cont_store,
    )

    assert result.step_outcome == "dream_paused"
    assert result.dream_status == "paused"
    # No save calls — early return
    assert store.saved == []


@pytest.mark.parametrize("status", ["completed", "exhausted", "halted"])
def test_advance_terminal_states(status: str):
    """Dreams in terminal states return matching step_outcome immediately."""
    dream = _make_dream(status=status)
    store = _FakeDreamStore(dream)
    cont_store = _FakeContStore()

    result = advance_dream(
        dream_id=dream.dream_id,
        tools={},
        store=store,
        cont_store=cont_store,
    )

    assert result.step_outcome == f"dream_{status}"
    assert result.dream_status == status


def test_advance_continuation_loss_replans(tmp_path):
    """current_cycle_task_id set but continuation file missing → runner starts a new cycle."""
    dream = _make_dream(
        status="active",
        current_cycle_task_id="cycle-missing-001",
    )
    store = _FakeDreamStore(dream)
    cont_store = _FakeContStore()  # no continuations

    # Mock out get_planner + cont_store.create so we don't hit filesystem
    from sovereign_agent.planners.base import PlanResult

    def _fake_plan(**kwargs) -> PlanResult:
        return PlanResult(
            goal="test cycle",
            steps=[],
            output_path=str(tmp_path / "out.txt"),
        )

    with (
        mock.patch("sovereign_agent.dream_runner.get_planner") as mock_planner,
        mock.patch("sovereign_agent.dream_runner.run_one_step") as mock_step,
        mock.patch("sovereign_agent.dream_runner.emit_event"),
        mock.patch.object(Path, "mkdir"),
    ):
        mock_planner.return_value.plan.side_effect = _fake_plan
        mock_step.return_value = mock.MagicMock(
            step_outcome="new_cycle",
            iterations=0, tokens=0, elapsed_seconds=0.0,
            step_id=0, step_kind="noop",
            final_message=None,
        )
        result = advance_dream(
            dream_id=dream.dream_id,
            tools={},
            store=store,
            cont_store=cont_store,
        )

    # The runner should have created a new cycle (not crashed)
    assert result is not None
    assert result.dream_id == dream.dream_id


def test_hard_cycle_cap_enforcement():
    """cycles_completed == HARD_CAP_CYCLES → dream_exhausted, no new cycle planned."""
    dream = _make_dream(
        status="active",
        cycles_completed=HARD_CAP_CYCLES,
        current_cycle_task_id=None,  # no active cycle, forces new-cycle path
    )
    store = _FakeDreamStore(dream)
    cont_store = _FakeContStore()

    result = advance_dream(
        dream_id=dream.dream_id,
        tools={},
        store=store,
        cont_store=cont_store,
    )

    assert result.step_outcome == "dream_exhausted"
    assert "exhausted" in store.saved


def test_idle_cycle_detection_ec_dream_006():
    """3 cycles each with atoms_written=0 → auto-paused with EC-DREAM-006 in notes."""
    # Build 3 completed idle cycles
    idle_cycles = [
        CycleEntry(
            cycle_number=i + 1,
            task_id=f"cycle-test-{i:03d}",
            started_at=_now(),
            status="completed",
            cycle_dir="/tmp",
            atoms_written=0,  # idle
        )
        for i in range(IDLE_CYCLE_WINDOW)
    ]

    dream = _make_dream(
        status="active",
        cycles_completed=IDLE_CYCLE_WINDOW,
        cycles=idle_cycles,
        current_cycle_task_id="cycle-test-done",
    )
    store = _FakeDreamStore(dream)

    # The active continuation is drained (cycle just finished)
    cont_store = _FakeContStore({
        "cycle-test-done": _FakeCont(status="active", drained=True, task_id="cycle-test-done"),
    })

    with mock.patch("sovereign_agent.dream_runner.emit_event"):
        result = advance_dream(
            dream_id=dream.dream_id,
            tools={},
            store=store,
            cont_store=cont_store,
        )

    assert result.step_outcome == "dream_paused"
    assert result.dream_status == "paused"
    # notes should carry EC-DREAM-006
    final_dream = store._dream
    assert "EC-DREAM-006" in (final_dream.notes or ""), (
        f"Expected EC-DREAM-006 in notes, got: {final_dream.notes!r}"
    )
