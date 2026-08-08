"""Tests for lab_slot — a separate pointer for whatever model is currently
being worked on/experimented with/fine-tuned/bulked, kept apart from the
production roster.

Kevin, 2026-07-21: "add a new configuration slot called fine-tuned/
bulking slot. So we can keep our main working AIs but have a configured
slot for open sourced AIs we are working with... or working on or
experimenting on, fine tuning, bulking."
"""
from __future__ import annotations


def test_empty_by_default():
    from sovereign_agent.lab_slot import get_lab_slot

    slot = get_lab_slot()
    assert slot.is_set is False
    assert slot.model is None


def test_set_and_get_round_trips():
    from sovereign_agent.lab_slot import get_lab_slot, set_lab_slot

    set_lab_slot("aria-lab-v1:latest", note="first LoRA candidate")
    slot = get_lab_slot()
    assert slot.is_set is True
    assert slot.model == "aria-lab-v1:latest"
    assert slot.note == "first LoRA candidate"
    assert slot.set_at is not None


def test_set_without_a_note_is_fine():
    from sovereign_agent.lab_slot import get_lab_slot, set_lab_slot

    set_lab_slot("qwen3.5:2b")
    slot = get_lab_slot()
    assert slot.model == "qwen3.5:2b"
    assert slot.note == ""


def test_clear_empties_the_slot():
    from sovereign_agent.lab_slot import clear_lab_slot, get_lab_slot, set_lab_slot

    set_lab_slot("some-experiment:latest")
    assert get_lab_slot().is_set is True
    clear_lab_slot()
    assert get_lab_slot().is_set is False


def test_clear_on_an_already_empty_slot_is_a_harmless_noop():
    from sovereign_agent.lab_slot import clear_lab_slot, get_lab_slot

    clear_lab_slot()
    clear_lab_slot()  # must not raise
    assert get_lab_slot().is_set is False


def test_setting_the_lab_slot_never_touches_production_bases(tmp_path, monkeypatch):
    """The whole point of this being separate: pointing the lab slot at
    something must never change model_corps.bases.json (the production
    roster)."""
    from sovereign_agent.model_corps import bases as bases_module
    from sovereign_agent.lab_slot import set_lab_slot

    fake_bases_path = tmp_path / "isolated_bases.json"
    monkeypatch.setattr(bases_module, "_bases_path", lambda: fake_bases_path)

    set_lab_slot("some-experimental-model:latest")

    assert not fake_bases_path.exists()  # untouched -- never even created


def test_corrupt_state_file_degrades_to_empty_not_a_crash():
    from sovereign_agent.config import SETTINGS
    from sovereign_agent.lab_slot import get_lab_slot

    path = SETTINGS.paths.config_dir / "lab_slot.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{ not valid json", encoding="utf-8")

    slot = get_lab_slot()
    assert slot.is_set is False
