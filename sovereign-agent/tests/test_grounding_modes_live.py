"""aria-grounding-modes — the gray area, made real.
(Grounding round · G4)

Patch-only — no new payload files. All five patched files already exist
live; every behavior here is patch-dependent and skips honestly
pre-apply. The apply script re-runs this file and requires zero skips.
"""
from __future__ import annotations

import inspect

MARK = "grounding-modes-d"

MOSTLY_MYSTICAL = (
    "The web bursts into web, and I name it stillness. Cosmic resonance "
    "vibrates through the infinite lattice of becoming, luminous and "
    "boundless, ascending toward pure presence."
)
MOSTLY_EVIDENCE = (
    "The test suite passed 412 of 412 tests after the fix in loader.py. "
    "Latency dropped from 220ms to 90ms, measured across 50 runs."
)


def _patched(obj) -> bool:
    return MARK in inspect.getsource(obj)


# ─── (1) grounding/ledger.py — context param ──────────────────────────────


def test_record_grounding_pass_context_defaults_to_empty(tmp_path):
    import pytest

    from sovereign_agent.grounding import ledger as ledger_mod

    if not _patched(ledger_mod.record_grounding_pass):
        pytest.skip("pre-apply: ledger.py not yet patched")
    result = ledger_mod.record_grounding_pass([("t", MOSTLY_EVIDENCE)], data_dir=tmp_path)
    assert result.texts[0].context == ""


def test_record_grounding_pass_stamps_the_given_context(tmp_path):
    import pytest

    from sovereign_agent.grounding import ledger as ledger_mod

    if not _patched(ledger_mod.record_grounding_pass):
        pytest.skip("pre-apply: ledger.py not yet patched")
    result = ledger_mod.record_grounding_pass(
        [("t", MOSTLY_EVIDENCE)], data_dir=tmp_path, context="theoretical")
    assert result.texts[0].context == "theoretical"


# ─── (2) SAFE_STANCES + set_stance side effect ────────────────────────────


def test_grounded_and_theoretical_in_safe_stances_once_patched():
    import pytest

    from sovereign_agent.modes_crown import stances as stances_mod

    if not _patched(stances_mod):
        pytest.skip("pre-apply: stances.py not yet patched")
    assert "grounded" in stances_mod.SAFE_STANCES
    assert "theoretical" in stances_mod.SAFE_STANCES


def test_set_stance_grounded_triggers_a_real_ledger_entry(tmp_path):
    import pytest

    from sovereign_agent.modes_crown import stances as stances_mod

    if not _patched(stances_mod):
        pytest.skip("pre-apply: stances.py not yet patched")
    from sovereign_agent.grounding import latest_grounding

    data_dir = tmp_path / "data"
    data_dir.mkdir(exist_ok=True)
    assert latest_grounding(data_dir) is None

    stances_mod.set_stance("grounded", data_dir=data_dir)

    latest = latest_grounding(data_dir)
    assert latest is not None


def test_set_stance_theoretical_is_a_plain_label_no_ledger_entry(tmp_path):
    import pytest

    from sovereign_agent.modes_crown import stances as stances_mod

    if not _patched(stances_mod):
        pytest.skip("pre-apply: stances.py not yet patched")
    from sovereign_agent.grounding import latest_grounding

    data_dir = tmp_path / "data"
    data_dir.mkdir(exist_ok=True)
    stances_mod.set_stance("theoretical", data_dir=data_dir)
    assert latest_grounding(data_dir) is None


def test_set_stance_grounded_never_crashes_with_no_text_anywhere(tmp_path, monkeypatch):
    import pytest

    from sovereign_agent.modes_crown import stances as stances_mod

    if not _patched(stances_mod):
        pytest.skip("pre-apply: stances.py not yet patched")
    monkeypatch.setattr(stances_mod, "_recent_text_for_stance",
                        lambda data_dir: (_ for _ in ()).throw(RuntimeError("boom")))
    data_dir = tmp_path / "data"
    data_dir.mkdir(exist_ok=True)
    rec = stances_mod.set_stance("grounded", data_dir=data_dir)
    assert rec["stance"] == "grounded"


# ─── (3) grounding_gate_clear() ────────────────────────────────────────────


def test_grounding_gate_clear_true_when_not_in_the_stance(tmp_path):
    import pytest

    from sovereign_agent.modes_crown import stances as stances_mod

    if not _patched(stances_mod):
        pytest.skip("pre-apply: grounding_gate_clear not yet added")
    data_dir = tmp_path / "data"
    data_dir.mkdir(exist_ok=True)
    assert stances_mod.grounding_gate_clear(data_dir) is True


