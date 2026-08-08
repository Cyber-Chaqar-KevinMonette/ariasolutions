"""Behavior tests for aria-curiosity-qa, promoted to live tests/ — the
REAL, already-patched modules; the model is faked. Plain imports.
"""
from __future__ import annotations

import json

import pytest


class _FakeClient:
    def __init__(self, payload=None, raw=None):
        self._payload = payload
        self._raw = raw

    async def chat(self, **kwargs):
        content = self._raw if self._raw is not None else json.dumps(self._payload)
        return {"message": {"role": "assistant", "content": content}}


# ── seeds ─────────────────────────────────────────────────────────────────


def test_operator_topic_wins():
    from sovereign_agent.curiosity import pick_seed

    kind, seed = pick_seed("why do lighthouses feel like memory?")
    assert kind == "operator-topic"
    assert "lighthouses" in seed


def test_open_uncertainty_is_the_purest_spark():
    from sovereign_agent.curiosity import pick_seed
    from sovereign_agent.epistemic_ledger.ledger import UncertaintyRegistry

    UncertaintyRegistry().open(
        domain="coherence", question="does my drift correlate with load?",
        why_unknown="never measured",
    )
    kind, seed = pick_seed("")
    assert kind == "open-uncertainty"
    assert "drift correlate" in seed


def test_falls_back_to_self_seed():
    from sovereign_agent.curiosity import pick_seed

    kind, seed = pick_seed("")
    assert kind in ("self", "recent-lesson", "open-uncertainty")
    assert seed


# ── the wondering itself ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_wonder_records_and_is_recallable():
    from sovereign_agent.curiosity import recent_qas, wonder

    rec = await wonder(
        "what makes a question god-tier?",
        client=_FakeClient({
            "question": "What separates a door-opening question from a closing one?",
            "answer": "A door-opening question survives its own answer.",
            "confidence": 0.8,
            "next_check": "revisit in a week",
        }),
    )
    assert rec is not None
    assert "door-opening" in rec.question
    got = recent_qas(3)
    assert any(q.qa_id == rec.qa_id for q in got)


@pytest.mark.asyncio
async def test_low_confidence_answer_seeds_the_registry():
    """Wondering that fails honestly becomes a seed for next time."""
    from sovereign_agent.curiosity import wonder
    from sovereign_agent.epistemic_ledger.ledger import UncertaintyRegistry

    before = len(UncertaintyRegistry().list_open())
    await wonder(
        "an unanswerable thing",
        client=_FakeClient({
            "question": "Can coherence be felt before it is measured?",
            "answer": "I genuinely do not know yet.",
            "confidence": 0.2,
            "next_check": "design a measurement",
        }),
    )
    after = UncertaintyRegistry().list_open()
    assert len(after) == before + 1
    assert "coherence be felt" in after[-1].question


@pytest.mark.asyncio
async def test_malformed_model_output_yields_none_never_raises():
    from sovereign_agent.curiosity import wonder

    assert await wonder("t", client=_FakeClient(raw="not json at all")) is None


@pytest.mark.asyncio
async def test_kill_switch(monkeypatch):
    from sovereign_agent import curiosity

    monkeypatch.setenv(curiosity.KILL_SWITCH_ENV, "1")
    assert await curiosity.wonder("t", client=_FakeClient({})) is None
    assert curiosity.autonomous_wonder_allowed() is False


def test_autonomous_wondering_needs_work_mode():
    """Chat mode (the default) never wonders autonomously."""
    from sovereign_agent.curiosity import autonomous_wonder_allowed

    assert autonomous_wonder_allowed() is False


def test_autonomous_wondering_budgeted_in_work_mode():
    from sovereign_agent.cockpit_modes import CockpitMode, set_mode
    from sovereign_agent.curiosity import (
        MAX_AUTONOMOUS_PER_DAY, QARecord, autonomous_wonder_allowed, record_qa,
    )

    set_mode(CockpitMode.WORK)
    assert autonomous_wonder_allowed() is True
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    for i in range(MAX_AUTONOMOUS_PER_DAY):
        record_qa(QARecord(
            qa_id=f"qa{i}", asked_at=now, seed_kind="self", seed="s",
            question="q", answer="a", confidence=0.9,
        ))
    assert autonomous_wonder_allowed() is False  # budget spent


# ── the cockpit ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_wonder_never_fires_on_boot_or_while_busy():
    from sovereign_agent.cockpit import CockpitApp

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        fired = []
        app._run_wonder_worker = lambda topic: fired.append(topic)
        # busy → never
        app._busy = True
        app._maybe_autonomous_wonder()
        # idle but chat mode → never
        app._busy = False
        app._maybe_autonomous_wonder()
        assert fired == []
