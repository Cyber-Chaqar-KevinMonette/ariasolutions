"""patcher.py — Fable F1: register the LooseThreadsSentinel."""
from __future__ import annotations

MARK = "loose-threads-d"


class PatchError(Exception):
    pass


def _replace_once(text, old, new, *, label):
    if text.count(old) != 1:
        raise PatchError(f"{label}: expected 1, found {text.count(old)}")
    return text.replace(old, new, 1)


INIT_ANCHOR = "from . import backup_sentinel as _backup_sentinel  # noqa: F401  # auto-backup-d\n"
INIT_NEW = (
    INIT_ANCHOR
    + f"from sovereign_agent.loose_threads import sentinel as _loose_threads  # noqa: F401  # {MARK}\n"
)


def patch_stewardship_init(text):
    if MARK in text:
        return text, False
    return _replace_once(text, INIT_ANCHOR, INIT_NEW, label="init anchor"), True
