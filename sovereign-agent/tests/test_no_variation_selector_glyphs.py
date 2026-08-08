"""Regression test for the safe-glyphs bug: glyphs like '⚠️' / '⏸️' / '▪️'
are a base character plus an invisible variation selector (U+FE0F).
Terminals disagree on their cell width, the cursor desyncs from what's
drawn, and the TUI layout visibly corrupts.

`aria-safe-glyphs/` fixed this once; Workstream O's full rewrite of
`requests.py` (the dual-inbox build, same session) predates that fix and
reintroduced the exact same glyphs — this test is the actual fix for the
*recurrence*, not just the glyph swap itself. The original module had
this exact test but it was never promoted to live `tests/`, which is
very likely why the regression went undetected.

Scoped to the three files the original bug targeted (the TUI-rendering
surface), not a whole-tree sweep — `qa/edge_cases.py` legitimately uses a
ZWJ emoji sequence as an edge-case test fixture, and `aria_lm/data.py`
has a VS16 glyph in an internal data-processing heuristic list; neither
is ever rendered to a terminal, so neither belongs in this check.
"""
from __future__ import annotations

from pathlib import Path

VS16 = "️"
ZWJ = "‍"

_TUI_FILES = (
    "src/sovereign_agent/workflow/requests.py",
    "src/sovereign_agent/cli.py",
    "src/sovereign_agent/cockpit/app.py",
)


def _find_repo_root(start: Path) -> Path:
    for candidate in (start, *start.parents):
        if (candidate / "src" / "sovereign_agent" / "cockpit" / "app.py").is_file():
            return candidate
    raise RuntimeError("could not locate repo root from " + str(start))


REPO_ROOT = _find_repo_root(Path(__file__).resolve())


def test_no_variation_selector_or_zwj_in_tui_facing_modules():
    offenders = []
    for rel_path in _TUI_FILES:
        path = REPO_ROOT / rel_path
        text = path.read_text(encoding="utf-8")
        for i, line in enumerate(text.splitlines(), start=1):
            if VS16 in line or ZWJ in line:
                offenders.append(f"{rel_path}:{i}: {line.strip()!r}")

    assert not offenders, (
        "Found variation-selector-16 (U+FE0F) or ZWJ (U+200D) characters in "
        "TUI-facing code — these glitch terminal cell-width alignment:\n  "
        + "\n  ".join(offenders)
    )


def test_status_and_priority_emoji_are_single_codepoint():
    """Direct check of the specific dicts that caused the regression."""
    from sovereign_agent.workflow.requests import PRIORITY_EMOJI, STATUS_EMOJI

    for name, value in {**STATUS_EMOJI, **PRIORITY_EMOJI}.items():
        assert VS16 not in value, f"{name!r} still has a variation selector: {value!r}"
        assert ZWJ not in value, f"{name!r} still has a ZWJ: {value!r}"
