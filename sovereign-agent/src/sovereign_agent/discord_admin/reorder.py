"""reorder — put the live server in blueprint order.

reorder-d (Kevin, 2026-08-03): "build the command to reorder."

The planner (`planner.plan`) is deliberately CREATE-ONLY — it never deletes
and never moves, which is what makes `/setup-shop` safe to run blind. The
cost of that safety showed up the moment the blueprint was reorganised:
Discord keeps existing categories wherever they already sit, so a rewritten
`shop_blueprint()` changed nothing on screen. This module is the missing,
explicitly-invoked other half.

Pure: `plan_positions` is data → data, so the ordering rules are testable
without a gateway. The bot applies the returned moves.

Two rules that matter:
  • Match on `canon_name`, not the raw string. Kevin decorates his real
    categories ("🛒 SHOP", "📢 WELCOME"); comparing raw names would call
    every one of them missing and reorder nothing.
  • Only reposition what BOTH sides know about. A category living in the
    guild but absent from the blueprint keeps its relative place at the
    bottom rather than being yanked somewhere arbitrary — reordering must
    never be a disguised way to hide someone's channel.
"""
from __future__ import annotations

from .blueprint import canon_name

__all__ = ["plan_positions", "describe_moves"]


def plan_positions(desired: list[str], live: list[str]) -> list[tuple[str, int]]:
    """[(live_name, target_position)] for everything that must move.

    `desired` is blueprint order; `live` is the guild's current order. Names
    present only in `live` are appended after the known ones, keeping their
    existing relative order — unknown things drift to the bottom, they never
    get scattered.

    An already-ordered server returns [] — the command is then a genuine
    no-op costing zero API calls.

    When anything IS out of place the FULL order is emitted, not just the
    items that differ. Positions are absolute and each edit shifts every
    item after it, so a "minimal" list computed against the original indices
    is only correct for the first move — the rest silently land wrong. This
    was caught by test_the_real_blueprint_order_applies_cleanly. Emitting
    every position costs N calls on a handful of categories and is correct
    by construction, which is the right trade here.
    """
    want = [canon_name(n) for n in desired]
    live_canon = [canon_name(n) for n in live]

    # blueprint order first (only those that actually exist), then the
    # strangers in the order the guild already had them
    known = [n for n in want if n in live_canon]
    unknown = [n for n in live_canon if n not in want]
    target_order = known + unknown

    if target_order == live_canon:
        return []
    by_canon = {canon_name(n): n for n in live}
    return [(by_canon[c], pos) for pos, c in enumerate(target_order)]


def plan_rehome(blueprint_homes: dict[str, str],
                live_homes: dict[str, str]) -> list[tuple[str, str]]:
    """[(channel_name, target_category)] for channels in the wrong category.

    rehome-d (Kevin, 2026-08-04): "the vehicles and command categories will
    not delete after two tries." They weren't deletable. Consolidating
    BACKEND/STATUS/COMMAND into ADMIN left their CHANNELS behind —
    #owner-bridge, #aria-control, #mod-log and friends were still sitting
    in the old categories. Those channels are not orphans (the blueprint
    still wants them, just somewhere else), so `/cleanup-orphans` correctly
    refuses to delete them, which leaves the old category non-empty, which
    means the category never gets removed either. `/setup-shop` can't help:
    it creates by name, sees the name already exists, and skips.

    Moving the channel is the only operation that resolves it, and neither
    existing command could do it.

    `blueprint_homes` and `live_homes` are both {channel_name: category}.
    Channels the blueprint doesn't know are left exactly where they are —
    re-homing must never adopt somebody else's channel.
    """
    live_canon_to_cat = {canon_name(ch): cat for ch, cat in live_homes.items()}
    moves: list[tuple[str, str]] = []
    for ch, want_cat in blueprint_homes.items():
        cur = live_canon_to_cat.get(canon_name(ch))
        if cur is None:
            continue                       # doesn't exist yet — /setup-shop's job
        if canon_name(cur) != canon_name(want_cat):
            moves.append((ch, want_cat))
    return moves


def describe_moves(moves: list[tuple[str, int]], *, kind: str = "category") -> str:
    if not moves:
        return f"✅ every {kind} is already in blueprint order — nothing to do."
    lines = [f"↕ {len(moves)} {kind}(s) to move:"]
    lines += [f"   {name} → position {pos}" for name, pos in moves[:20]]
    if len(moves) > 20:
        lines.append(f"   …and {len(moves) - 20} more")
    return "\n".join(lines)
