"""patcher.py — Wellbeing round W5: proving wing + close-out + extensibility retrofit.

The stick before any tuning, for the W1-W4 machinery: five real, scored
tasks wired into the proving ground's own offline suite. Plus a genuine
9th god-tier dimension — "Love & Flourishing" — bringing
`GOD_TIER_STANDARD.md` in line with `GOD_TIER_CRITERIA.md`'s own existing
dimension 9. Plus the extensibility retrofit this round's own asks
require: a marked `{MARK}` extension seam on each of the three
pre-existing modules this round composed but doesn't own.

Patches:
  1. proving_ground/runner.py — SUITE_VERSION v5 → v6, same tail-import
     pattern trust_wing.py/quality_wing.py/grounding_wing.py already use.
  2. GOD_TIER_STANDARD.md — a new 9th dimension, "Love & Flourishing";
     header updated from "eight dimensions" to "nine dimensions".
  3. scripts/lib/god_tier_floor.json — the matching "wellbeing" entry.
  4. stewardship/msims.py — extension seam: a future 4th (Relational)
     dimension.
  5. stewardship/calibration.py — extension seam: honor_score()'s five
     weighted components are already named constants a future round
     could tune from observed calibration accuracy.
  6. tools/companion_tools.py — extension seam: the care-flag/future-flag
     sets are deliberately small and extendable.

Anchored transforms only; MARK-idempotent; a moved anchor raises loudly."""
from __future__ import annotations

MARK = "wellbeing-wing-d"


class PatchError(Exception):
    pass


def _replace_once(text: str, old: str, new: str, *, label: str) -> str:
    if text.count(old) != 1:
        raise PatchError(f"{label}: expected 1 anchor, found {text.count(old)}")
    return text.replace(old, new, 1)


# ── 1. proving_ground/runner.py ──────────────────────────────────────────

VERSION_ANCHOR = (
    'SUITE_VERSION = "v5"  # grounding-wing-d — v5 adds the grounding wing '
    '(G1-G4 machinery); stored scores keep naming the suite they scored'
)

VERSION_NEW = (
    'SUITE_VERSION = "v6"  # wellbeing-wing-d — v6 adds the wellbeing wing '
    '(W1-W4 machinery); stored scores keep naming the suite they scored'
)

TAIL_ANCHOR = '''# grounding-wing-d — Grounding round G5: the grounding wing (persisted composite
# epistemic score, the calibration gate, the fixed-prefix standing audit,
# the measured skeptic lens, the grounded/theoretical stance pair).
from .grounding_wing import GROUNDING_TASKS  # noqa: E402

OFFLINE_TASKS.update(GROUNDING_TASKS)
'''

TAIL_NEW = f'''# grounding-wing-d — Grounding round G5: the grounding wing (persisted composite
# epistemic score, the calibration gate, the fixed-prefix standing audit,
# the measured skeptic lens, the grounded/theoretical stance pair).
from .grounding_wing import GROUNDING_TASKS  # noqa: E402

OFFLINE_TASKS.update(GROUNDING_TASKS)

# {MARK} — Wellbeing round W5: the wellbeing wing (persisted composite
# value/care/flourishing score, persistence at the value_report source,
# the standing audit, the measured angel lens, the reflecting stance).
from .wellbeing_wing import WELLBEING_TASKS  # noqa: E402

OFFLINE_TASKS.update(WELLBEING_TASKS)
'''


