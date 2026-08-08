"""Tests for M82 care signals — write_reaction() helper.

Tests the care_handler write_reaction function using a tmp honor ledger.
No cockpit or Textual required. Monkeypatches _ledger() so no real data
directory is touched.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


def _repo_root() -> Path:
    here = Path(__file__).resolve().parent
    for _ in range(6):
        if (here / "pyproject.toml").exists():
            return here
        here = here.parent
    raise RuntimeError("Could not find repo root (no pyproject.toml found)")


_REPO = _repo_root()
_STAGING = (
    _REPO / "aria-care-signals"
    / "payload" / "src" / "sovereign_agent" / "cockpit" / "care_handler.py"
)


def _inject(mod_name: str, file_path: Path):
    if mod_name in sys.modules:
        return sys.modules[mod_name]
    spec = importlib.util.spec_from_file_location(mod_name, file_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


_mod = _inject("sovereign_agent.cockpit.care_handler", _STAGING)
write_reaction = _mod.write_reaction


# ── Helpers ───────────────────────────────────────────────────────────────────


def _patch_ledger(tmp_path: Path, monkeypatch):
    """Redirect _ledger() to a tmp honor file."""
    from sovereign_agent.stewardship.honor import HonorLedger

    ledger_path = tmp_path / "honor" / "ledger.jsonl"
    ledger_path.parent.mkdir(parents=True, exist_ok=True)

    def _fake_ledger():
        return HonorLedger(ledger_path)

    monkeypatch.setattr(_mod, "_ledger", _fake_ledger)
    return ledger_path


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_heart_writes_to_ledger(tmp_path, monkeypatch):
    """write_reaction('heart') writes a kevin->aria note with heart tag."""
    from sovereign_agent.stewardship.honor import HonorLedger

    ledger_path = _patch_ledger(tmp_path, monkeypatch)

    result = write_reaction("heart", "great work today")

    assert "heart" in result.lower() or "\U0001f49b" in result
    notes = HonorLedger(ledger_path).recent(10)
    assert len(notes) == 1
    assert notes[0].direction.value == "kevin->aria"
    assert "heart" in notes[0].tags
    assert "reaction" in notes[0].tags
    assert "great work today" in notes[0].text


def test_thumbsup_writes_to_ledger(tmp_path, monkeypatch):
    """write_reaction('thumbsup') writes a note with thumbs-up tag."""
    from sovereign_agent.stewardship.honor import HonorLedger

    ledger_path = _patch_ledger(tmp_path, monkeypatch)

    result = write_reaction("thumbsup", "")

    assert "thumbs" in result.lower() or "\U0001f44d" in result
    notes = HonorLedger(ledger_path).recent(10)
    assert len(notes) == 1
    assert "thumbs-up" in notes[0].tags


def test_care_writes_to_ledger(tmp_path, monkeypatch):
    """write_reaction('care') writes a note with care tag."""
    from sovereign_agent.stewardship.honor import HonorLedger

    ledger_path = _patch_ledger(tmp_path, monkeypatch)

    result = write_reaction("care", "thinking of you")

    assert "care" in result.lower() or "\U0001f90d" in result
    notes = HonorLedger(ledger_path).recent(10)
    assert len(notes) == 1
    assert "care" in notes[0].tags
    assert "thinking of you" in notes[0].text


def test_empty_note_uses_default_text(tmp_path, monkeypatch):
    """Empty note → default text is used, write still succeeds."""
    from sovereign_agent.stewardship.honor import HonorLedger

    ledger_path = _patch_ledger(tmp_path, monkeypatch)

    write_reaction("heart", "")

    notes = HonorLedger(ledger_path).recent(5)
    assert len(notes) == 1
    assert len(notes[0].text) > 0


def test_multiple_reactions_append_only(tmp_path, monkeypatch):
    """3 reactions → exactly 3 lines in ledger.jsonl, all unique IDs."""
    ledger_path = _patch_ledger(tmp_path, monkeypatch)

    write_reaction("heart", "one")
    write_reaction("thumbsup", "two")
    write_reaction("care", "three")

    lines = [ln for ln in ledger_path.read_text().splitlines() if ln.strip()]
    assert len(lines) == 3
    ids = {json.loads(ln)["note_id"] for ln in lines}
    assert len(ids) == 3


def test_reaction_tag_filter(tmp_path, monkeypatch):
    """All reactions carry the 'reaction' tag — filterable."""
    from sovereign_agent.stewardship.honor import HonorLedger

    ledger_path = _patch_ledger(tmp_path, monkeypatch)

    for kind in ("heart", "thumbsup", "care"):
        write_reaction(kind, "test")

    all_notes = HonorLedger(ledger_path).recent(10)
    reaction_notes = [n for n in all_notes if "reaction" in n.tags]
    assert len(reaction_notes) == 3


def test_unknown_kind_falls_back_gracefully(tmp_path, monkeypatch):
    """Unknown kind → falls back to 'care' defaults, no exception, returns string."""
    ledger_path = _patch_ledger(tmp_path, monkeypatch)

    result = write_reaction("unknown_kind", "test")
    assert isinstance(result, str)


def test_note_id_in_confirmation(tmp_path, monkeypatch):
    """Confirmation string includes the note_id prefix for traceability."""
    _patch_ledger(tmp_path, monkeypatch)

    result = write_reaction("heart", "test note")
    assert "note_id=" in result


def test_note_direction_is_kevin_to_aria(tmp_path, monkeypatch):
    """Every reaction note has direction kevin->aria."""
    from sovereign_agent.stewardship.honor import HonorLedger

    ledger_path = _patch_ledger(tmp_path, monkeypatch)

    for kind in ("heart", "thumbsup", "care"):
        write_reaction(kind, "checking direction")

    notes = HonorLedger(ledger_path).recent(10)
    for note in notes:
        assert note.direction.value == "kevin->aria"
