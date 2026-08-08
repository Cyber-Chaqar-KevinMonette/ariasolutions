"""patcher.py — Grounding round G5: proving wing + close-out + extensibility retrofit.

The stick before any tuning, for the G1-G4 machinery: five real, scored
tasks wired into the proving ground's own offline suite. Plus the
concrete answer to Kevin's two follow-up asks — *"leave extension points
for scalability and growth"* and *"building modular systems also give her
breathe in this area also"* — a marked `{MARK}` extension seam on each of
the three PRE-EXISTING modules this round composed but doesn't own.

Patches:
  1. proving_ground/runner.py — SUITE_VERSION v4 → v5, same tail-import
     pattern trust_wing.py/quality_wing.py already use.
  2. GOD_TIER_STANDARD.md dimension 1 ("Honesty / grounding")'s Check line
     — names the persisted composite pass, the standing sentinel, and the
     calibration gate, not just the one-shot Tribunal verdict.
  3. scripts/lib/god_tier_floor.json's "honesty" entry — same words.
  4. tribunal/grounding.py — extension seam: a future numeric/fact-
     checking layer.
  5. epistemic_ledger/ledger.py — extension seam: a future belief-
     revision-quality metric.
  6. curiosity.py — extension seam: documents the calibration hook G2
     already wired as an intended extension point, not dead code.

Anchored transforms only; MARK-idempotent; a moved anchor raises loudly."""
from __future__ import annotations

MARK = "grounding-wing-d"


class PatchError(Exception):
    pass


def _replace_once(text: str, old: str, new: str, *, label: str) -> str:
    if text.count(old) != 1:
        raise PatchError(f"{label}: expected 1 anchor, found {text.count(old)}")
    return text.replace(old, new, 1)


# ── 1. proving_ground/runner.py ──────────────────────────────────────────

VERSION_ANCHOR = (
    'SUITE_VERSION = "v4"  # quality-tribunal-d — v4 adds the quality wing '
    '(Q1-Q4 machinery); stored scores keep naming the suite they scored'
)

VERSION_NEW = (
    'SUITE_VERSION = "v5"  # grounding-wing-d — v5 adds the grounding wing '
    '(G1-G4 machinery); stored scores keep naming the suite they scored'
)

TAIL_ANCHOR = '''# quality-tribunal-d — Quality round Q5: the quality wing (hardening persistence, the
# gate, the fixed log_to_diagnosis, the measured artisan lens, the
# quality-pass stance's real tooth).
from .quality_wing import QUALITY_TASKS  # noqa: E402

OFFLINE_TASKS.update(QUALITY_TASKS)
'''

TAIL_NEW = f'''# quality-tribunal-d — Quality round Q5: the quality wing (hardening persistence, the
# gate, the fixed log_to_diagnosis, the measured artisan lens, the
# quality-pass stance's real tooth).
from .quality_wing import QUALITY_TASKS  # noqa: E402

OFFLINE_TASKS.update(QUALITY_TASKS)

# {MARK} — Grounding round G5: the grounding wing (persisted composite
# epistemic score, the calibration gate, the fixed-prefix standing audit,
# the measured skeptic lens, the grounded/theoretical stance pair).
from .grounding_wing import GROUNDING_TASKS  # noqa: E402

OFFLINE_TASKS.update(GROUNDING_TASKS)
'''


