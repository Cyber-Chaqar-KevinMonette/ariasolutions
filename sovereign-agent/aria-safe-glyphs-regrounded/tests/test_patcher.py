"""Patcher tests for aria-safe-glyphs-regrounded — verify both patch
functions against the CURRENT live files, before anything is applied."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

STAGING = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(STAGING))
from patcher import MARK, PatchError, patch_cli, patch_requests  # noqa: E402

REPO_ROOT = STAGING.parent
REQUESTS_PATH = REPO_ROOT / "src" / "sovereign_agent" / "workflow" / "requests.py"
CLI_PATH = REPO_ROOT / "src" / "sovereign_agent" / "cli.py"

VS16 = "️"
ZWJ = "‍"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_patch_requests_applies_cleanly():
    new_text, _ = patch_requests(_text(REQUESTS_PATH))  # changed may be False if already applied
    assert MARK in new_text


def test_patch_cli_applies_cleanly():
    new_text, _ = patch_cli(_text(CLI_PATH))  # changed may be False if already applied
    assert MARK in new_text


def test_patch_requests_is_idempotent():
    once, _ = patch_requests(_text(REQUESTS_PATH))
    twice, changed2 = patch_requests(once)
    assert changed2 is False
    assert once == twice


def test_patch_cli_is_idempotent():
    once, _ = patch_cli(_text(CLI_PATH))
    twice, changed2 = patch_cli(once)
    assert changed2 is False
    assert once == twice


def test_patched_requests_has_zero_vs16_or_zwj():
    new_text, _ = patch_requests(_text(REQUESTS_PATH))
    assert VS16 not in new_text
    assert ZWJ not in new_text


def test_patched_cli_has_zero_vs16_or_zwj():
    new_text, _ = patch_cli(_text(CLI_PATH))
    assert VS16 not in new_text
    assert ZWJ not in new_text


def test_patched_files_compile():
    import py_compile
    import tempfile

    new_req, _ = patch_requests(_text(REQUESTS_PATH))
    new_cli, _ = patch_cli(_text(CLI_PATH))
    for text in (new_req, new_cli):
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
            f.write(text)
            tmp_path = f.name
        py_compile.compile(tmp_path, doraise=True)


def test_priority_emoji_normal_key_preserved_not_removed():
    """VALID_PRIORITY = frozenset(PRIORITY_EMOJI) depends on 'normal'
    staying a valid dict key — only its glyph value should become empty,
    the key must never be deleted."""
    new_text, _ = patch_requests(_text(REQUESTS_PATH))
    assert '"normal": ""' in new_text
    assert 'VALID_PRIORITY = frozenset(PRIORITY_EMOJI)' in new_text


def test_missing_anchor_raises_patch_error_not_silent_noop():
    with pytest.raises(PatchError):
        patch_requests("this text has none of the expected anchors")
    with pytest.raises(PatchError):
        patch_cli("this text has none of the expected anchors")


def test_already_patched_text_is_a_noop_for_both():
    req_once, _ = patch_requests(_text(REQUESTS_PATH))
    req_twice, changed = patch_requests(req_once)
    assert changed is False
    assert req_twice == req_once

    cli_once, _ = patch_cli(_text(CLI_PATH))
    cli_twice, changed = patch_cli(cli_once)
    assert changed is False
    assert cli_twice == cli_once
