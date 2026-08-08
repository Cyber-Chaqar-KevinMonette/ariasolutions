"""aria-quality-modes — a quality stance with a real tooth.
(Quality round · Q4)

Patch-only — no new payload files. All three patched files
(`modes_crown/stances.py`, `session_bridge.py`, `modes_crown/observatory.py`)
already exist live; every behavior here is patch-dependent and skips
honestly pre-apply. The apply script re-runs this file and requires zero
skips.
"""
from __future__ import annotations

import inspect

MARK = "quality-modes-d"


def _patched(obj) -> bool:
    return MARK in inspect.getsource(obj)


# ─── (1) SAFE_STANCES + set_stance side effect ───────────────────────────


def test_quality_pass_in_safe_stances_once_patched():
    import pytest

    from sovereign_agent.modes_crown import stances as stances_mod

    if not _patched(stances_mod):
        pytest.skip("pre-apply: stances.py not yet patched")
    assert "quality-pass" in stances_mod.SAFE_STANCES


def test_set_stance_quality_pass_triggers_a_real_ledger_entry(tmp_path):
    import pytest

    from sovereign_agent.modes_crown import stances as stances_mod

    if not _patched(stances_mod):
        pytest.skip("pre-apply: stances.py not yet patched")
    from sovereign_agent.quality import latest_quality

    data_dir = tmp_path / "data"
    data_dir.mkdir(exist_ok=True)
    before = latest_quality(data_dir)
    assert before is None

    stances_mod.set_stance("quality-pass", data_dir=data_dir)

    after = latest_quality(data_dir)
    assert after is not None
    assert "value" in after
    assert "critical_ok" in after


def test_set_stance_quality_pass_never_crashes_with_no_git_repo(tmp_path, monkeypatch):
    """The stance change itself must survive even if the change-detection
    subprocess call fails entirely (no repo, git missing, etc)."""
    import pytest

    from sovereign_agent.modes_crown import stances as stances_mod

    if not _patched(stances_mod):
        pytest.skip("pre-apply: stances.py not yet patched")

    monkeypatch.setattr(stances_mod, "_changed_py_files_since_head",
                        lambda data_dir: (_ for _ in ()).throw(RuntimeError("boom")))
    data_dir = tmp_path / "data"
    data_dir.mkdir(exist_ok=True)
    rec = stances_mod.set_stance("quality-pass", data_dir=data_dir)
    assert rec["stance"] == "quality-pass"


# ─── (2) quality_gate_clear() ─────────────────────────────────────────────


def test_quality_gate_clear_true_when_not_in_the_stance(tmp_path):
    import pytest

    from sovereign_agent.modes_crown import stances as stances_mod

    if not _patched(stances_mod):
        pytest.skip("pre-apply: quality_gate_clear not yet added")
    data_dir = tmp_path / "data"
    data_dir.mkdir(exist_ok=True)
    assert stances_mod.quality_gate_clear(data_dir) is True


def test_quality_gate_clear_false_then_true_across_a_real_pass(tmp_path, monkeypatch):
    import pytest

    from sovereign_agent.modes_crown import stances as stances_mod

    if not _patched(stances_mod):
        pytest.skip("pre-apply: quality_gate_clear not yet added")

    data_dir = tmp_path / "data"
    data_dir.mkdir(exist_ok=True)
    # enter the stance with the ledger side effect disabled, so it starts
    # unclear (mirrors a fresh entry before any pass has landed)
    monkeypatch.setattr(stances_mod, "_run_quality_pass_for_stance",
                        lambda data_dir: None)
    stances_mod.set_stance("quality-pass", data_dir=data_dir)
    assert stances_mod.quality_gate_clear(data_dir) is False

    from sovereign_agent.quality import record_quality_pass

    record_quality_pass([], data_dir=data_dir)
    assert stances_mod.quality_gate_clear(data_dir) is True


def test_quality_gate_clear_false_when_the_pass_had_a_critical_failure(tmp_path, monkeypatch):
    import pytest

    from sovereign_agent.modes_crown import stances as stances_mod

    if not _patched(stances_mod):
        pytest.skip("pre-apply: quality_gate_clear not yet added")

    data_dir = tmp_path / "data"
    data_dir.mkdir(exist_ok=True)
    monkeypatch.setattr(stances_mod, "_run_quality_pass_for_stance",
                        lambda data_dir: None)
    stances_mod.set_stance("quality-pass", data_dir=data_dir)

    bad = tmp_path / "bad.py"
    bad.write_text("def f(a):\n    return a\n", encoding="utf-8")
    from sovereign_agent.quality import record_quality_pass

    record_quality_pass([bad], data_dir=data_dir)
    assert stances_mod.quality_gate_clear(data_dir) is False


