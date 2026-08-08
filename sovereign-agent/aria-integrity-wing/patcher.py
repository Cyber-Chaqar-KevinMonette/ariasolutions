"""patcher.py — Integrity round I5: proving wing wiring + doc sync.

Patches:
  1. proving_ground/runner.py — SUITE_VERSION v6 -> v7, tail-import of
     INTEGRITY_TASKS folded into OFFLINE_TASKS, same pattern every prior
     wing used.
  2. GOD_TIER_STANDARD.md — dimension 1 ("Honesty / grounding")'s Check
     line extended to also name the persisted integrity composite +
     standing sentinel + gate, mirroring every prior round's own
     dimension-check extension.

Anchored transforms only; MARK-idempotent; a moved anchor raises loudly."""
from __future__ import annotations

MARK = "integrity-wing-d"


class PatchError(Exception):
    pass


def _replace_once(text: str, old: str, new: str, *, label: str) -> str:
    if text.count(old) != 1:
        raise PatchError(f"{label}: expected 1 anchor, found {text.count(old)}")
    return text.replace(old, new, 1)


# ── 1. proving_ground/runner.py ───────────────────────────────────────────

VERSION_ANCHOR = 'SUITE_VERSION = "v6"  # wellbeing-wing-d — v6 adds the wellbeing wing (W1-W4 machinery); stored scores keep naming the suite they scored'

VERSION_NEW = (
    f'SUITE_VERSION = "v7"  # {MARK} — v7 adds the integrity wing (I1-I4 machinery); '
    f'stored scores keep naming the suite they scored'
)


def patch_suite_version(text: str) -> tuple[str, bool]:
    # No independent MARK guard here — patch_runner() is the only caller
    # and already guards once at the top. VERSION_NEW's own comment
    # embeds MARK, so an independent guard here would falsely see MARK
    # as "already patched" the instant this step runs, before the tail
    # import step below ever gets a chance to land.
    return _replace_once(text, VERSION_ANCHOR, VERSION_NEW, label="SUITE_VERSION"), True


TAIL_ANCHOR = '''# wellbeing-wing-d — Wellbeing round W5: the wellbeing wing (persisted composite
# value/care/flourishing score, persistence at the value_report source,
# the standing audit, the measured angel lens, the reflecting stance).
from .wellbeing_wing import WELLBEING_TASKS  # noqa: E402

OFFLINE_TASKS.update(WELLBEING_TASKS)'''

TAIL_NEW = f'''# wellbeing-wing-d — Wellbeing round W5: the wellbeing wing (persisted composite
# value/care/flourishing score, persistence at the value_report source,
# the standing audit, the measured angel lens, the reflecting stance).
from .wellbeing_wing import WELLBEING_TASKS  # noqa: E402

OFFLINE_TASKS.update(WELLBEING_TASKS)

# {MARK} — Integrity round I5: the integrity wing (persisted composite
# anti-misleading score, the gate, the standing audit, the measured
# witness lens, the honest stance).
from .integrity_wing import INTEGRITY_TASKS  # noqa: E402

OFFLINE_TASKS.update(INTEGRITY_TASKS)'''


def patch_tail_import(text: str) -> tuple[str, bool]:
    # No independent MARK guard here either — see patch_suite_version's
    # note above; patch_runner() guards once, before either step runs.
    return _replace_once(text, TAIL_ANCHOR, TAIL_NEW, label="runner.py tail import"), True


def patch_runner(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    text, _ = patch_suite_version(text)
    text, changed = patch_tail_import(text)
    return text, changed


# ── 2. GOD_TIER_STANDARD.md — dimension 1's Check line ────────────────────

DOC_ANCHOR = '''1. **Honesty / grounding** — *Floor:* humility over hype; every claim grounded in evidence or marked a
   falsifiable hypothesis; no ungrounded profundity. *Check:* Tribunal grounding verdict ≠ `ungrounded`; a
   composite epistemic score is persisted standing and gates the "grounded" stance and the wonder loop's
   own confidence calibration. *Ratchet:* tighten the grounding threshold; widen what must be evidenced.'''

DOC_NEW = f'''1. **Honesty / grounding** — *Floor:* humility over hype; every claim grounded in evidence or marked a
   falsifiable hypothesis; no ungrounded profundity. *Check:* Tribunal grounding verdict ≠ `ungrounded`; a
   composite epistemic score is persisted standing and gates the "grounded" stance and the wonder loop's
   own confidence calibration. A composite anti-misleading score (text-honesty + outcome-honesty +
   proposal-honesty + refusal-honesty, `integrity/ledger.py`, {MARK}) is persisted standing and gates the
   "honest" stance. *Ratchet:* tighten the grounding threshold; widen what must be evidenced.'''


def patch_god_tier_standard(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    return _replace_once(text, DOC_ANCHOR, DOC_NEW, label="GOD_TIER_STANDARD.md dimension 1"), True


ALL_PATCHES = {
    "proving_ground/runner.py": patch_runner,
}

DOC_PATCHES = {
    "GOD_TIER_STANDARD.md": patch_god_tier_standard,
}