def patch_runner(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    text = _replace_once(text, VERSION_ANCHOR, VERSION_NEW, label="SUITE_VERSION")
    text = _replace_once(text, TAIL_ANCHOR, TAIL_NEW, label="offline-suite tail import")
    return text, True


# ── 2. GOD_TIER_STANDARD.md — a new 9th dimension ────────────────────────

HEADER_ANCHOR = "## The eight dimensions of the floor"
HEADER_NEW = "## The nine dimensions of the floor"


def patch_standard_header(text: str) -> tuple[str, bool]:
    if "## The nine dimensions of the floor" in text:
        return text, False
    return _replace_once(text, HEADER_ANCHOR, HEADER_NEW,
                         label="GOD_TIER_STANDARD dimension count header"), True


DIMENSION_ANCHOR = '''8. **Collaboration** — *Floor:* every conflict logged + learned (diagnosis catalog); the human is **more
   capable after each interaction, never more dependent.** *Check:* conflicts → `ConflictCatalog` with a
   rollback. *Ratchet:* feed more lessons back into the PLAYBOOK and into Aria's atoms.

## The 14-generation ratchet (the law of the floor)'''

DIMENSION_NEW = f'''8. **Collaboration** — *Floor:* every conflict logged + learned (diagnosis catalog); the human is **more
   capable after each interaction, never more dependent.** *Check:* conflicts → `ConflictCatalog` with a
   rollback. *Ratchet:* feed more lessons back into the PLAYBOOK and into Aria's atoms.
9. **Love & Flourishing** — *Floor:* a composite value/care/flourishing score is persisted and gates
   apply; a zombie (false-certainty) pass never ships silently. *Check:* `wellbeing.gate()` verdict ≠
   BLOCK. *Ratchet:* fold in more of `stewardship.msims`'s impact-vector richness; widen what's scored.

## The 14-generation ratchet (the law of the floor)'''


def patch_standard_dimension(text: str) -> tuple[str, bool]:
    if "9. **Love & Flourishing**" in text:
        return text, False
    return _replace_once(text, DIMENSION_ANCHOR, DIMENSION_NEW,
                         label="GOD_TIER_STANDARD 9th dimension"), True


def patch_standard(text: str) -> tuple[str, bool]:
    text, c1 = patch_standard_header(text)
    text, c2 = patch_standard_dimension(text)
    return text, (c1 or c2)


# ── 3. scripts/lib/god_tier_floor.json ───────────────────────────────────

FLOOR_JSON_ANCHOR = '''    {
      "id": "collaboration",
      "floor": "Every conflict logged + learned (diagnosis catalog). The human is more capable after each interaction, never more dependent.",
      "check": "conflicts → ConflictCatalog with rollback; honest hand-offs",
      "ratchet": "raise by feeding more lessons back into the playbook"
    }
  ]
}'''

FLOOR_JSON_NEW = '''    {
      "id": "collaboration",
      "floor": "Every conflict logged + learned (diagnosis catalog). The human is more capable after each interaction, never more dependent.",
      "check": "conflicts → ConflictCatalog with rollback; honest hand-offs",
      "ratchet": "raise by feeding more lessons back into the playbook"
    },
    {
      "id": "wellbeing",
      "floor": "A composite value/care/flourishing score is persisted and gates apply. A zombie (false-certainty) pass never ships silently.",
      "check": "wellbeing.gate() verdict != 'BLOCK'",
      "ratchet": "raise by folding in more of stewardship.msims's impact-vector richness"
    }
  ]
}'''


def patch_floor_json(text: str) -> tuple[str, bool]:
    if '"id": "wellbeing"' in text:
        return text, False
    return _replace_once(text, FLOOR_JSON_ANCHOR, FLOOR_JSON_NEW,
                         label="god_tier_floor.json wellbeing entry"), True


# ── 4. stewardship/msims.py — extension seam ──────────────────────────────

MSIMS_ANCHOR = '''__all__ = [
    "Dimension",
    "Scale",
    "Horizon",
    "Reversibility",
    "Cell",
    "ImpactVector",
    "ImpactWaveform",
    "SCALE_WEIGHTS",
    "DIMENSION_WEIGHTS",
    "HORIZON_DISCOUNT",
]'''

MSIMS_NEW = f'''# {MARK} — extension seam: `Dimension` is currently Mental/Physical/
# Financial. A future round could add a 4th (e.g. Relational — the
# quality of the human-Aria relationship itself) without changing
# `ImpactVector`'s aggregate-scoring contract: `dimension_score()`,
# `impact_score()`, and `is_7g()` all iterate `for d in Dimension`
# already, so a new enum member is picked up automatically once
# `DIMENSION_WEIGHTS` names its weight.

__all__ = [
    "Dimension",
    "Scale",
    "Horizon",
    "Reversibility",
    "Cell",
    "ImpactVector",
    "ImpactWaveform",
    "SCALE_WEIGHTS",
    "DIMENSION_WEIGHTS",
    "HORIZON_DISCOUNT",
]'''


def patch_msims(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    return _replace_once(text, MSIMS_ANCHOR, MSIMS_NEW,
                         label="stewardship/msims.py extension seam"), True


# ── 5. stewardship/calibration.py — extension seam ────────────────────────

CALIBRATION_ANCHOR = '''    total = (
        alpha * pq
        + beta * cal
        + gamma * impact
        - delta * zombie
        + epsilon * bonus
    )'''

CALIBRATION_NEW = f'''    # {MARK} — extension seam: alpha/beta/gamma/delta/epsilon are already
    # named, independent weights (not a single hand-tuned formula) — a
    # future round could tune them from observed calibration accuracy
    # (how often a high predicted_iv confidence matched the actual_iv)
    # instead of the current hand-picked defaults, without changing this
    # function's signature or its callers.
    total = (
        alpha * pq
        + beta * cal
        + gamma * impact
        - delta * zombie
        + epsilon * bonus
    )'''


def patch_calibration(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    return _replace_once(text, CALIBRATION_ANCHOR, CALIBRATION_NEW,
                         label="stewardship/calibration.py extension seam"), True


# ── 6. tools/companion_tools.py — extension seam ──────────────────────────

COMPANION_ANCHOR = '''    return {
        "accomplished": accomplished[:10],
        "value_shown": value_shown[:5],
        "seeds": seeds[:5],
        "overall_grade": grade,
        "summary": summary,
        "event_count_analyzed": len(events),
        "note": (
            "Love is shown in work, not words. "
            "A grade of C or D means: what could have been done differently?"
        ),
    }'''

COMPANION_NEW = f'''    # {MARK} — extension seam: the care-flag/future-flag sets above are
    # deliberately small and named (not a catch-all) — the moment a new
    # event flag proves worth classifying as an accomplishment, a care
    # signal, or a seed, it's a one-line addition to the matching set,
    # no change to this function's return contract.
    return {{
        "accomplished": accomplished[:10],
        "value_shown": value_shown[:5],
        "seeds": seeds[:5],
        "overall_grade": grade,
        "summary": summary,
        "event_count_analyzed": len(events),
        "note": (
            "Love is shown in work, not words. "
            "A grade of C or D means: what could have been done differently?"
        ),
    }}'''


def patch_companion_tools(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    return _replace_once(text, COMPANION_ANCHOR, COMPANION_NEW,
                         label="companion_tools.py extension seam"), True


ALL_PATCHES = {
    "proving_ground/runner.py": patch_runner,
    "stewardship/msims.py": patch_msims,
    "stewardship/calibration.py": patch_calibration,
    "tools/companion_tools.py": patch_companion_tools,
}

DOC_PATCHES = {
    "GOD_TIER_STANDARD.md": patch_standard,
}

FLOOR_JSON_PATCHES = {
    "lib/god_tier_floor.json": patch_floor_json,
}
