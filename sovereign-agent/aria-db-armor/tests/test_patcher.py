"""Patcher tests for aria-db-armor — verify the patch functions against the
CURRENT live files, before anything is applied."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

STAGING = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(STAGING))
from patcher import (  # noqa: E402
    MARK, PatchError,
    patch_aegis, patch_feedback, patch_palace, patch_persistence, patch_shards,
)

REPO_ROOT = STAGING.parent
SRC = REPO_ROOT / "src" / "sovereign_agent"

TARGETS = [
    ("palace.py", SRC / "palace.py", patch_palace),
    ("shards.py", SRC / "shards.py", patch_shards),
    ("persistence/store.py", SRC / "persistence" / "store.py", patch_persistence),
    ("feedback/feedback.py", SRC / "feedback" / "feedback.py", patch_feedback),
    ("aegis/bitemporal.py", SRC / "aegis" / "bitemporal.py", patch_aegis),
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
    assert 'PRAGMA busy_timeout = 5000' in once
    twice, changed2 = fn(once)
    assert changed2 is False and twice == once
    _compiles(once)


@pytest.mark.parametrize("name,path,fn", TARGETS, ids=[t[0] for t in TARGETS])
def test_missing_anchor_raises(name, path, fn):
    with pytest.raises(PatchError):
        fn("no anchors here at all")


def test_feedback_all_four_sites_routed_through_helper():
    text = (SRC / "feedback" / "feedback.py").read_text(encoding="utf-8")
    new, _ = patch_feedback(text)
    assert new.count("conn = _connect(self._store._path)") == 4
    assert "conn = sqlite3.connect(str(self._store._path))" not in new


def test_aegis_gains_wal():
    text = (SRC / "aegis" / "bitemporal.py").read_text(encoding="utf-8")
    new, _ = patch_aegis(text)
    assert 'PRAGMA journal_mode = WAL' in new
