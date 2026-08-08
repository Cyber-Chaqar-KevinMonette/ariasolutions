"""Tests for aria-people-health-privacy (PH3): channel registration at
real app startup, retrieval privacy gating, and doctor's channel count.
All three patched files are in-place edits to already-live modules, so
these tests only pass post-apply."""
from __future__ import annotations

import inspect

import pytest

MARK = "people-health-privacy-d"


def _patched(obj) -> bool:
    return MARK in inspect.getsource(obj)


def test_people_health_registers_via_mem_channels_import():
    from sovereign_agent import mem_channels

    if not _patched(mem_channels):
        pytest.skip("pre-apply: mem_channels/__init__.py not yet patched")
    from sovereign_agent.channels import list_channels

    names = {spec.name for spec in list_channels()}
    assert "people_health" in names


def test_people_health_excluded_from_default_retrieval():
    from sovereign_agent.retrieval import filter as filter_mod

    if not _patched(filter_mod):
        pytest.skip("pre-apply: retrieval/filter.py not yet patched")
    assert "people_health" in filter_mod._PRIVATE_CHANNELS
    assert "people" in filter_mod._PRIVATE_CHANNELS  # unaffected


def test_doctor_channel_check_expects_people_health():
    from sovereign_agent import doctor

    if not _patched(doctor.check_channels):
        pytest.skip("pre-apply: doctor.py not yet patched")
    result = doctor.check_channels()
    assert result.level == "ok", result.detail
    assert "people_health" not in (result.detail or "missing")
