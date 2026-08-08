"""patcher.py — Grounding round G1: persist a composite epistemic score.

Kevin: *"a god tier grounding system... anti-hallucination, but free to
explore, dream, think, and work in grounded reasoning."* This first
workstream composes three real, already-existing subsystems (tribunal.
grounding, epistemic_ledger, curiosity's wonder loop) into one persisted,
standing pass — nothing new invented, same shape as Quality round Q1.

Patches:
  1. stewardship/__init__.py — registers GroundingSentinel, anchored right
     after the confirmed quality-sentinel-d import line.

Anchored transforms only; MARK-idempotent; a moved anchor raises loudly.
"""
from __future__ import annotations

MARK = "grounding-sentinel-d"


class PatchError(Exception):
    pass


def _replace_once(text: str, old: str, new: str, *, label: str) -> str:
    if text.count(old) != 1:
        raise PatchError(f"{label}: expected 1 anchor, found {text.count(old)}")
    return text.replace(old, new, 1)


STEWARDSHIP_INIT_ANCHOR = (
    'from sovereign_agent.stewardship import quality_sentinel as '
    '_quality_sentinel  # noqa: F401  # quality-sentinel-d'
)

STEWARDSHIP_INIT_NEW = (
    'from sovereign_agent.stewardship import quality_sentinel as '
    '_quality_sentinel  # noqa: F401  # quality-sentinel-d\n'
    'from . import grounding_sentinel as _grounding_sentinel  # noqa: F401  '
    f'# {MARK}'
)


def patch_stewardship_init(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    return _replace_once(text, STEWARDSHIP_INIT_ANCHOR, STEWARDSHIP_INIT_NEW,
                         label="stewardship __init__ sentinel registration"), True


ALL_PATCHES = {
    "stewardship/__init__.py": patch_stewardship_init,
}