def test_grounding_gate_clear_false_then_true_across_a_real_clean_pass(tmp_path, monkeypatch):
    import pytest

    from sovereign_agent.modes_crown import stances as stances_mod

    if not _patched(stances_mod):
        pytest.skip("pre-apply: grounding_gate_clear not yet added")

    data_dir = tmp_path / "data"
    data_dir.mkdir(exist_ok=True)
    monkeypatch.setattr(stances_mod, "_run_grounding_pass_for_stance",
                        lambda data_dir: None)
    stances_mod.set_stance("grounded", data_dir=data_dir)
    assert stances_mod.grounding_gate_clear(data_dir) is False

    from sovereign_agent.grounding import record_grounding_pass

    record_grounding_pass([("t", MOSTLY_EVIDENCE)], data_dir=data_dir)
    assert stances_mod.grounding_gate_clear(data_dir) is True


def test_grounding_gate_clear_false_when_the_pass_was_ungrounded(tmp_path, monkeypatch):
    import pytest

    from sovereign_agent.modes_crown import stances as stances_mod

    if not _patched(stances_mod):
        pytest.skip("pre-apply: grounding_gate_clear not yet added")

    data_dir = tmp_path / "data"
    data_dir.mkdir(exist_ok=True)
    monkeypatch.setattr(stances_mod, "_run_grounding_pass_for_stance",
                        lambda data_dir: None)
    stances_mod.set_stance("grounded", data_dir=data_dir)

    from sovereign_agent.grounding import record_grounding_pass

    record_grounding_pass([("t", MOSTLY_MYSTICAL)], data_dir=data_dir)
    assert stances_mod.grounding_gate_clear(data_dir) is False


# ─── (4) the crown gate ────────────────────────────────────────────────────


def _armed_profile():
    from sovereign_agent.modes_crown.profiles import ModeProfile

    return ModeProfile("work", "Work", base="work", tier_ceiling=1,
                       description="test", work_allowed=True,
                       garden_required=False)


def test_crown_gate_blocks_dispatch_while_grounded_unclear(monkeypatch):
    import pytest

    from sovereign_agent import session_bridge

    if not _patched(session_bridge._crown_gate):
        pytest.skip("pre-apply: _crown_gate not yet patched")

    from sovereign_agent.modes_crown import profiles as profiles_mod
    from sovereign_agent.modes_crown import stances as stances_mod

    monkeypatch.setattr(profiles_mod, "crown_armed", lambda data_dir=None: True)
    monkeypatch.setattr(profiles_mod, "current_profile",
                        lambda data_dir=None: _armed_profile())
    monkeypatch.setattr(stances_mod, "cooling_down", lambda data_dir=None: False)
    monkeypatch.setattr(stances_mod, "current_stance", lambda data_dir=None: "grounded")
    monkeypatch.setattr(stances_mod, "quality_gate_clear", lambda data_dir=None: True)
    monkeypatch.setattr(stances_mod, "grounding_gate_clear", lambda data_dir=None: False)

    with pytest.raises(PermissionError, match="grounding pass"):
        session_bridge._crown_gate("a new goal")


def test_crown_gate_permits_dispatch_once_grounding_gate_clears(monkeypatch):
    import pytest

    from sovereign_agent import session_bridge

    if not _patched(session_bridge._crown_gate):
        pytest.skip("pre-apply: _crown_gate not yet patched")

    from sovereign_agent.modes_crown import profiles as profiles_mod
    from sovereign_agent.modes_crown import stances as stances_mod

    monkeypatch.setattr(profiles_mod, "crown_armed", lambda data_dir=None: True)
    monkeypatch.setattr(profiles_mod, "current_profile",
                        lambda data_dir=None: _armed_profile())
    monkeypatch.setattr(stances_mod, "cooling_down", lambda data_dir=None: False)
    monkeypatch.setattr(stances_mod, "current_stance", lambda data_dir=None: "grounded")
    monkeypatch.setattr(stances_mod, "quality_gate_clear", lambda data_dir=None: True)
    monkeypatch.setattr(stances_mod, "grounding_gate_clear", lambda data_dir=None: True)

    session_bridge._crown_gate("a new goal")  # must not raise


