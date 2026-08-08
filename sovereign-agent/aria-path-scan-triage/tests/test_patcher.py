"""Patcher tests for aria-path-scan-triage — verify the patch functions
against the CURRENT live files, before anything is applied."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

STAGING = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(STAGING))
from patcher import MARK, PatchError, patch_main, patch_scanner  # noqa: E402

REPO_ROOT = STAGING.parent
SCANNER = REPO_ROOT / "src" / "sovereign_agent" / "path_scan" / "scanner.py"
MAIN = REPO_ROOT / "src" / "sovereign_agent" / "path_scan" / "__main__.py"
TRIAGE_PAYLOAD = STAGING / "payload" / "src" / "sovereign_agent" / "path_scan" / "triage.py"


def _compiles(text: str) -> None:
    import py_compile
    import tempfile

    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(text)
        tmp = f.name
    py_compile.compile(tmp, doraise=True)


def test_scanner_applies_idempotent_compiles():
    once, _ = patch_scanner(SCANNER.read_text(encoding="utf-8"))
    assert MARK in once
    twice, changed2 = patch_scanner(once)
    assert changed2 is False and twice == once
    _compiles(once)


def test_scan_one_is_untouched():
    """THE safety property: the apply-time gate keeps full block semantics —
    the patch must not modify scan_one's body at all."""
    before = SCANNER.read_text(encoding="utf-8")
    after, _ = patch_scanner(before)

    def _fn_body(text: str, name: str) -> str:
        start = text.index(f"def {name}(")
        nxt = text.find("\ndef ", start + 1)
        return text[start:nxt]

    assert _fn_body(before, "scan_one") == _fn_body(after, "scan_one")


def test_downgrade_is_best_effort_never_a_blocker():
    once, _ = patch_scanner(SCANNER.read_text(encoding="utf-8"))
    idx = once.index("def scan_repo(")
    body = once[idx:idx + 2000]
    assert body.count("except Exception") >= 2


def test_historicize_shape():
    once, _ = patch_scanner(SCANNER.read_text(encoding="utf-8"))
    assert 'kind=f"historical/{f.kind}"' in once
    assert 'severity="warn"' in once


def test_main_applies_idempotent_compiles():
    once, _ = patch_main(MAIN.read_text(encoding="utf-8"))
    assert MARK in once
    assert '"triage"' in once
    twice, changed2 = patch_main(once)
    assert changed2 is False and twice == once
    _compiles(once)


def test_missing_anchor_raises():
    with pytest.raises(PatchError):
        patch_scanner("no anchors")
    with pytest.raises(PatchError):
        patch_main("no anchors")


def test_triage_payload_compiles():
    _compiles(TRIAGE_PAYLOAD.read_text(encoding="utf-8"))
