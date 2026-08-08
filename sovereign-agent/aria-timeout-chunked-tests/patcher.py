"""patcher.py — Timeout round T5: document the pytest-chunking convention.

Patches .claude/PLAYBOOK.md — adds a line to the Environment section
naming `scripts/run_tests_chunked.sh` as the standard full-suite
verification command, closing the gap the research found: nothing in
CLAUDE.md/PLAYBOOK.md addressed the literal thing that happened twice
this session (a pytest chunk exceeding the harness's own command
timeout).
"""
from __future__ import annotations

MARK = "timeout-chunked-tests-d"


class PatchError(Exception):
    pass


def _replace_once(text: str, old: str, new: str, *, label: str) -> str:
    if text.count(old) != 1:
        raise PatchError(f"{label}: expected 1 anchor, found {text.count(old)}")
    return text.replace(old, new, 1)


ANCHOR = '''## Environment
`.venv/bin/python` · `.venv/bin/sovereign` (never system Python). Version source of truth:
`src/sovereign_agent/__init__.py` `__version__` → after any bump update `pyproject.toml` AND
`.venv/bin/pip install -e .` (CacheSentinel drift trap). Tests: `.venv/bin/python -m pytest`.'''

NEW = f'''## Environment
`.venv/bin/python` · `.venv/bin/sovereign` (never system Python). Version source of truth:
`src/sovereign_agent/__init__.py` `__version__` → after any bump update `pyproject.toml` AND
`.venv/bin/pip install -e .` (CacheSentinel drift trap). Tests: `.venv/bin/python -m pytest`.
**Full-suite verification (a command-timeout-safe harness): `./scripts/run_tests_chunked.sh`**
({MARK}) — chunks `tests/test_*.py` (default 10 chunks, 270s each) and auto-bisects any chunk
that TIMES OUT (never a real failure — those are surfaced directly) until the exact slow/hung
file is isolated. Prefer this over a single unchunked `pytest` run for the full suite.'''


def patch_playbook(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    return _replace_once(text, ANCHOR, NEW, label=".claude/PLAYBOOK.md Environment section"), True


DOC_PATCHES = {
    ".claude/PLAYBOOK.md": patch_playbook,
}