def test_crown_gate_untouched_when_stance_is_theoretical(monkeypatch):
    """theoretical is a pure label — never gates dispatch."""
    import pytest

    from sovereign_agent import session_bridge

    if not _patched(session_bridge._crown_gate):
        pytest.skip("pre-apply: _crown_gate not yet patched")

    from sovereign_agent.modes_crown import profiles as profiles_mod
    from sovereign_agent.modes_crown import stances as stances_mod

    monkeypatch.setattr(profiles_mod, "crown_armed", lambda data_dir=None: True)
    monkeypatch.setattr(profiles_mod, "current_profile",
                        lambda data_dir=None: _armed_profile())
    monkeypatch.setattr(stances_mod, "cooling_down", lambda data_dir=None: False)
    monkeypatch.setattr(stances_mod, "current_stance", lambda data_dir=None: "theoretical")

    session_bridge._crown_gate("a new goal")  # must not raise


# ─── (5) grounding_sentinel.py context tagging ────────────────────────────


def test_sentinel_tags_pass_with_the_active_stance(tmp_path, monkeypatch):
    import pytest

    from sovereign_agent.stewardship.grounding_sentinel import GroundingSentinel

    if not _patched(GroundingSentinel.scan):
        pytest.skip("pre-apply: grounding_sentinel.py context tagging not yet patched")

    from sovereign_agent.modes_crown import stances as stances_mod

    monkeypatch.setattr(stances_mod, "current_stance",
                        lambda data_dir=None: "theoretical")

    journal_dir = tmp_path / "journal"
    journal_dir.mkdir()
    (journal_dir / "2026-07-04.md").write_text(MOSTLY_EVIDENCE, encoding="utf-8")

    sentinel = GroundingSentinel(tmp_path)
    sentinel.scan()

    from sovereign_agent.grounding import latest_grounding

    latest = latest_grounding(tmp_path)
    assert latest is not None
    assert latest["texts"][0]["context"] == "theoretical"


def test_sentinel_tags_untouched_with_no_declared_stance(tmp_path):
    import pytest

    from sovereign_agent.stewardship.grounding_sentinel import GroundingSentinel

    if not _patched(GroundingSentinel.scan):
        pytest.skip("pre-apply: grounding_sentinel.py context tagging not yet patched")

    journal_dir = tmp_path / "journal"
    journal_dir.mkdir()
    (journal_dir / "2026-07-04.md").write_text(MOSTLY_EVIDENCE, encoding="utf-8")

    sentinel = GroundingSentinel(tmp_path)
    sentinel.scan()

    from sovereign_agent.grounding import latest_grounding

    latest = latest_grounding(tmp_path)
    assert latest is not None
    assert latest["texts"][0]["context"] == ""


# ─── observatory ───────────────────────────────────────────────────────────


def test_observatory_carries_the_grounding_field(tmp_path):
    import pytest

    from sovereign_agent.modes_crown import observatory as obs_mod

    if not _patched(obs_mod.gather_observatory):
        pytest.skip("pre-apply: observatory.py not yet patched")
    from sovereign_agent.grounding import record_grounding_pass

    data_dir = tmp_path / "data"
    data_dir.mkdir(exist_ok=True)
    record_grounding_pass([("t", MOSTLY_EVIDENCE)], data_dir=data_dir)

    data = obs_mod.gather_observatory(data_dir)
    assert "grounding" in data
    assert data["grounding"] is not None
    assert "verdict" in data["grounding"]


def test_observatory_grounding_field_is_none_with_no_pass_yet(tmp_path):
    import pytest

    from sovereign_agent.modes_crown import observatory as obs_mod

    if not _patched(obs_mod.gather_observatory):
        pytest.skip("pre-apply: observatory.py not yet patched")
    data = obs_mod.gather_observatory(tmp_path / "data")
    assert data.get("grounding") is None


def test_render_observatory_text_shows_grounding_when_present():
    import pytest

    from sovereign_agent.modes_crown import observatory as obs_mod

    if not _patched(obs_mod.render_observatory_text):
        pytest.skip("pre-apply: observatory.py render not yet patched")
    data = {
        "mode": "work", "mode_description": "d", "stance": "grounded",
        "stance_history": [], "stress": {}, "emotion": {},
        "grounding": {"verdict": "grounded", "value": 0.85, "qa_calibration_ok": True},
    }
    text = obs_mod.render_observatory_text(data)
    assert "0.85" in text
    assert "grounding" in text.lower()


def test_render_observatory_text_omits_grounding_when_absent():
    import pytest

    from sovereign_agent.modes_crown import observatory as obs_mod

    if not _patched(obs_mod.render_observatory_text):
        pytest.skip("pre-apply: observatory.py render not yet patched")
    data = {
        "mode": "work", "mode_description": "d", "stance": "(none declared)",
        "stance_history": [], "stress": {}, "emotion": {}, "grounding": None,
    }
    text = obs_mod.render_observatory_text(data)
    assert "⚡ load" in text
