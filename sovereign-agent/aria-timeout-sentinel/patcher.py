"""patcher.py — Timeout round T3: standing sentinel registration.

Patches stewardship/__init__.py — anchored on the current tail
(self_integrity_sentinel, the Integrity round's own addition).
"""
from __future__ import annotations

MARK = "timeout-sentinel-d"


class PatchError(Exception):
    pass


def _replace_once(text: str, old: str, new: str, *, label: str) -> str:
    if text.count(old) != 1:
        raise PatchError(f"{label}: expected 1 anchor, found {text.count(old)}")
    return text.replace(old, new, 1)


INIT_ANCHOR = (
    "from . import self_integrity_sentinel as _self_integrity_sentinel  "
    "# noqa: F401  # self-integrity-sentinel-d\n"
)

INIT_NEW = (
    INIT_ANCHOR
    + f"from . import timeout_sentinel as _timeout_sentinel  # noqa: F401  # {MARK}\n"
)


def patch_stewardship_init(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    return _replace_once(text, INIT_ANCHOR, INIT_NEW, label="stewardship init"), True


ALL_PATCHES = {
    "stewardship/__init__.py": patch_stewardship_init,
}
