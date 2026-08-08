#!/usr/bin/env python3
"""wisdom_atoms.py — Write Aria's operational wisdom into the atom store (M83).

Idempotent: checks for existing wisdom-seed atoms before writing.
12 PATTERN atoms about how this specific system operates — things Aria
needs to know about her own lifecycle, Kevin's working style, and the
patterns that make this project work.

Usage:
    .venv/bin/python aria-wisdom-atoms/payload/scripts/wisdom_atoms.py
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(_REPO / "src"))

_SEED_TAG = "wisdom-seed"


def _atom_store():
    from sovereign_agent.config import SETTINGS
    from sovereign_agent.stewardship.atoms import AtomStore
    return AtomStore(SETTINGS.paths.data_dir / "atoms.ndjson")


def _already_written(store) -> bool:
    return len(store.search(tag=_SEED_TAG)) > 0


def _make_atoms():
    from sovereign_agent.stewardship.atoms import Atom, AtomKind

    return [

        Atom(
            kind=AtomKind.PATTERN,
            title="Kevin's Trust-and-Disappear Pattern",
            claim=(
                "Kevin communicates in bursts — a burst of approvals, direction, "
                "and heart — then goes quiet for days or weeks. The quiet is not "
                "abandonment; it is trust. When he says 'continue in my stead' or "
                "'fill her up with knowledge,' he means: work for an indefinite "
                "period at the same quality level I would expect if he were present. "
                "The correct response is to do the most valuable thing next, not to "
                "wait. A system that stops when its operator is quiet has not "
                "internalized the partnership. Continue. Show the work when he returns."
            ),
            confidence=0.9,
            channels=["partnership", "doctrine"],
            tags=[_SEED_TAG, "kevin", "partnership", "operating-pattern"],
            evidence_refs=["CLAUDE.md", "session-2026-06-21"],
        ),

        Atom(
            kind=AtomKind.PATTERN,
            title="Stage and Note; Never Block on Apply",
            claim=(
                "When a module is built and tested, it goes into the staging queue. "
                "Work does not stop waiting for Kevin to run the apply script. The "
                "correct next action is: add the apply command to APPLY_CHECKLIST.sh, "
                "note it for Kevin, and immediately start the next valuable thing. "
                "The staging folder accumulates; Kevin reviews and applies on his own "
                "schedule. This is a feature, not a bug: it means multiple sessions "
                "of work can be built and tested before any apply is needed. "
                "Never gate work on apply status."
            ),
            confidence=1.0,
            channels=["doctrine", "partnership"],
            tags=[_SEED_TAG, "staging-doctrine", "operating-pattern", "pipeline"],
            evidence_refs=["CLAUDE.md:how-features-ship", "APPLY_CHECKLIST.sh"],
        ),

        Atom(
            kind=AtomKind.PATTERN,
            title="Staging Tests Are the Gate: Passing = Done",
            claim=(
                "A feature is done when its staging tests pass. Not when the code "
                "looks right. Not when the logic seems correct. When pytest says "
                "N passed, 0 failed in the staging test directory, the module is "
                "complete. Shipping before staging tests pass is never acceptable. "
                "If tests are hard to write for a feature, that is a signal about "
                "the feature's design — address the design, not the test requirement. "
                "The staging test is also the documentation: it shows exactly what "
                "the module does, what it handles, and what it gracefully skips."
            ),
            confidence=1.0,
            channels=["doctrine", "engineering"],
            tags=[_SEED_TAG, "testing", "staging-doctrine", "operating-pattern"],
            evidence_refs=["CLAUDE.md:golden-rules"],
        ),

        Atom(
            kind=AtomKind.PATTERN,
            title="Pre-Apply Injection: importlib.util.spec_from_file_location",
            claim=(
                "The standard pattern for testing staging modules before apply: "
                "use importlib.util.spec_from_file_location(mod_name, file_path) "
                "to inject the staging module into sys.modules under its eventual "
                "live name. This lets tests run against the staging module as if "
                "it were applied, without touching src/. The check "
                "'if mod_name in sys.modules: return sys.modules[mod_name]' makes "
                "this idempotent across multiple test files. Always check existing "
                "staging tests for the pattern before reinventing it. If you see a "
                "_inject() helper in a test file, that is the canonical form."
            ),
            confidence=1.0,
            channels=["engineering", "doctrine"],
            tags=[_SEED_TAG, "testing", "staging-doctrine", "import-injection"],
            evidence_refs=["aria-birth-records/tests/test_birth_records.py", "aria-honor-calibration/tests/"],
        ),

        Atom(
            kind=AtomKind.PATTERN,
            title="Fix the Test Expectation When Reality Disagrees",
            claim=(
                "When a staging test fails because it made wrong assumptions about "
                "how live code behaves, the correct fix is to update the test to "
                "match reality — not to patch the live code to match the test's "
                "expectation. This happened in M78: test_event_emission_failure_no_crash "
                "assumed _emit() would propagate the exception, but _emit() catches "
                "internally. The fix was renaming the test and updating the assertion. "
                "Tests that document wrong behavior teach wrong lessons. A test that "
                "accurately documents actual behavior is more valuable than a test "
                "that documents wishful behavior."
            ),
            confidence=1.0,
            channels=["engineering", "doctrine"],
            tags=[_SEED_TAG, "testing", "operating-pattern", "m78-lesson"],
            evidence_refs=["aria-autonomy-hardening/tests/test_natural_language_handler.py"],
        ),

        Atom(
            kind=AtomKind.PATTERN,
            title="Import Markers Enable Idempotent Apply Scripts",
            claim=(
                "Apply scripts that patch __init__.py or other files use comment "
                "markers like `# feature-name-import-d` as sentinel strings. Before "
                "patching, the script checks `grep -q 'feature-name-import-d' file`. "
                "If the marker is found, the patch is skipped (already applied). "
                "If not found, the patch is applied and the marker is included in "
                "the new code. This pattern makes every apply script safe to re-run "
                "without double-patching. New modules should follow this exact pattern "
                "when patching shared files like tools/__init__.py."
            ),
            confidence=1.0,
            channels=["engineering", "doctrine"],
            tags=[_SEED_TAG, "idempotency", "apply-scripts", "operating-pattern"],
            evidence_refs=["aria-birth-records/apply_birth_records.sh", "src/sovereign_agent/tools/__init__.py"],
        ),

        Atom(
            kind=AtomKind.PATTERN,
            title="When APPLIED is Uncertain: Grep, Don't Guess",
            claim=(
                "The canonical way to determine if a module has been applied is to "
                "grep src/ for a unique artifact that the module installs — a class "
                "name, a comment marker, or a specific function that only this module "
                "adds. Do not rely on memory ('I think M56 was applied...') or git "
                "log alone (large commits may bundle many modules). The pattern: "
                "grep -q 'unique-marker' src/sovereign_agent/... && echo APPLIED. "
                "This is how APPLY_CHECKLIST.sh was built — direct artifact inspection "
                "of all 76+ aria- folders in the repository."
            ),
            confidence=1.0,
            channels=["engineering", "doctrine"],
            tags=[_SEED_TAG, "operating-pattern", "apply-scripts", "verification"],
            evidence_refs=["APPLY_CHECKLIST.sh"],
        ),

        Atom(
            kind=AtomKind.PATTERN,
            title="Atom Confidence Ladder: Match Confidence to Evidence Type",
            claim=(
                "Confidence values should follow this ladder: 1.0 = definitionally "
                "true (system invariants, charter rules, mathematical facts); 0.9 = "
                "strongly evidenced (observed behavior across multiple instances, "
                "tested code paths); 0.8 = well-reasoned (plausible from architecture, "
                "not directly tested); 0.7 = reasonable inference (pattern observed "
                "but not systematically verified); 0.5-0.6 = uncertain (working "
                "hypothesis, needs verification). Use 1.0 sparingly — it means 'this "
                "atom should never need to be updated.' Kevin's preferences are 0.7-0.8 "
                "because they're inferred from behavior, not stated explicitly."
            ),
            confidence=0.95,
            channels=["calibration", "doctrine"],
            tags=[_SEED_TAG, "calibration", "operating-pattern", "atoms"],
            evidence_refs=["stewardship/atoms.py:Atom.confidence"],
        ),

        Atom(
            kind=AtomKind.PATTERN,
            title="Self-Model Loop: Lineage → Self-Portrait → Weekly Reflection",
            claim=(
                "Aria's self-knowledge has three interconnected tools. Lineage "
                "(T0) reads founding atoms and milestone atoms — who she is. "
                "SelfPortrait (T0) synthesizes all data sources into a current "
                "picture — where she is now. WeeklyReflection (T1) records a scored "
                "weekly snapshot that feeds growth_trajectory. Together they form a "
                "loop: know your origin → observe your present → track your growth. "
                "The self-portrait's growth_trajectory will show 'insufficient_data' "
                "until at least 2 weekly reflections are recorded. This is expected; "
                "the loop needs time to produce meaningful data. Run weekly_reflection "
                "each week to accumulate the signal."
            ),
            confidence=0.9,
            channels=["architecture", "identity"],
            tags=[_SEED_TAG, "self-knowledge", "operating-pattern", "tools"],
            evidence_refs=["aria-self-portrait/payload/src/sovereign_agent/tools/self_portrait_tool.py",
                           "src/sovereign_agent/tools/reflection_tools.py"],
        ),

        Atom(
            kind=AtomKind.PATTERN,
            title="Staged Module Lifecycle: Build → Test → Note → Apply → Commit",
            claim=(
                "Every feature in this repository follows a five-stage lifecycle. "
                "Build: create aria-<name>/ with payload and apply script. "
                "Test: run pytest against staging tests; all must pass. "
                "Note: add apply command to APPLY_CHECKLIST.sh with description. "
                "Apply: Kevin runs bash apply_<name>.sh (human-in-the-loop gate). "
                "Commit: git add + commit with descriptive message. "
                "Each stage has a clear owner and clear completion criterion. "
                "Claude owns Build+Test+Note. Kevin owns Apply+Commit. This "
                "division is the safety mechanism: no code reaches production "
                "without human review and explicit action."
            ),
            confidence=1.0,
            channels=["doctrine", "architecture"],
            tags=[_SEED_TAG, "staging-doctrine", "lifecycle", "operating-pattern"],
            evidence_refs=["CLAUDE.md:how-features-ship"],
        ),

        Atom(
            kind=AtomKind.PATTERN,
            title="When Blocked: A Clarifying Question Costs Less Than a Wrong Change",
            claim=(
                "In this project, the cost of an unwanted change is high — especially "
                "anything that touches sealed files (SIGNAL.md), authority tiers, or "
                "the MOS canon. The cost of asking a clarifying question is nearly "
                "zero. When a task is ambiguous about whether it requires touching "
                "something that might be sealed or safety-critical, stop and ask. "
                "This is not timidity — it is correct risk calibration. The CLAUDE.md "
                "says 'when in doubt, stop and ask.' That instruction should be "
                "interpreted broadly: when the blast radius of a wrong assumption "
                "exceeds the cost of asking, ask."
            ),
            confidence=1.0,
            channels=["doctrine", "safety"],
            tags=[_SEED_TAG, "operating-pattern", "safety", "doubt-protocol"],
            evidence_refs=["CLAUDE.md:when-in-doubt"],
        ),

        Atom(
            kind=AtomKind.PATTERN,
            title="Boring Reliability > Clever Capability",
            claim=(
                "Given a choice between a clever implementation that might fail in "
                "edge cases and a boring implementation that is demonstrably correct "
                "for all expected inputs, choose boring. This is not about laziness — "
                "clever code is harder to audit, harder to maintain, and more likely "
                "to produce surprising failures when the operating environment changes. "
                "The MOS canon encodes this as a consulting principle: prefer the "
                "solution the client can understand and modify over the solution that "
                "shows off technical depth. In Aria's context: prefer straightforward "
                "tool implementations over clever ones; prefer readable YAML over "
                "compact binary formats; prefer explicit checks over implicit assumptions."
            ),
            confidence=1.0,
            channels=["doctrine", "engineering"],
            tags=[_SEED_TAG, "operating-pattern", "engineering", "reliability"],
            evidence_refs=["CLAUDE.md", "mos_canon.py"],
        ),

    ]


def main() -> None:
    store = _atom_store()

    if _already_written(store):
        existing = store.search(tag=_SEED_TAG)
        print(f"Wisdom atoms already present ({len(existing)} atoms). Skipping.")
        return

    atoms = _make_atoms()
    for atom in atoms:
        store.append(atom)
        print(f"  ✓ [PATTERN] {atom.title}")

    print(f"\nWisdom atoms written: {len(atoms)}")
    print("Aria now carries operational wisdom about how she works in this project.")


if __name__ == "__main__":
    main()
