"""patcher.py — Timeout round T4: proving wing wiring.

Patches proving_ground/runner.py — SUITE_VERSION v7 -> v8, tail-import of
TIMEOUT_TASKS folded into OFFLINE_TASKS.

A single top-level MARK guard covers BOTH edits (the version-bump
comment embeds MARK itself) — a lesson learned the hard way in the
Integrity round's own I5 patcher: two independently-guarded sub-steps
where the first step's own inserted text contains the MARK causes the
second step's guard to falsely fire as "already patched," silently
discarding the whole patch. `patch_runner()` is the ONLY guarded entry
point; the two sub-functions below are unguarded helpers, called only
from here.
"""
from __future__ import annotations

MARK = "timeout-wing-d"


class PatchError(Exception):
    pass


def _replace_once(text: str, old: str, new: str, *, label: str) -> str:
    if text.count(old) != 1:
        raise PatchError(f"{label}: expected 1 anchor, found {text.count(old)}")
    return text.replace(old, new, 1)


VERSION_ANCHOR = (
    'SUITE_VERSION = "v7"  # integrity-wing-d — v7 adds the integrity wing '
    '(I1-I4 machinery); stored scores keep naming the suite they scored'
)

VERSION_NEW = (
    f'SUITE_VERSION = "v8"  # {MARK} — v8 adds the timeout wing (T1-T3 machinery); '
    f'stored scores keep naming the suite they scored'
)


def _patch_suite_version(text: str) -> str:
    return _replace_once(text, VERSION_ANCHOR, VERSION_NEW, label="SUITE_VERSION")


TAIL_ANCHOR = '''# integrity-wing-d — Integrity round I5: the integrity wing (persisted composite
# anti-misleading score, the gate, the standing audit, the measured
# witness lens, the honest stance).
from .integrity_wing import INTEGRITY_TASKS  # noqa: E402

OFFLINE_TASKS.update(INTEGRITY_TASKS)'''

TAIL_NEW = f'''# integrity-wing-d — Integrity round I5: the integrity wing (persisted composite
# anti-misleading score, the gate, the standing audit, the measured
# witness lens, the honest stance).
from .integrity_wing import INTEGRITY_TASKS  # noqa: E402

OFFLINE_TASKS.update(INTEGRITY_TASKS)

# {MARK} — Timeout round T4: the timeout wing (persisted justified/
# unexplained classification, the recurring-hang gate, the standing
# audit).
from .timeout_wing import TIMEOUT_TASKS  # noqa: E402

OFFLINE_TASKS.update(TIMEOUT_TASKS)'''


def _patch_tail_import(text: str) -> str:
    return _replace_once(text, TAIL_ANCHOR, TAIL_NEW, label="runner.py tail import")


def patch_runner(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    text = _patch_suite_version(text)
    text = _patch_tail_import(text)
    return text, True


ALL_PATCHES = {
    "proving_ground/runner.py": patch_runner,
}
