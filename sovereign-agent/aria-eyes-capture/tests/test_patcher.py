"""Patcher tests for aria-eyes-capture — verify all three patch functions
against the CURRENT live files, before anything is applied."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

STAGING = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(STAGING))
from patcher import (  # noqa: E402
    MARK,
    PatchError,
    patch_eyes,
    patch_senses_tools,
    patch_tools_init,
)

REPO_ROOT = STAGING.parent
EYES_PATH = REPO_ROOT / "src" / "sovereign_agent" / "senses" / "eyes.py"
SENSES_TOOLS_PATH = REPO_ROOT / "src" / "sovereign_agent" / "tools" / "senses_tools.py"
TOOLS_INIT_PATH = REPO_ROOT / "src" / "sovereign_agent" / "tools" / "__init__.py"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "path,fn",
    [(EYES_PATH, patch_eyes), (SENSES_TOOLS_PATH, patch_senses_tools), (TOOLS_INIT_PATH, patch_tools_init)],
)
def test_patch_applies_cleanly(path, fn):
    new_text, _ = fn(_text(path))  # changed may be False if already applied
    assert MARK in new_text


@pytest.mark.parametrize(
    "path,fn",
    [(EYES_PATH, patch_eyes), (SENSES_TOOLS_PATH, patch_senses_tools), (TOOLS_INIT_PATH, patch_tools_init)],
)
def test_patch_is_idempotent(path, fn):
    once, _ = fn(_text(path))
    twice, changed2 = fn(once)
    assert changed2 is False
    assert once == twice


@pytest.mark.parametrize(
    "path,fn",
    [(EYES_PATH, patch_eyes), (SENSES_TOOLS_PATH, patch_senses_tools), (TOOLS_INIT_PATH, patch_tools_init)],
)
def test_patched_file_compiles(path, fn):
    import py_compile
    import tempfile

    new_text, _ = fn(_text(path))
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(new_text)
        tmp_path = f.name
    py_compile.compile(tmp_path, doraise=True)


def test_look_world_and_see_are_completely_unmodified():
    """The core regression guard: look_world()/see() must stay byte-
    identical to the original — capture_frame() is purely additive,
    inserted AFTER look_world() ends, never called by it.

    Uses the patcher's own LOOK_WORLD_END_ANCHOR (the exact known-good
    pre-patch text) as ground truth rather than slicing it out of live
    text, which is only reliable pre-apply — once applied, live already
    has capture_frame() inserted right after look_world(), so a naive
    "from look_world() to look_screen()" slice would wrongly include it."""
    from patcher import LOOK_WORLD_END_ANCHOR

    assert "capture_frame" not in LOOK_WORLD_END_ANCHOR  # sanity on the known-good anchor

    original = _text(EYES_PATH)
    new_text, _ = patch_eyes(original)
    # the exact original look_world() body must still appear verbatim
    assert LOOK_WORLD_END_ANCHOR in new_text
    # and capture_frame's own definition sits AFTER that unchanged block
    capture_def_idx = new_text.index("def capture_frame(")
    anchor_idx = new_text.index(LOOK_WORLD_END_ANCHOR)
    assert capture_def_idx > anchor_idx


def test_capture_frame_added_and_never_auto_invoked():
    new_text, _ = patch_eyes(_text(EYES_PATH))
    assert "def capture_frame(" in new_text
    # confirm it's not called anywhere else in the file except its own definition
    calls = new_text.count("capture_frame(")
    definitions = new_text.count("def capture_frame(")
    assert calls == definitions  # only ever defined, never called internally


def test_capture_frame_tool_is_tier_1_not_tier_0():
    new_text, _ = patch_senses_tools(_text(SENSES_TOOLS_PATH))
    tool_start = new_text.index("class CaptureFrameTool")
    tool_slice = new_text[tool_start : tool_start + 600]
    assert "tier = 1" in tool_slice


def test_tools_init_import_and_all_both_added_together():
    """L's own lesson this session: a missing __all__ entry is a real,
    recurring bug class — always add import + __all__ together."""
    new_text, _ = patch_tools_init(_text(TOOLS_INIT_PATH))
    assert "from .senses_tools import CaptureFrameTool" in new_text
    assert '"CaptureFrameTool"' in new_text


def test_missing_anchor_raises_patch_error_not_silent_noop():
    with pytest.raises(PatchError):
        patch_eyes("no anchors here")
    with pytest.raises(PatchError):
        patch_senses_tools("no anchors here")
    with pytest.raises(PatchError):
        patch_tools_init("no anchors here")