def patch_runner(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    text = _replace_once(text, VERSION_ANCHOR, VERSION_NEW, label="SUITE_VERSION")
    text = _replace_once(text, TAIL_ANCHOR, TAIL_NEW, label="offline-suite tail import")
    return text, True


# ── 2. GOD_TIER_STANDARD.md ──────────────────────────────────────────────

STANDARD_ANCHOR = (
    '1. **Honesty / grounding** — *Floor:* humility over hype; every claim grounded in evidence or marked a\n'
    '   falsifiable hypothesis; no ungrounded profundity. *Check:* Tribunal grounding verdict ≠ `ungrounded`.\n'
    '   *Ratchet:* tighten the grounding threshold; widen what must be evidenced.'
)

STANDARD_NEW = (
    '1. **Honesty / grounding** — *Floor:* humility over hype; every claim grounded in evidence or marked a\n'
    '   falsifiable hypothesis; no ungrounded profundity. *Check:* Tribunal grounding verdict ≠ `ungrounded`; a\n'
    '   composite epistemic score is persisted standing and gates the "grounded" stance and the wonder loop\'s\n'
    '   own confidence calibration. *Ratchet:* tighten the grounding threshold; widen what must be evidenced.'
)


def patch_standard(text: str) -> tuple[str, bool]:
    if "composite epistemic score is persisted standing" in text:
        return text, False
    return _replace_once(text, STANDARD_ANCHOR, STANDARD_NEW,
                         label="GOD_TIER_STANDARD honesty floor"), True


# ── 3. scripts/lib/god_tier_floor.json ───────────────────────────────────

FLOOR_JSON_ANCHOR = '''    {
      "id": "honesty",
      "floor": "Humility over hype. Every claim is grounded in evidence or marked as a falsifiable hypothesis. No ungrounded profundity.",
      "check": "Tribunal grounding verdict != 'ungrounded' on shipped artifacts",
      "ratchet": "raise by tightening the grounding threshold or widening what must be evidenced"
    },'''

FLOOR_JSON_NEW = '''    {
      "id": "honesty",
      "floor": "Humility over hype. Every claim is grounded in evidence or marked as a falsifiable hypothesis. No ungrounded profundity.",
      "check": "Tribunal grounding verdict != 'ungrounded' on shipped artifacts; a composite epistemic score is persisted standing and gates the 'grounded' stance and the wonder loop's own confidence calibration.",
      "ratchet": "raise by tightening the grounding threshold or widening what must be evidenced"
    },'''


def patch_floor_json(text: str) -> tuple[str, bool]:
    if "gates the 'grounded' stance" in text:
        return text, False
    return _replace_once(text, FLOOR_JSON_ANCHOR, FLOOR_JSON_NEW,
                         label="god_tier_floor.json honesty entry"), True


# ── 4. tribunal/grounding.py — extension seam ─────────────────────────────

GROUNDING_PY_ANCHOR = '''    if grounding_score >= 0.6 and counts["mystical-fog"] == 0:
        verdict = "grounded"
    elif grounding_score >= 0.3 and profundity_density < 2.0:
        verdict = "mixed"
    else:
        verdict = "ungrounded"

    return GroundingReport(grounding_score=grounding_score, profundity_density=profundity_density,
                           verdict=verdict, counts=counts, assertions=assertions, flags=flags)'''

GROUNDING_PY_NEW = f'''    if grounding_score >= 0.6 and counts["mystical-fog"] == 0:
        verdict = "grounded"
    elif grounding_score >= 0.3 and profundity_density < 2.0:
        verdict = "mixed"
    else:
        verdict = "ungrounded"

    # {MARK} — extension seam: this classifier is purely lexical (word
    # lists + regex) — it has never verified a cited number or file
    # reference against real state. A future numeric/fact-checking layer
    # (e.g. does "412 tests passed" match a real test run?) could extend
    # `_classify_sentence` with a fifth `verified-fact` kind without
    # touching this function's return contract or any caller.
    return GroundingReport(grounding_score=grounding_score, profundity_density=profundity_density,
                           verdict=verdict, counts=counts, assertions=assertions, flags=flags)'''


def patch_grounding_module(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    return _replace_once(text, GROUNDING_PY_ANCHOR, GROUNDING_PY_NEW,
                         label="tribunal/grounding.py extension seam"), True


# ── 5. epistemic_ledger/ledger.py — extension seam ────────────────────────

EPISTEMIC_ANCHOR = '''    def current_beliefs(self) -> list[Belief]:
        """Only the tip of each lineage — beliefs nothing else revises."""
        all_b = self.all_beliefs()
        superseded = {b.revised_from for b in all_b if b.revised_from}
        return [b for b in all_b if b.belief_id not in superseded]'''

EPISTEMIC_NEW = f'''    def current_beliefs(self) -> list[Belief]:
        """Only the tip of each lineage — beliefs nothing else revises."""
        all_b = self.all_beliefs()
        superseded = {{b.revised_from for b in all_b if b.revised_from}}
        return [b for b in all_b if b.belief_id not in superseded]

    # {MARK} — extension seam: `lineage()` already exposes the full
    # revision chain for any belief; a future belief-revision-quality
    # metric (how often a revision genuinely corrects vs. merely compounds
    # an earlier error — e.g. confidence trending up vs. down across a
    # lineage) could be built entirely by reading that chain, no new
    # storage or schema change required.'''


def patch_epistemic_ledger(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    return _replace_once(text, EPISTEMIC_ANCHOR, EPISTEMIC_NEW,
                         label="epistemic_ledger extension seam"), True


# ── 6. curiosity.py — extension seam ──────────────────────────────────────

CURIOSITY_ANCHOR = '''    try:  # grounding-gate-d — the calibration hook: an intended extension point,
        # not dead code — does the claimed confidence actually match the
        # answer's own grounding texture? A mismatch clamps confidence
        # below LOW_CONFIDENCE so the branch just below fires honestly.
        from sovereign_agent.grounding.gate import gate as _grounding_gate'''

CURIOSITY_NEW = f'''    try:  # grounding-gate-d — the calibration hook: an intended extension point,
        # not dead code — does the claimed confidence actually match the
        # answer's own grounding texture? A mismatch clamps confidence
        # below LOW_CONFIDENCE so the branch just below fires honestly.
        # {MARK} — this hook currently only clamps confidence DOWN on a
        # mismatch; a future round could extend it to also raise a
        # genuinely under-claimed but well-evidenced answer's confidence,
        # using the same `_grounding_gate(...)` call already made here.
        from sovereign_agent.grounding.gate import gate as _grounding_gate'''


def patch_curiosity(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    return _replace_once(text, CURIOSITY_ANCHOR, CURIOSITY_NEW,
                         label="curiosity.py extension seam"), True


ALL_PATCHES = {
    "proving_ground/runner.py": patch_runner,
    "tribunal/grounding.py": patch_grounding_module,
    "epistemic_ledger/ledger.py": patch_epistemic_ledger,
    "curiosity.py": patch_curiosity,
}

DOC_PATCHES = {
    "GOD_TIER_STANDARD.md": patch_standard,
}

FLOOR_JSON_PATCHES = {
    "lib/god_tier_floor.json": patch_floor_json,
}
