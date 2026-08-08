"""Tests for the /council and /globe cockpit handlers."""
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


def _handler():
    from sovereign_agent.cockpit.council_handler import globe_text, consult_text
    return globe_text, consult_text


def test_globe_text_renders():
    globe_text, _ = _handler()
    out = globe_text()
    assert "THE GLOBE" in out
    assert "ARIA" in out


def test_consult_text_renders_advisory():
    _, consult_text = _handler()
    out = consult_text("Should we proceed with the build?")
    assert "council" in out.lower()
    assert "Advisory only" in out
    assert any(w in out.upper() for w in ("YES", "NO", "SPLIT"))


def test_consult_text_empty_usage():
    _, consult_text = _handler()
    out = consult_text("   ")
    assert "usage" in out.lower()


def test_globe_text_shows_families():
    globe_text, _ = _handler()
    out = globe_text()
    assert "GodCore" in out and "Independent" in out and "Maverick" in out
    assert "Void" in out  # Void is GodCore in the canonical design
