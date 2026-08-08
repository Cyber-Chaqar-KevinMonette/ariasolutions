"""patcher.py — Quality round Q5: proving-ground wing + round close-out.

The stick before any tuning, for the Q1-Q4 machinery: five real, scored
tasks wired into the proving ground's own offline suite.

Patches:
  1. proving_ground/runner.py — SUITE_VERSION v3 → v4, and the same
     tail-import pattern trust_wing.py already uses.
  2. GOD_TIER_STANDARD.md line 34's Quality floor text — the check now
     names the persisted score and the gate, not just "tests pass".
  3. scripts/lib/god_tier_floor.json's "quality" entry — same words.

Anchored transforms only; MARK-idempotent; a moved anchor raises loudly."""
from __future__ import annotations

MARK = "quality-tribunal-d"


class PatchError(Exception):
    pass


def _replace_once(text: str, old: str, new: str, *, label: str) -> str:
    if text.count(old) != 1:
        raise PatchError(f"{label}: expected 1 anchor, found {text.count(old)}")
    return text.replace(old, new, 1)


# ── 1. proving_ground/runner.py ──────────────────────────────────────────

VERSION_ANCHOR = (
    'SUITE_VERSION = "v3"  # graduated-trust-d — v3 adds the graduated-trust '
    'wing (hold-and-continue); stored scores keep naming the suite they scored'
)

VERSION_NEW = (
    'SUITE_VERSION = "v4"  # quality-tribunal-d — v4 adds the quality wing '
    '(Q1-Q4 machinery); stored scores keep naming the suite they scored'
)

TAIL_ANCHOR = '''# graduated-trust-d — FABLE II M7: the graduated-trust wing (hold-and-continue: five
# T1s complete, one T2 holds — no full-session stop).
from .trust_wing import TRUST_TASKS  # noqa: E402

OFFLINE_TASKS.update(TRUST_TASKS)
'''

TAIL_NEW = f'''# graduated-trust-d — FABLE II M7: the graduated-trust wing (hold-and-continue: five
# T1s complete, one T2 holds — no full-session stop).
from .trust_wing import TRUST_TASKS  # noqa: E402

OFFLINE_TASKS.update(TRUST_TASKS)

# {MARK} — Quality round Q5: the quality wing (hardening persistence, the
# gate, the fixed log_to_diagnosis, the measured artisan lens, the
# quality-pass stance's real tooth).
from .quality_wing import QUALITY_TASKS  # noqa: E402

OFFLINE_TASKS.update(QUALITY_TASKS)
'''


def patch_runner(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    text = _replace_once(text, VERSION_ANCHOR, VERSION_NEW, label="SUITE_VERSION")
    text = _replace_once(text, TAIL_ANCHOR, TAIL_NEW, label="offline-suite tail import")
    return text, True


# ── 2. GOD_TIER_STANDARD.md ──────────────────────────────────────────────

STANDARD_ANCHOR = (
    '6. **Quality** — *Floor:* tests green; the smallest reversible step; clarity over cleverness. *Check:*\n'
    '   module tests pass; `verify_module` passes. *Ratchet:* add behavior tests that prove it WORKS, not just\n'
    '   imports.'
)

STANDARD_NEW = (
    '6. **Quality** — *Floor:* tests green; the smallest reversible step; clarity over cleverness. *Check:*\n'
    '   module tests pass; `verify_module` passes; a hardening/test quality score is persisted and gates apply.\n'
    '   *Ratchet:* add behavior tests that prove it WORKS, not just imports.'
)


def patch_standard(text: str) -> tuple[str, bool]:
    if "a hardening/test quality score is persisted and gates" in text:
        return text, False
    return _replace_once(text, STANDARD_ANCHOR, STANDARD_NEW,
                         label="GOD_TIER_STANDARD quality floor"), True


# ── 3. scripts/lib/god_tier_floor.json ───────────────────────────────────

FLOOR_JSON_ANCHOR = '''    {
      "id": "quality",
      "floor": "Tests green. The smallest reversible step. Clarity over cleverness.",
      "check": "module tests pass; verify_module passes",
      "ratchet": "raise by adding behavior tests (prove it WORKS, not just imports)"
    },'''

FLOOR_JSON_NEW = '''    {
      "id": "quality",
      "floor": "Tests green. The smallest reversible step. Clarity over cleverness.",
      "check": "module tests pass; verify_module passes; a hardening/test quality score is persisted and gates apply.",
      "ratchet": "raise by adding behavior tests (prove it WORKS, not just imports)"
    },'''


def patch_floor_json(text: str) -> tuple[str, bool]:
    if "a hardening/test quality score is persisted and gates apply." in text:
        return text, False
    return _replace_once(text, FLOOR_JSON_ANCHOR, FLOOR_JSON_NEW,
                         label="god_tier_floor.json quality entry"), True


ALL_PATCHES = {
    "proving_ground/runner.py": patch_runner,
}

DOC_PATCHES = {
    "GOD_TIER_STANDARD.md": patch_standard,
}

FLOOR_JSON_PATCHES = {
    "lib/god_tier_floor.json": patch_floor_json,
}
