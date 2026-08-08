"""Tests for staged_status.py — the shared is_applied()/pending_modules() logic
factored out of 3 independent copies of the same detection bug (2026-08-02)."""
from __future__ import annotations

from pathlib import Path

from sovereign_agent.staged_status import is_applied, pending_modules


def _mkfile(p: Path, content: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def test_is_applied_via_test_file(tmp_path):
    _mkfile(tmp_path / "tests" / "test_my_feature.py", "# marker\n")
    assert is_applied(tmp_path, "aria-my-feature") is True


def test_is_applied_via_backups_dir(tmp_path):
    (tmp_path / "aria-my-feature" / "backups").mkdir(parents=True)
    assert is_applied(tmp_path, "aria-my-feature") is True


def test_is_applied_payload_parity_fallback(tmp_path):
    mod = "aria-my-domain-thing"
    payload = tmp_path / mod / "payload" / "src" / "sovereign_agent"
    _mkfile(payload / "domain_thing.py", "VALUE = 1\n")

    assert is_applied(tmp_path, mod) is False  # not live yet

    live = tmp_path / "src" / "sovereign_agent"
    _mkfile(live / "domain_thing.py", "VALUE = 2\n")
    assert is_applied(tmp_path, mod) is False  # live but differs — would regress if applied

    _mkfile(live / "domain_thing.py", "VALUE = 1\n")
    assert is_applied(tmp_path, mod) is True  # byte-identical — applied


def test_is_applied_no_payload_no_test_no_backups(tmp_path):
    (tmp_path / "aria-empty").mkdir()
    assert is_applied(tmp_path, "aria-empty") is False


def test_pending_modules_lists_only_unapplied(tmp_path):
    for name in ("aria-done", "aria-todo"):
        (tmp_path / name).mkdir()
        (tmp_path / name / f"apply_{name.removeprefix('aria-')}.sh").write_text("#!/bin/bash\n")
    _mkfile(tmp_path / "tests" / "test_done.py", "# marker\n")

    pending = pending_modules(tmp_path)
    assert pending == ["aria-todo"]
