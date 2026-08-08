"""Behavior tests for aria-self-witness, promoted to live tests/."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest


def _plant_yesterday_events(n=8):
    from sovereign_agent.config import SETTINGS

    day = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
    path = SETTINGS.paths.events_jsonl
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for i in range(n):
            f.write(json.dumps({"event_id": f"e{i}", "ts": f"{day}T10:00:0{i%10}.0Z",
                                "flag": "settle-d", "plane": "control",
                                "trace_id": "t", "payload": {}}) + "\n")
    return day


class _FakeClient:
    async def chat(self, **kw):
        return {"message": {"role": "assistant", "content":
                "Yesterday I tended eight small settlements. I learned that "
                "quiet days still count. I carry the thread forward."}}


@pytest.mark.asyncio
async def test_witness_writes_journal_field_note_and_greets_once():
    from sovereign_agent.config import SETTINGS
    from sovereign_agent.self_witness import witness_yesterday

    day = _plant_yesterday_events()
    first = await witness_yesterday(client=_FakeClient())
    assert first and "tended" in first
    entry = SETTINGS.paths.data_dir / "journal" / f"{day}.md"
    assert entry.exists() and "witnessed" in entry.read_text()
    notes = (SETTINGS.paths.data_dir / "stewardship" / "field-notes.jsonl").read_text()
    assert "daily-witness" in notes
    # once per day — the second wake is silent
    assert await witness_yesterday(client=_FakeClient()) is None


@pytest.mark.asyncio
async def test_quiet_yesterday_stays_silent():
    from sovereign_agent.self_witness import witness_yesterday

    assert await witness_yesterday(client=_FakeClient()) is None  # no events planted


@pytest.mark.asyncio
async def test_model_down_falls_back_mechanically_never_blocks():
    from sovereign_agent.config import SETTINGS
    from sovereign_agent.self_witness import witness_yesterday

    day = _plant_yesterday_events()

    class _Down:
        async def chat(self, **kw):
            raise ConnectionError("ollama gone")

    first = await witness_yesterday(client=_Down())
    assert first is not None  # the honest mechanical entry
    assert (SETTINGS.paths.data_dir / "journal" / f"{day}.md").exists()


@pytest.mark.asyncio
async def test_kill_switch(monkeypatch):
    from sovereign_agent import self_witness

    monkeypatch.setenv(self_witness.KILL_SWITCH_ENV, "1")
    _plant_yesterday_events()
    assert await self_witness.witness_yesterday(client=_FakeClient()) is None
