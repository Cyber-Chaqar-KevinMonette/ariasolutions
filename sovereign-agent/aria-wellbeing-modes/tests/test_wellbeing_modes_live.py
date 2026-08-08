"""aria-wellbeing-modes — a stance for deliberate reflection.
(Wellbeing round · W4)

Patch-only — no new payload files. All three patched files already exist
live; every behavior here is patch-dependent and skips honestly
pre-apply. The apply script re-runs this file and requires zero skips.
"""
from __future__ import annotations

import inspect
import json

MARK = "wellbeing-modes-d"

HEALTHY_EVENTS = [
    {"flag": "commit-d", "payload": {"message": "fix the loader bug"}},
    {"flag": "presence-note-d", "payload": {}},
]


def _patched(obj) -> bool:
    return MARK in inspect.getsource(obj)


def _write_events_file(data_dir, events):
    from datetime import datetime, timezone

    events_dir = data_dir / "events"
    events_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    path = events_dir / f"events-{today}.jsonl"
    with path.open("w", encoding="utf-8") as fh:
        for e in events:
            fh.write(json.dumps(e) + "\n")


# ─── (1) SAFE_STANCES + set_stance side effect ────────────────────────────


def test_reflecting_in_safe_stances_once_patched():
    import pytest

    from sovereign_agent.modes_crown import stances as stances_mod

    if not _patched(stances_mod):
        pytest.skip("pre-apply: stances.py not yet patched")
    assert "reflecting" in stances_mod.SAFE_STANCES


def test_set_stance_reflecting_triggers_a_real_ledger_entry(tmp_path):
    import pytest

    from sovereign_agent.modes_crown import stances as stances_mod

    if not _patched(stances_mod):
        pytest.skip("pre-apply: stances.py not yet patched")
    from sovereign_agent.wellbeing import latest_wellbeing

    data_dir = tmp_path / "data"
    data_dir.mkdir(exist_ok=True)
    _write_events_file(data_dir, HEALTHY_EVENTS)
    assert latest_wellbeing(data_dir) is None

    stances_mod.set_stance("reflecting", data_dir=data_dir)

    latest = latest_wellbeing(data_dir)
    assert latest is not None


def test_set_stance_reflecting_never_crashes_with_no_events_anywhere(tmp_path, monkeypatch):
    import pytest

    from sovereign_agent.modes_crown import stances as stances_mod

    if not _patched(stances_mod):
        pytest.skip("pre-apply: stances.py not yet patched")
    monkeypatch.setattr(stances_mod, "_recent_events_for_stance",
                        lambda data_dir: (_ for _ in ()).throw(RuntimeError("boom")))
    data_dir = tmp_path / "data"
    data_dir.mkdir(exist_ok=True)
    rec = stances_mod.set_stance("reflecting", data_dir=data_dir)
    assert rec["stance"] == "reflecting"


# ─── (2) wellbeing_gate_clear() ────────────────────────────────────────────


def test_wellbeing_gate_clear_true_when_not_in_the_stance(tmp_path):
    import pytest

    from sovereign_agent.modes_crown import stances as stances_mod

    if not _patched(stances_mod):
        pytest.skip("pre-apply: wellbeing_gate_clear not yet added")
    data_dir = tmp_path / "data"
    data_dir.mkdir(exist_ok=True)
    assert stances_mod.wellbeing_gate_clear(data_dir) is True


def test_wellbeing_gate_clear_false_then_true_across_a_real_healthy_pass(tmp_path, monkeypatch):
    import pytest

    from sovereign_agent.modes_crown import stances as stances_mod

    if not _patched(stances_mod):
        pytest.skip("pre-apply: wellbeing_gate_clear not yet added")

    data_dir = tmp_path / "data"
    data_dir.mkdir(exist_ok=True)
    monkeypatch.setattr(stances_mod, "_run_wellbeing_pass_for_stance",
                        lambda data_dir: None)
    stances_mod.set_stance("reflecting", data_dir=data_dir)
    assert stances_mod.wellbeing_gate_clear(data_dir) is False

    from sovereign_agent.wellbeing import record_wellbeing_pass

    record_wellbeing_pass(HEALTHY_EVENTS, data_dir=data_dir)
    assert stances_mod.wellbeing_gate_clear(data_dir) is True


