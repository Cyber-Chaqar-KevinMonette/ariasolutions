"""Behavior tests for aria-cosmic-fitness-restore — prove the patch actually fixes
the crash (CosmicFitnessScreen + WorkflowsScreen import cleanly afterward), is
idempotent, and never touches the live repo directly (pure string transform).

SUPERSEDED (2026-07-04, gym-round triage): the fragment-patching mechanism this
file tests was abandoned MID-BUILD in favor of a full git-restore of app.py
(commit 16baa1d — see this module's own apply script and the plan's P0 Progress
entry). The P0 crash it guarded against has been fixed, verified, and committed
for weeks; live app.py has since grown by thousands of lines, so the historical
patcher's anchors (e.g. its `grid-import` import-line anchor) no longer exist —
these tests fail on a stale premise, not a live bug. Kept as provenance;
skipped as a suite member. The LIVE regression coverage for the original crash
is `tests/test_cosmic_fitness.py` (imports CosmicFitnessScreen from the real
cockpit), which remains fully active.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytest.skip(
    "historical: tests a patch mechanism superseded by the full git-restore "
    "(commit 16baa1d); live coverage lives in tests/test_cosmic_fitness.py",
    allow_module_level=True,
)

from patcher import ALL_MARKERS, PatchError, is_fully_patched, patch  # noqa: E402

FRAG_DIR = Path(__file__).parents[1] / "patch_fragments"
REPO_ROOT = Path(__file__).parents[2]
BAK_APP = (
    REPO_ROOT / "src/sovereign_agent/cockpit/app.py.bak.20260623142159"
)


def _live_app_text() -> str:
    """The CURRENT live app.py — the one that's actually crashing."""
    return (REPO_ROOT / "src/sovereign_agent/cockpit/app.py").read_text(encoding="utf-8")


# ── the actual crash, fixed ─────────────────────────────────────────────────

def test_patch_makes_live_app_py_compile_and_import_clean(tmp_path):
    """The real regression test: patch the CURRENT live app.py (read-only source),
    write the result to an isolated shadow copy of the whole package, and confirm
    CosmicFitnessScreen + WorkflowsScreen import cleanly — never touching real src."""
    import py_compile
    import shutil

    new_text, changed = patch(_live_app_text(), FRAG_DIR)
    assert set(changed) == {"grid-import", "import", "classes", "methods", "dispatch"}

    shadow = tmp_path / "shadow"
    shutil.copytree(REPO_ROOT / "src/sovereign_agent", shadow / "sovereign_agent")
    (shadow / "sovereign_agent/cockpit/app.py").write_text(new_text, encoding="utf-8")
    for pyc in shadow.rglob("__pycache__"):
        shutil.rmtree(pyc)

    py_compile.compile(
        str(shadow / "sovereign_agent/cockpit/app.py"), doraise=True
    )

    # Save-and-restore, never destroy: deleting sys.modules entries outright
    # (the original approach here) has a session-wide side effect far beyond
    # this test — it decouples singletons like sovereign_agent.config.SETTINGS
    # from whatever tests/conftest.py's isolation fixture patched via
    # object.__setattr__ (which relies on object IDENTITY, not just being
    # importable again). Once a singleton like that gets silently replaced,
    # every test that runs afterward in the same pytest process quietly
    # starts reading/writing real paths instead of its own isolated tmp_path.
    # Saving the exact prior module objects and restoring them in `finally`
    # keeps this test's shadow-import trick fully self-contained.
    saved = {
        name: mod for name, mod in sys.modules.items()
        if name == "sovereign_agent" or name.startswith("sovereign_agent.")
    }
    for name in saved:
        del sys.modules[name]

    sys.path.insert(0, str(shadow))
    try:
        from sovereign_agent.cockpit import (  # noqa: F401
            CockpitApp,
            CosmicFitnessScreen,
            WorkflowsScreen,
        )
    finally:
        sys.path.remove(str(shadow))
        for name in list(sys.modules):
            if name == "sovereign_agent" or name.startswith("sovereign_agent."):
                del sys.modules[name]
        sys.modules.update(saved)


def test_patch_is_idempotent():
    """Running the patch twice must not double-insert anything (no duplicate
    decorators, no duplicate methods) — the exact bug class this module's own
    dry-run caught once already (a stray @dataclass(frozen=True) duplicate)."""
    once, changed_once = patch(_live_app_text(), FRAG_DIR)
    assert changed_once  # the live file is genuinely unpatched right now
    twice, changed_twice = patch(once, FRAG_DIR)
    assert changed_twice == []
    assert twice == once


def test_is_fully_patched_reports_true_after_patch_false_before():
    assert not is_fully_patched(_live_app_text())
    patched, _ = patch(_live_app_text(), FRAG_DIR)
    assert is_fully_patched(patched)


def test_all_markers_present_after_patch():
    patched, _ = patch(_live_app_text(), FRAG_DIR)
    for marker in ALL_MARKERS:
        assert marker in patched


# ── failure mode: a moved anchor is a loud error, never a silent corruption ──

def test_missing_anchor_raises_patch_error_not_silent_corruption():
    broken = _live_app_text().replace(
        "logger = logging.getLogger(__name__)", "logger = get_logger(__name__)"
    )
    with pytest.raises(PatchError):
        patch(broken, FRAG_DIR)


# ── fragments are self-consistent (parens balance, no leftover decorators) ──

@pytest.mark.parametrize(
    "fragment", ["classes_block.py", "methods_block.py", "dispatch_block.py"]
)
def test_fragment_parens_are_balanced(fragment):
    text = (FRAG_DIR / fragment).read_text(encoding="utf-8")
    assert text.count("(") == text.count(")"), fragment


def test_classes_fragment_does_not_end_with_a_dangling_decorator():
    """Regression for the exact bug this module's own build hit: the fragment
    used to end with a lone `@dataclass(frozen=True)` that stacked with the
    anchor's own copy, causing 'Cannot overwrite attribute __setattr__'."""
    text = (FRAG_DIR / "classes_block.py").read_text(encoding="utf-8").rstrip()
    assert not text.endswith("@dataclass(frozen=True)")
