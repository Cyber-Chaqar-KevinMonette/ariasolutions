"""Text-transform tests for aria-checkpoint-chunks's patcher.py — proves the
tools/__init__.py, loop.py, and cockpit/app.py patches apply cleanly against
the CURRENT live files, are idempotent, and the patched result compiles."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from patcher import MARK, patch_app, patch_loop, patch_tools_init  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
TOOLS_INIT_PY = REPO_ROOT / "src" / "sovereign_agent" / "tools" / "__init__.py"
LOOP_PY = REPO_ROOT / "src" / "sovereign_agent" / "loop.py"
APP_PY = REPO_ROOT / "src" / "sovereign_agent" / "cockpit" / "app.py"


def _compiles(text: str) -> None:
    import py_compile
    import tempfile

    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as fh:
        fh.write(text)
        tmp_name = fh.name
    py_compile.compile(tmp_name, doraise=True)


def test_patch_tools_init_applies_and_is_idempotent():
    text = TOOLS_INIT_PY.read_text(encoding="utf-8")
    once, _ = patch_tools_init(text)  # changed may be False if already applied
    assert MARK in once
    assert "from .recall_chunk_tool import RecallChunkTool" in once
    assert '"RecallChunkTool"' in once
    twice, changed_again = patch_tools_init(once)
    assert not changed_again
    assert twice == once


def test_patched_tools_init_compiles():
    text = TOOLS_INIT_PY.read_text(encoding="utf-8")
    patched, _ = patch_tools_init(text)
    _compiles(patched)


def test_patch_loop_applies_and_is_idempotent():
    text = LOOP_PY.read_text(encoding="utf-8")
    once, _ = patch_loop(text)  # changed may be False if already applied
    assert MARK in once
    assert "recall_chunk(keyword)" in once
    assert "compress_context()" in once  # still mentioned — not removed
    twice, changed_again = patch_loop(once)
    assert not changed_again
    assert twice == once


def test_patched_loop_compiles():
    text = LOOP_PY.read_text(encoding="utf-8")
    patched, _ = patch_loop(text)
    _compiles(patched)


def test_patch_app_applies_and_is_idempotent():
    text = APP_PY.read_text(encoding="utf-8")
    once, _ = patch_app(text)  # changed may be False if already applied
    assert MARK in once
    assert "ChunkRecorder" in once
    assert "_chunk_session_id" in once
    twice, changed_again = patch_app(once)
    assert not changed_again
    assert twice == once


def test_patched_app_compiles():
    text = APP_PY.read_text(encoding="utf-8")
    patched, _ = patch_app(text)
    _compiles(patched)
