"""patcher.py — anchored, idempotent text patches for loop.py and
agent_session.py (Workstream N). Pure string transforms so they're testable
against the live file text WITHOUT touching src/ — same discipline as
aria-locator-events-fix's patcher and aria-cosmic-fitness-restore's.

Both patches do the same two things to their respective file:
  1. add `effective_wall_limit` to the existing `from .modes import ...` line
  2. route the wall-seconds budget check through it instead of comparing
     directly against `budget.max_wall_seconds`
"""
from __future__ import annotations

MARK = "safe-interval-stop-d"


class PatchError(Exception):
    pass


def patch_loop(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False

    old_import = "from .modes import BudgetExceeded, Mode, RunBudget\n"
    if old_import not in text:
        raise PatchError("loop.py: modes import line not found verbatim")
    new_import = "from .modes import BudgetExceeded, Mode, RunBudget, effective_wall_limit\n"
    text = text.replace(old_import, new_import, 1)

    old_block = (
        "    elapsed = time.monotonic() - started_at\n"
        "    if elapsed >= budget.max_wall_seconds:\n"
        '        raise BudgetExceeded("wall_seconds", used=elapsed, limit=budget.max_wall_seconds)\n'
    )
    if old_block not in text:
        raise PatchError("loop.py: _check_budget wall-seconds block not found verbatim")
    new_block = (
        f"    elapsed = time.monotonic() - started_at\n"
        f"    wall_limit = effective_wall_limit(budget)  # {MARK}\n"
        f"    if elapsed >= wall_limit:\n"
        f'        raise BudgetExceeded("wall_seconds", used=elapsed, limit=wall_limit)\n'
    )
    text = text.replace(old_block, new_block, 1)
    return text, True


def patch_agent_session(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False

    old_import = "from .modes import BudgetExceeded, Mode, RunBudget\n"
    if old_import not in text:
        raise PatchError("agent_session.py: modes import line not found verbatim")
    new_import = "from .modes import BudgetExceeded, Mode, RunBudget, effective_wall_limit\n"
    text = text.replace(old_import, new_import, 1)

    old_block = (
        "    if state.started_at_monotonic is not None:\n"
        "        elapsed = time.monotonic() - state.started_at_monotonic\n"
        "        if elapsed >= budget.max_wall_seconds:\n"
        '            raise BudgetExceeded("wall_seconds", used=elapsed,\n'
        "                                 limit=budget.max_wall_seconds)\n"
    )
    if old_block not in text:
        raise PatchError("agent_session.py: _check_session_budget wall-seconds block not found verbatim")
    new_block = (
        f"    if state.started_at_monotonic is not None:\n"
        f"        elapsed = time.monotonic() - state.started_at_monotonic\n"
        f"        wall_limit = effective_wall_limit(budget)  # {MARK}\n"
        f"        if elapsed >= wall_limit:\n"
        f'            raise BudgetExceeded("wall_seconds", used=elapsed,\n'
        f"                                 limit=wall_limit)\n"
    )
    text = text.replace(old_block, new_block, 1)
    return text, True
