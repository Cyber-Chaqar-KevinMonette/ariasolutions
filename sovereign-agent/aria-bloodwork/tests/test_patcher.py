"""Patcher tests for aria-bloodwork — verify the patch functions against
the CURRENT live files, before anything is applied."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

STAGING = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(STAGING))
from patcher import (  # noqa: E402
    KILL_SWITCH_LINES, MARK, PatchError,
    patch_conformance, patch_doctor, patch_kill_switch_doc,
)

REPO_ROOT = STAGING.parent
SRC = REPO_ROOT / "src" / "sovereign_agent"
BOOTSTRAP_PAYLOAD = STAGING / "payload" / "src" / "sovereign_agent" / "aegis" / "bootstrap.py"


def _compiles(text: str) -> None:
    import py_compile
    import tempfile

    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(text)
        tmp = f.name
    py_compile.compile(tmp, doraise=True)


def _sentinel_path(basename: str) -> Path:
    p = SRC / basename
    return p if p.exists() else SRC / "stewardship" / basename


# ─── kill-switch docs ────────────────────────────────────────────────────


@pytest.mark.parametrize("basename", sorted(KILL_SWITCH_LINES))
def test_kill_switch_doc_applies_idempotent_compiles(basename):
    path = _sentinel_path(basename)
    text = path.read_text(encoding="utf-8")
    once, _ = patch_kill_switch_doc(basename, text)
    assert "SOV_NO_" in once
    twice, changed2 = patch_kill_switch_doc(basename, once)
    assert changed2 is False and twice == once
    _compiles(once)


@pytest.mark.parametrize("basename", sorted(KILL_SWITCH_LINES))
def test_kill_switch_line_lands_inside_module_docstring(basename):
    """The line must land inside the module docstring (visible to help()),
    not as a stray statement after it."""
    path = _sentinel_path(basename)
    once, _ = patch_kill_switch_doc(basename, path.read_text(encoding="utf-8"))
    start = once.index('"""')
    end = once.index('"""', start + 3)
    assert "Kill switch:" in once[start:end]


def test_registry_sentinels_document_a_real_switch():
    """For registry sentinels the documented env var must MATCH what
    base.Sentinel.kill_switch_env actually derives from the class id —
    never document a switch that doesn't work."""
    expected = {
        "godtier_sentinel.py": "SOV_NO_GODTIER_SENTINEL",
        "resilience_sentinel.py": "SOV_NO_RESILIENCE_SENTINEL",
        "peig_sentinel.py": "SOV_NO_PEIG_SENTINEL",
        "tribunal_sentinel.py": "SOV_NO_TRIBUNAL_SENTINEL",
        "atoms_compact_sentinel.py": "SOV_NO_ATOMS_COMPACT_SENTINEL",
        "schedule_sentinel.py": "SOV_NO_SCHEDULE_SENTINEL",
        "cache_sentinel.py": "SOV_NO_CACHE_SENTINEL",
        "glyph_sentinel.py": "SOV_NO_GLYPHS_SENTINEL",
    }
    for basename, env in expected.items():
        assert env in KILL_SWITCH_LINES[basename], basename


def test_pre_registry_sentinels_say_none_honestly():
    for basename in ("temporal_sentinel.py", "integrity_sentinel.py",
                     "skill_sentinel.py", "workflow_sentinel.py"):
        assert "Kill switch: none" in KILL_SWITCH_LINES[basename], basename


def test_unknown_basename_raises():
    with pytest.raises(PatchError):
        patch_kill_switch_doc("not_a_sentinel.py", '"""doc"""\n')


# ─── conformance scoping ─────────────────────────────────────────────────


def test_conformance_applies_idempotent_compiles():
    path = SRC / "stewardship" / "conformance_sentinel.py"
    once, _ = patch_conformance(path.read_text(encoding="utf-8"))
    assert MARK in once
    assert 'search_root = repo_root / "src"' in once
    assert 'py.name.startswith("test_")' in once
    twice, changed2 = patch_conformance(once)
    assert changed2 is False and twice == once
    _compiles(once)


def test_conformance_missing_anchor_raises():
    with pytest.raises(PatchError):
        patch_conformance("no anchors")


# ─── doctor ──────────────────────────────────────────────────────────────


def test_doctor_applies_idempotent_compiles():
    path = SRC / "doctor.py"
    once, _ = patch_doctor(path.read_text(encoding="utf-8"))
    assert MARK in once
    assert "def check_aegis()" in once
    assert "report.checks.append(check_aegis())" in once
    assert '"check_aegis",' in once
    twice, changed2 = patch_doctor(once)
    assert changed2 is False and twice == once
    _compiles(once)


# ─── payload ─────────────────────────────────────────────────────────────


def test_bootstrap_payload_compiles():
    _compiles(BOOTSTRAP_PAYLOAD.read_text(encoding="utf-8"))
