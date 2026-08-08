"""patcher.py — People-Health round PH3: retrieval privacy + registration
+ doctor sync.

Patches:
  1. mem_channels/__init__.py — add `people_health` to the registration
     import list. Without this, PeopleHealthChannel's @register_channel
     never fires at real app startup — only in tests that import the
     module directly. A real gap PH2 left open; closed here.
  2. retrieval/filter.py's _PRIVATE_CHANNELS — add "people_health"
     alongside "people"/"relationships" (health data is at least as
     sensitive as the PII those two already gate).
  3. doctor.py's expected channel set — add "people_health" so `sov
     doctor`'s channel-count check stays accurate.

Anchored transforms only; MARK-idempotent; a moved anchor raises loudly."""
from __future__ import annotations

MARK = "people-health-privacy-d"


class PatchError(Exception):
    pass


def _replace_once(text: str, old: str, new: str, *, label: str) -> str:
    if text.count(old) != 1:
        raise PatchError(f"{label}: expected 1 anchor, found {text.count(old)}")
    return text.replace(old, new, 1)


# ── 1. mem_channels/__init__.py — register the channel at import time ────

CHANNELS_IMPORT_ANCHOR = '''from . import (
    commitments,
    context,
    emotions,
    episodes,
    financial,
    gaps,
    goals,
    heartbeat,
    humor,
    identity,
    insights,
    intention,
    intuition,
    lessons,
    people,
    personalities,
    reasoning,
    recall,
    relationships,
    reward,
    ritual,
    specialist,
    task,
    trust,
)'''

CHANNELS_IMPORT_NEW = f'''from . import (
    commitments,
    context,
    emotions,
    episodes,
    financial,
    gaps,
    goals,
    heartbeat,
    humor,
    identity,
    insights,
    intention,
    intuition,
    lessons,
    people,
    people_health,  # {MARK}
    personalities,
    reasoning,
    recall,
    relationships,
    reward,
    ritual,
    specialist,
    task,
    trust,
)'''


def patch_channels_init(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    return _replace_once(text, CHANNELS_IMPORT_ANCHOR, CHANNELS_IMPORT_NEW,
                         label="mem_channels/__init__.py import list"), True


# ── 2. retrieval/filter.py — add to the private-channel exclusion set ────

FILTER_ANCHOR = '_PRIVATE_CHANNELS = frozenset({"people", "relationships"})'

FILTER_NEW = f'_PRIVATE_CHANNELS = frozenset({{"people", "relationships", "people_health"}})  # {MARK}'


def patch_retrieval_filter(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    return _replace_once(text, FILTER_ANCHOR, FILTER_NEW, label="retrieval/filter.py"), True


# ── 3. doctor.py — the expected channel set ───────────────────────────────

DOCTOR_ANCHOR = '''    expected_v0218 = {
        "context", "emotions", "episodes", "financial", "goals", "humor",
        "identity", "insights", "intention", "intuition", "lessons",
        "people", "personalities", "recall", "reward", "ritual",
        "specialist", "task", "trust",
        # v0.2.18 additions:
        "reasoning", "gaps", "relationships", "commitments", "heartbeat",
    }'''

DOCTOR_NEW = f'''    expected_v0218 = {{
        "context", "emotions", "episodes", "financial", "goals", "humor",
        "identity", "insights", "intention", "intuition", "lessons",
        "people", "personalities", "recall", "reward", "ritual",
        "specialist", "task", "trust",
        # v0.2.18 additions:
        "reasoning", "gaps", "relationships", "commitments", "heartbeat",
        # {MARK}:
        "people_health",
    }}'''


def patch_doctor(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    return _replace_once(text, DOCTOR_ANCHOR, DOCTOR_NEW, label="doctor.py expected_v0218"), True


ALL_PATCHES = {
    "mem_channels/__init__.py": patch_channels_init,
    "retrieval/filter.py": patch_retrieval_filter,
    "doctor.py": patch_doctor,
}
