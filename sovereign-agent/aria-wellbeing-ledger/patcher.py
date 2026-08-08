"""patcher.py — Wellbeing round W1: composite value/care/flourishing score.

Kevin: *"do the same for love, flourishing, and MSIMS... whatever brings her
value, perspective, and insight into her self and her actions."* This first
workstream composes three real, already-existing subsystems
(`companion_tools.value_report`, `stewardship.msims`, `foresight.project`)
into one persisted, standing pass — same shape as Quality round Q1 and
Grounding round G1.

Patches:
  1. stewardship/__init__.py — registers WellbeingSentinel, anchored right
     after the confirmed grounding-sentinel-d import line.
  2. tools/companion_tools.py — a real bug fix: `_load_recent_events_for_
     report()` globs `events_dir/*.ndjson`, but the real, canonical event
     log (`config.py:Paths.events_jsonl`) is daily-rotated
     `events_dir/events-{day}.jsonl` — the glob has NEVER matched a single
     real event file. `value_report()` has always silently degraded to
     "no recorded high-signal events" in the live vessel. Every existing
     test mocks this function entirely, which is exactly how the bug
     survived. Fixed to the real pattern; behavior for any caller that
     already passes its own event list (every test) is unchanged.

Anchored transforms only; MARK-idempotent; a moved anchor raises loudly."""
from __future__ import annotations

MARK = "wellbeing-sentinel-d"


class PatchError(Exception):
    pass


def _replace_once(text: str, old: str, new: str, *, label: str) -> str:
    if text.count(old) != 1:
        raise PatchError(f"{label}: expected 1 anchor, found {text.count(old)}")
    return text.replace(old, new, 1)


# ── 1. stewardship/__init__.py ────────────────────────────────────────────

STEWARDSHIP_INIT_ANCHOR = (
    'from . import grounding_sentinel as _grounding_sentinel  # noqa: F401  '
    '# grounding-sentinel-d'
)

STEWARDSHIP_INIT_NEW = (
    'from . import grounding_sentinel as _grounding_sentinel  # noqa: F401  '
    '# grounding-sentinel-d\n'
    'from . import wellbeing_sentinel as _wellbeing_sentinel  # noqa: F401  '
    f'# {MARK}'
)


def patch_stewardship_init(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    return _replace_once(text, STEWARDSHIP_INIT_ANCHOR, STEWARDSHIP_INIT_NEW,
                         label="stewardship __init__ sentinel registration"), True


# ── 2. tools/companion_tools.py — the dormant glob bug, fixed ─────────────

EVENTS_GLOB_ANCHOR = '''        if not events_dir.exists():
            return events
        for f in sorted(events_dir.glob("*.ndjson"))[-3:]:'''

EVENTS_GLOB_NEW = f'''        if not events_dir.exists():
            return events
        # {MARK} — the real, canonical event log is daily-rotated
        # `events-{{day}}.jsonl` (config.py:Paths.events_jsonl), never
        # `*.ndjson` — this glob has never matched a real event file, so
        # value_report() has always silently scored an empty session in
        # the live vessel. Every existing test mocks this function
        # entirely, which is exactly how the bug survived undetected.
        for f in sorted(events_dir.glob("events-*.jsonl"))[-3:]:'''


def patch_companion_tools(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    return _replace_once(text, EVENTS_GLOB_ANCHOR, EVENTS_GLOB_NEW,
                         label="companion_tools events glob bug fix"), True


ALL_PATCHES = {
    "stewardship/__init__.py": patch_stewardship_init,
    "tools/companion_tools.py": patch_companion_tools,
}
