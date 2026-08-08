"""Patcher tests for aria-session-bridge — verify against the CURRENT live
files, before anything is applied."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

STAGING = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(STAGING))
from patcher import MARK, PatchError, patch_agent_session, patch_app  # noqa: E402

REPO_ROOT = STAGING.parent
AGENT_SESSION = REPO_ROOT / "src" / "sovereign_agent" / "agent_session.py"
APP_PY = REPO_ROOT / "src" / "sovereign_agent" / "cockpit" / "app.py"
PAYLOAD = STAGING / "payload" / "src" / "sovereign_agent" / "session_bridge.py"


def _compiles(text: str) -> None:
    import py_compile
    import tempfile

    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(text)
        tmp = f.name
    py_compile.compile(tmp, doraise=True)


def test_agent_session_applies_idempotent_compiles():
    once, _ = patch_agent_session(AGENT_SESSION.read_text(encoding="utf-8"))
    assert MARK in once
    twice, changed2 = patch_agent_session(once)
    assert changed2 is False and twice == once
    _compiles(once)


def test_boundary_delivery_is_best_effort_and_tag_scoped():
    once, _ = patch_agent_session(AGENT_SESSION.read_text(encoding="utf-8"))
    idx = once.index("drain_operator_messages")
    surrounding = once[max(0, idx - 500):idx + 900]
    assert "try:" in surrounding and "except Exception" in surrounding
    assert "OPERATOR MESSAGES" in surrounding


def test_gates_untouched():
    """The four gates' bodies must be byte-identical before/after — the
    bridge adds delivery, never weakens a gate."""
    before = AGENT_SESSION.read_text(encoding="utf-8")
    after, _ = patch_agent_session(before)
    for gate in ("Gate 1: PROTOCOL-ZERO", "Gate 2: Operator interrupt",
                 "Gate 3: Session-level budget", "Gate 4: Authority check"):
        b_idx = before.index(gate)
        a_idx = after.index(gate)
        assert before[b_idx:b_idx + 400] == after[a_idx:a_idx + 400], gate


def test_app_applies_idempotent_compiles():
    once, _ = patch_app(APP_PY.read_text(encoding="utf-8"))
    assert MARK in once
    twice, changed2 = patch_app(once)
    assert changed2 is False and twice == once
    _compiles(once)


def test_work_verb_and_gate_wired():
    new, _ = patch_app(APP_PY.read_text(encoding="utf-8"))
    assert 'elif verb == "work":' in new
    assert "autonomous_loops_allowed" in new
    # the never-called gate finally has a caller
    assert "allowed = autonomous_loops_allowed()" in new


def test_busy_branch_queues_instead_of_dropping():
    new, _ = patch_app(APP_PY.read_text(encoding="utf-8"))
    idx = new.index('if getattr(self, "_session_running", False):')
    surrounding = new[idx:idx + 400]
    assert "_queue_for_aria(text)" in surrounding
    # ordinary-busy behavior preserved right after
    assert "aria is still working" in new


def test_chat_mode_proposes_never_runs():
    new, _ = patch_app(APP_PY.read_text(encoding="utf-8"))
    idx = new.index("if not allowed:")
    surrounding = new[idx:idx + 700]
    assert "proposed, waiting" in surrounding
    assert "return" in surrounding
    assert "_run_work_session_worker" not in surrounding


def test_missing_anchor_raises():
    with pytest.raises(PatchError):
        patch_agent_session("no anchors")
    with pytest.raises(PatchError):
        patch_app("no anchors")


def test_payload_compiles():
    import py_compile

    py_compile.compile(str(PAYLOAD), doraise=True)
