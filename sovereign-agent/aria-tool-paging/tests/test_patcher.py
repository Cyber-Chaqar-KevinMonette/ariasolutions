"""Patcher tests for aria-tool-paging — verify against the CURRENT live
files, before anything is applied."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

STAGING = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(STAGING))
from patcher import (  # noqa: E402
    MARK, PatchError, patch_loop, patch_prompt_diet, patch_tools_init,
)

REPO_ROOT = STAGING.parent
SRC = REPO_ROOT / "src" / "sovereign_agent"
PAYLOAD = STAGING / "payload" / "src" / "sovereign_agent" / "tools" / "tool_paging.py"

TARGETS = [
    ("loop.py", SRC / "loop.py", patch_loop),
    ("tools/__init__.py", SRC / "tools" / "__init__.py", patch_tools_init),
    ("prompt_diet.py", SRC / "prompt_diet.py", patch_prompt_diet),
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


def test_unknown_tool_becomes_helpful():
    new, _ = patch_loop((SRC / "loop.py").read_text(encoding="utf-8"))
    assert "get_close_matches" in new
    assert "NOT ATTACHED" in new
    assert "request_tools" in new


def test_paging_is_authority_gated_and_capped():
    new, _ = patch_loop((SRC / "loop.py").read_text(encoding="utf-8"))
    idx = new.index('if tool_name == "request_tools" and result.ok:')
    body = new[idx:idx + 1400]
    # gated: only names from the loop's own authority meta-list attach
    assert "for m in available" in body
    # capped: MAX_PAGED_TOTAL bounds the schema budget
    assert "MAX_PAGED_TOTAL" in body
    assert '"tool-paged-d"' in body


def test_diet_core_gains_the_attachment_half():
    new, _ = patch_prompt_diet((SRC / "prompt_diet.py").read_text(encoding="utf-8"))
    assert '"request_tools",' in new


def test_payload_compiles_and_documents_bounds():
    import py_compile

    py_compile.compile(str(PAYLOAD), doraise=True)
    text = PAYLOAD.read_text(encoding="utf-8")
    assert "MAX_NAMES_PER_CALL" in text
    assert "MAX_PAGED_TOTAL" in text
