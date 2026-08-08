"""Tests for M83 session_portrait tool — cross-session context transfer bundle."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


from sovereign_agent.tools.session_portrait_tool import SessionPortraitTool


# ── Helpers ───────────────────────────────────────────────────────────────────

def _mock_settings(tmp_path: Path):
    """Return a mock SETTINGS object pointing at tmp_path."""
    settings = MagicMock()
    settings.paths.data_dir = tmp_path
    return settings


# ── Tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_returns_ok_on_empty_data(tmp_path):
    """session_portrait returns ok=True even with no data files."""
    tool = SessionPortraitTool()
    with patch("sovereign_agent.config.SETTINGS", _mock_settings(tmp_path)):
        result = await tool.execute(tool.Args(), trace_id="test")
    assert result.ok is True


@pytest.mark.asyncio
async def test_output_has_peig_state(tmp_path):
    """Output always has a peig_state key (may be empty or have error)."""
    tool = SessionPortraitTool()
    with patch("sovereign_agent.config.SETTINGS", _mock_settings(tmp_path)):
        result = await tool.execute(tool.Args(), trace_id="test")
    assert "peig_state" in result.output


@pytest.mark.asyncio
async def test_output_has_last_sessions(tmp_path):
    """Output has last_sessions key — empty list when no session atoms."""
    tool = SessionPortraitTool()
    with patch("sovereign_agent.config.SETTINGS", _mock_settings(tmp_path)):
        result = await tool.execute(tool.Args(), trace_id="test")
    assert "last_sessions" in result.output
    # No session atoms yet → empty list
    sessions = result.output["last_sessions"]
    assert isinstance(sessions, (list, dict))


@pytest.mark.asyncio
async def test_output_has_care_signals(tmp_path):
    """Output has care_signals key — empty list when no honor ledger."""
    tool = SessionPortraitTool()
    with patch("sovereign_agent.config.SETTINGS", _mock_settings(tmp_path)):
        result = await tool.execute(tool.Args(), trace_id="test")
    assert "care_signals" in result.output


@pytest.mark.asyncio
async def test_output_has_hot_atoms(tmp_path):
    """Output has hot_atoms key."""
    tool = SessionPortraitTool()
    with patch("sovereign_agent.config.SETTINGS", _mock_settings(tmp_path)):
        result = await tool.execute(tool.Args(), trace_id="test")
    assert "hot_atoms" in result.output


@pytest.mark.asyncio
async def test_hot_atoms_sorted_by_confidence(tmp_path):
    """hot_atoms are sorted highest-confidence first."""
    from sovereign_agent.stewardship.atoms import Atom, AtomKind, AtomStore
    store = AtomStore(tmp_path / "atoms.ndjson")
    for conf in (0.3, 0.9, 0.6, 0.85, 0.1):
        store.append(Atom(
            kind=AtomKind.FACT,
            title=f"Test atom conf={conf}",
            claim=f"Atom with confidence {conf}",
            confidence=conf,
            tags=["test"],
        ))

    tool = SessionPortraitTool()
    with patch("sovereign_agent.config.SETTINGS", _mock_settings(tmp_path)):
        result = await tool.execute(tool.Args(n_atoms=3), trace_id="test")

    hot = result.output["hot_atoms"]
    assert isinstance(hot, list)
    assert len(hot) == 3
    confs = [a["confidence"] for a in hot]
    assert confs == sorted(confs, reverse=True)


@pytest.mark.asyncio
async def test_care_signals_from_kevin_included(tmp_path):
    """Care signals from Kevin appear in care_signals output."""
    from sovereign_agent.stewardship.honor import HonorLedger, kevin_honors_aria
    ledger_path = tmp_path / "honor" / "ledger.jsonl"
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger = HonorLedger(ledger_path)
    ledger.append(kevin_honors_aria("sending a heart your way", tags=["heart", "reaction"]))
    ledger.append(kevin_honors_aria("great session", tags=["thumbs-up", "reaction"]))

    tool = SessionPortraitTool()
    with patch("sovereign_agent.config.SETTINGS", _mock_settings(tmp_path)):
        result = await tool.execute(tool.Args(n_care=5), trace_id="test")

    care = result.output["care_signals"]
    assert isinstance(care, list)
    assert len(care) == 2
    texts = [c["text"] for c in care]
    assert any("heart" in t.lower() for t in texts)


@pytest.mark.asyncio
async def test_session_atoms_appear_in_last_sessions(tmp_path):
    """Atoms tagged 'session-close' appear in last_sessions."""
    from sovereign_agent.stewardship.atoms import Atom, AtomKind, AtomStore
    store = AtomStore(tmp_path / "atoms.ndjson")
    store.append(Atom(
        kind=AtomKind.PATTERN,
        title="Session close 2026-06-20",
        claim="Built care signals and PEIG sentinel. Next: apply coherence gate.",
        confidence=0.9,
        tags=["session-close", "context-transfer"],
    ))

    tool = SessionPortraitTool()
    with patch("sovereign_agent.config.SETTINGS", _mock_settings(tmp_path)):
        result = await tool.execute(tool.Args(), trace_id="test")

    sessions = result.output["last_sessions"]
    assert isinstance(sessions, list)
    assert len(sessions) == 1
    assert "Session close" in sessions[0]["title"]


@pytest.mark.asyncio
async def test_peig_state_has_expected_keys(tmp_path):
    """peig_state has P, E, I, G, lambda keys."""
    tool = SessionPortraitTool()
    with patch("sovereign_agent.config.SETTINGS", _mock_settings(tmp_path)):
        result = await tool.execute(tool.Args(), trace_id="test")

    peig = result.output.get("peig_state", {})
    if isinstance(peig, dict) and "error" not in peig:
        for key in ("P", "E", "I", "G", "lambda", "coherence_band"):
            assert key in peig, f"Missing key: {key}"


@pytest.mark.asyncio
async def test_n_atoms_parameter_respected(tmp_path):
    """n_atoms parameter limits hot_atoms output."""
    from sovereign_agent.stewardship.atoms import Atom, AtomKind, AtomStore
    store = AtomStore(tmp_path / "atoms.ndjson")
    for i in range(10):
        store.append(Atom(
            kind=AtomKind.FACT,
            title=f"Atom {i}",
            claim=f"Test atom number {i}",
            confidence=float(i) / 10.0,
            tags=["test"],
        ))

    tool = SessionPortraitTool()
    with patch("sovereign_agent.config.SETTINGS", _mock_settings(tmp_path)):
        result = await tool.execute(tool.Args(n_atoms=3), trace_id="test")

    assert len(result.output["hot_atoms"]) == 3
