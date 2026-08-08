"""Tests for session_awareness (Aria wakes up aware — FLAW-002 + FLAW-005)."""
from __future__ import annotations

from pathlib import Path

import pytest


def _repo_root() -> Path:
    here = Path(__file__).resolve().parent
    for _ in range(6):
        if (here / "pyproject.toml").exists():
            return here
        here = here.parent
    raise RuntimeError("repo root not found")


def _lines():
    from sovereign_agent.cockpit.session_awareness import awareness_lines
    return awareness_lines()


def test_awareness_returns_lines():
    lines = _lines()
    assert isinstance(lines, list)
    # at least the coherence line should surface
    assert any("coherence" in l for l in lines)


def test_awareness_lines_are_strings():
    lines = _lines()
    assert all(isinstance(l, str) for l in lines)


def test_awareness_surfaces_self_state():
    # Always surfaces at least the coherence/voice line; flaw/atom/care lines are
    # data-dependent (absent when the data dir is empty/isolated, as in tests).
    lines = _lines()
    joined = " ".join(lines).lower()
    assert "coherence" in joined and "voice" in joined


def test_awareness_never_raises():
    # called twice, must be stable and non-crashing
    _lines()
    _lines()