def test_wellbeing_gate_clear_false_when_the_pass_was_strained(tmp_path, monkeypatch):
    import pytest

    from sovereign_agent.modes_crown import stances as stances_mod

    if not _patched(stances_mod):
        pytest.skip("pre-apply: wellbeing_gate_clear not yet added")

    data_dir = tmp_path / "data"
    data_dir.mkdir(exist_ok=True)
    monkeypatch.setattr(stances_mod, "_run_wellbeing_pass_for_stance",
                        lambda data_dir: None)
    stances_mod.set_stance("reflecting", data_dir=data_dir)

    from sovereign_agent.wellbeing import record_wellbeing_pass

    record_wellbeing_pass([{"flag": "unrecognized-flag-d", "payload": {}}], data_dir=data_dir)
    assert stances_mod.wellbeing_gate_clear(data_dir) is False


# ─── (3) the crown gate ────────────────────────────────────────────────────


def _armed_profile():
    from sovereign_agent.modes_crown.profiles import ModeProfile

    return ModeProfile("work", "Work", base="work", tier_ceiling=1,
                       description="test", work_allowed=True,
                       garden_required=False)


def test_crown_gate_blocks_dispatch_while_reflecting_unclear(monkeypatch):
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
    monkeypatch.setattr(stances_mod, "current_stance", lambda data_dir=None: "reflecting")
    monkeypatch.setattr(stances_mod, "quality_gate_clear", lambda data_dir=None: True)
    monkeypatch.setattr(stances_mod, "grounding_gate_clear", lambda data_dir=None: True)
    monkeypatch.setattr(stances_mod, "wellbeing_gate_clear", lambda data_dir=None: False)

    with pytest.raises(PermissionError, match="wellbeing pass"):
        session_bridge._crown_gate("a new goal")


def test_crown_gate_permits_dispatch_once_wellbeing_gate_clears(monkeypatch):
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
    monkeypatch.setattr(stances_mod, "current_stance", lambda data_dir=None: "reflecting")
    monkeypatch.setattr(stances_mod, "quality_gate_clear", lambda data_dir=None: True)
    monkeypatch.setattr(stances_mod, "grounding_gate_clear", lambda data_dir=None: True)
    monkeypatch.setattr(stances_mod, "wellbeing_gate_clear", lambda data_dir=None: True)

    session_bridge._crown_gate("a new goal")  # must not raise


def test_crown_gate_untouched_when_stance_is_not_reflecting(monkeypatch):
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
    monkeypatch.setattr(stances_mod, "current_stance", lambda data_dir=None: "planning")

    session_bridge._crown_gate("a new goal")  # must not raise


# ─── observatory ───────────────────────────────────────────────────────────


def test_observatory_carries_the_wellbeing_field(tmp_path):
    import pytest

    from sovereign_agent.modes_crown import observatory as obs_mod

    if not _patched(obs_mod.gather_observatory):
        pytest.skip("pre-apply: observatory.py not yet patched")
    from sovereign_agent.wellbeing import record_wellbeing_pass

    data_dir = tmp_path / "data"
    data_dir.mkdir(exist_ok=True)
    record_wellbeing_pass(HEALTHY_EVENTS, data_dir=data_dir)

    data = obs_mod.gather_observatory(data_dir)
    assert "wellbeing" in data
    assert data["wellbeing"] is not None
    assert "verdict" in data["wellbeing"]


def test_observatory_wellbeing_field_is_none_with_no_pass_yet(tmp_path):
    import pytest

    from sovereign_agent.modes_crown import observatory as obs_mod

    if not _patched(obs_mod.gather_observatory):
        pytest.skip("pre-apply: observatory.py not yet patched")
    data = obs_mod.gather_observatory(tmp_path / "data")
    assert data.get("wellbeing") is None


def test_render_observatory_text_shows_wellbeing_when_present():
    import pytest

    from sovereign_agent.modes_crown import observatory as obs_mod

    if not _patched(obs_mod.render_observatory_text):
        pytest.skip("pre-apply: observatory.py render not yet patched")
    data = {
        "mode": "work", "mode_description": "d", "stance": "reflecting",
        "stance_history": [], "stress": {}, "emotion": {},
        "wellbeing": {"verdict": "healthy", "love_grade": "A", "impact_is_zombie": False},
    }
    text = obs_mod.render_observatory_text(data)
    assert "healthy" in text
    assert "wellbeing" in text.lower()


def test_render_observatory_text_omits_wellbeing_when_absent():
    import pytest

    from sovereign_agent.modes_crown import observatory as obs_mod

    if not _patched(obs_mod.render_observatory_text):
        pytest.skip("pre-apply: observatory.py render not yet patched")
    data = {
        "mode": "work", "mode_description": "d", "stance": "(none declared)",
        "stance_history": [], "stress": {}, "emotion": {}, "wellbeing": None,
    }
    text = obs_mod.render_observatory_text(data)
    assert "⚡ load" in text