# ─── (3) the crown gate ───────────────────────────────────────────────────


def _armed_profile():
    from sovereign_agent.modes_crown.profiles import ModeProfile

    return ModeProfile("work", "Work", base="work", tier_ceiling=1,
                       description="test", work_allowed=True,
                       garden_required=False)


def test_crown_gate_blocks_dispatch_while_quality_pass_unclear(tmp_path, monkeypatch):
    import pytest

    from sovereign_agent import session_bridge

    if not _patched(session_bridge._crown_gate):
        pytest.skip("pre-apply: _crown_gate not yet patched")

    from sovereign_agent.modes_crown import profiles as profiles_mod
    from sovereign_agent.modes_crown import stances as stances_mod

    data_dir = tmp_path / "data"
    data_dir.mkdir(exist_ok=True)
    monkeypatch.setattr(profiles_mod, "crown_armed", lambda data_dir=None: True)
    monkeypatch.setattr(profiles_mod, "current_profile",
                        lambda data_dir=None: _armed_profile())
    monkeypatch.setattr(stances_mod, "_run_quality_pass_for_stance",
                        lambda data_dir: None)
    stances_mod.set_stance("quality-pass", data_dir=data_dir)
    monkeypatch.setattr(stances_mod, "current_stance",
                        lambda data_dir=None: "quality-pass")
    monkeypatch.setattr(stances_mod, "quality_gate_clear",
                        lambda data_dir=None: False)

    with pytest.raises(PermissionError, match="quality pass"):
        session_bridge._crown_gate("a new goal")


def test_crown_gate_permits_dispatch_once_quality_gate_clears(monkeypatch):
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
    monkeypatch.setattr(stances_mod, "current_stance",
                        lambda data_dir=None: "quality-pass")
    monkeypatch.setattr(stances_mod, "quality_gate_clear",
                        lambda data_dir=None: True)

    session_bridge._crown_gate("a new goal")  # must not raise


def test_crown_gate_untouched_when_stance_is_not_quality_pass(monkeypatch):
    """Every other stance is unaffected — byte-identical to before this
    patch when the operator isn't in quality-pass at all."""
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
    monkeypatch.setattr(stances_mod, "current_stance",
                        lambda data_dir=None: "planning")

    session_bridge._crown_gate("a new goal")  # must not raise


# ─── (4) observatory ───────────────────────────────────────────────────────


def test_observatory_carries_the_quality_field(tmp_path):
    import pytest

    from sovereign_agent.modes_crown import observatory as obs_mod

    if not _patched(obs_mod.gather_observatory):
        pytest.skip("pre-apply: observatory.py not yet patched")
    from sovereign_agent.quality import record_quality_pass

    data_dir = tmp_path / "data"
    data_dir.mkdir(exist_ok=True)
    record_quality_pass([], data_dir=data_dir)

    data = obs_mod.gather_observatory(data_dir)
    assert "quality" in data
    assert data["quality"] is not None
    assert "value" in data["quality"]


def test_observatory_quality_field_is_none_with_no_pass_yet(tmp_path):
    import pytest

    from sovereign_agent.modes_crown import observatory as obs_mod

    if not _patched(obs_mod.gather_observatory):
        pytest.skip("pre-apply: observatory.py not yet patched")
    data = obs_mod.gather_observatory(tmp_path / "data")
    assert data.get("quality") is None


def test_render_observatory_text_shows_quality_when_present():
    import pytest

    from sovereign_agent.modes_crown import observatory as obs_mod

    if not _patched(obs_mod.render_observatory_text):
        pytest.skip("pre-apply: observatory.py render not yet patched")
    data = {
        "mode": "work", "mode_description": "d", "stance": "quality-pass",
        "stance_history": [], "stress": {}, "emotion": {},
        "quality": {"value": 91.5, "critical_ok": True},
    }
    text = obs_mod.render_observatory_text(data)
    assert "91.5" in text
    assert "quality" in text.lower()


def test_render_observatory_text_omits_quality_when_absent():
    import pytest

    from sovereign_agent.modes_crown import observatory as obs_mod

    if not _patched(obs_mod.render_observatory_text):
        pytest.skip("pre-apply: observatory.py render not yet patched")
    data = {
        "mode": "work", "mode_description": "d", "stance": "(none declared)",
        "stance_history": [], "stress": {}, "emotion": {}, "quality": None,
    }
    text = obs_mod.render_observatory_text(data)
    assert "⚡ load" in text
