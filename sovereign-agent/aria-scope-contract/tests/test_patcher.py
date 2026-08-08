"""Patcher tests for aria-scope-contract — verify against the CURRENT live
files, before anything is applied."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

STAGING = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(STAGING))
from patcher import (  # noqa: E402
    MARK, PatchError, patch_agent_session, patch_bridge, patch_run_surface,
)

REPO_ROOT = STAGING.parent
SRC = REPO_ROOT / "src" / "sovereign_agent"
PAYLOAD = STAGING / "payload" / "src" / "sovereign_agent" / "scope.py"

TARGETS = [
    ("session_bridge.py", SRC / "session_bridge.py", patch_bridge),
    ("agent_session.py", SRC / "agent_session.py", patch_agent_session),
    ("run_surface.py", SRC / "cockpit" / "run_surface.py", patch_run_surface),
]


def _compiles(text: str) -> None:
    import py_compile
    import tempfile

    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(text)
        tmp = f.name
    py_compile.compile(tmp, doraise=True)


@pytest.mark.parametrize("name,path,fn", TARGETS, ids=[t[0] for t in TARGETS])
def test_applies_idempotent_compiles(name, path, fn):
    once, _ = fn(path.read_text(encoding="utf-8"))
    assert MARK in once
    twice, changed2 = fn(once)
    assert changed2 is False and twice == once
    _compiles(once)


@pytest.mark.parametrize("name,path,fn", TARGETS, ids=[t[0] for t in TARGETS])
def test_missing_anchor_raises(name, path, fn):
    with pytest.raises(PatchError):
        fn("no anchors here")


def test_out_of_scope_proposals_held_not_appended_silently():
    new, _ = patch_agent_session((SRC / "agent_session.py").read_text(encoding="utf-8"))
    idx = new.index("is_out_of_scope(desc)")
    body = new[idx:idx + 600]
    assert '"blocked"' in body
    assert "scope-review" in body
    assert '"scope-review-d"' in new
    assert '"scope-drift-d"' in new


def test_scope_is_always_best_effort():
    """A missing/broken contract must never crash a session."""
    new, _ = patch_agent_session((SRC / "agent_session.py").read_text(encoding="utf-8"))
    assert new.count("except Exception:  # noqa: BLE001") >= 2


def test_payload_compiles():
    import py_compile

    py_compile.compile(str(PAYLOAD), doraise=True)
