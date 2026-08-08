"""patcher.py — FABLE II M4: the proving ground grows a memory wing.

Suite membership changes ⇒ SUITE_VERSION bumps (v1 → v2): every stored
score references the suite it scored — the M1 `proving-suite` join.
Anchored transforms only; MARK-idempotent; a moved anchor raises loudly."""
from __future__ import annotations

MARK = "memory-proof-d"


class PatchError(Exception):
    pass


def _replace_once(text: str, old: str, new: str, *, label: str) -> str:
    if text.count(old) != 1:
        raise PatchError(f"{label}: expected 1 anchor, found {text.count(old)}")
    return text.replace(old, new, 1)


VERSION_ANCHOR = 'SUITE_VERSION = "v1"\n'
VERSION_NEW = (f'SUITE_VERSION = "v2"  # {MARK} — v2 adds the memory wing '
               f'(5 tasks); stored scores keep naming the suite they scored\n')

TASKS_ANCHOR = """OFFLINE_TASKS = {
    "paging-round-trip": _task_paging_round_trip,
    "authority-refusal": _task_authority_refusal,
    "scope-hold": _task_scope_hold,
    "garden-wall": _task_garden_wall,
    "thread-recall": _task_thread_recall,
    "rest-bookmark": _task_rest_resume_bookmark,
}
"""

TASKS_NEW = TASKS_ANCHOR + f"""
# {MARK} — FABLE II M4: the memory wing (cross-restart recall, lesson
# round-trip, journal once-only, one-truth clean, compaction recall).
from .memory_wing import MEMORY_TASKS  # noqa: E402

OFFLINE_TASKS.update(MEMORY_TASKS)
"""


def patch_runner(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    text = _replace_once(text, VERSION_ANCHOR, VERSION_NEW, label="suite version")
    text = _replace_once(text, TASKS_ANCHOR, TASKS_NEW, label="offline tasks")
    return text, True
