"""Tests for discord_admin.reorder — blueprint order applied to a live guild."""
from __future__ import annotations

from sovereign_agent.discord_admin.reorder import describe_moves, plan_positions


def _apply(live, moves):
    """Simulate Discord: apply each (name, pos) by removing and reinserting."""
    out = list(live)
    for name, pos in moves:
        out.remove(name)
        out.insert(pos, name)
    return out


def test_already_ordered_is_a_no_op():
    live = ["ADMIN", "WELCOME", "SHOP"]
    assert plan_positions(live, live) == []


def test_reverses_an_inverted_server():
    desired = ["ADMIN", "BACKEND", "WELCOME"]
    live = ["WELCOME", "BACKEND", "ADMIN"]
    assert _apply(live, plan_positions(desired, live)) == desired


def test_matches_through_emoji_decoration():
    """Kevin decorates his real categories — comparing raw strings would
    call every one of them unknown and reorder nothing."""
    desired = ["ADMIN", "WELCOME", "SHOP"]
    live = ["🛒 SHOP", "📢 WELCOME", "🔒 ADMIN"]
    moves = plan_positions(desired, live)
    assert _apply(live, moves) == ["🔒 ADMIN", "📢 WELCOME", "🛒 SHOP"]


def test_unknown_categories_sink_to_the_bottom_in_their_own_order():
    """A category the blueprint doesn't know about must keep its relative
    place, not get scattered — reordering is not a way to hide channels."""
    desired = ["ADMIN", "WELCOME"]
    live = ["MYSTERY-A", "WELCOME", "MYSTERY-B", "ADMIN"]
    result = _apply(live, plan_positions(desired, live))
    assert result[:2] == ["ADMIN", "WELCOME"]
    assert result[2:] == ["MYSTERY-A", "MYSTERY-B"]      # relative order kept


def test_blueprint_entries_missing_from_the_guild_are_skipped():
    desired = ["ADMIN", "GHOST", "WELCOME"]
    live = ["WELCOME", "ADMIN"]
    assert _apply(live, plan_positions(desired, live)) == ["ADMIN", "WELCOME"]


def test_partial_disorder_still_lands_exactly():
    """Positions are absolute and each edit shifts what follows, so the
    full order is emitted rather than a 'minimal' list computed against
    stale indices — that only gets the first move right."""
    desired = ["A", "B", "C", "D"]
    live = ["A", "B", "D", "C"]
    assert _apply(live, plan_positions(desired, live)) == desired


def test_an_ordered_server_costs_nothing():
    desired = ["A", "B", "C"]
    assert plan_positions(desired, list(desired)) == []


def test_empty_inputs_are_safe():
    assert plan_positions([], []) == []
    assert plan_positions(["A"], []) == []
    assert plan_positions([], ["A"]) == []


def test_the_real_blueprint_order_applies_cleanly():
    """End-to-end against the actual shop blueprint, scrambled."""
    from sovereign_agent.discord_admin.blueprint import shop_blueprint
    desired = [c.name for c in shop_blueprint().categories]
    live = list(reversed(desired))
    assert _apply(live, plan_positions(desired, live)) == desired


def test_describe_is_honest_about_a_no_op():
    assert "already in blueprint order" in describe_moves([])
    assert "2 category(s)" in describe_moves([("A", 0), ("B", 1)])


# ── re-homing: channels stranded in a retired category ─────────────────
from sovereign_agent.discord_admin.reorder import plan_rehome  # noqa: E402


def test_rehomes_channels_left_behind_by_a_merge():
    """The real case: BACKEND/COMMAND folded into ADMIN, but their channels
    stayed put — which is exactly what blocked those categories from being
    deleted."""
    bp = {"owner-bridge": "ADMIN", "mod-log": "ADMIN", "order-here": "SHOP"}
    live = {"owner-bridge": "COMMAND", "mod-log": "BACKEND",
            "order-here": "ORDERS"}
    assert sorted(plan_rehome(bp, live)) == [
        ("mod-log", "ADMIN"), ("order-here", "SHOP"),
        ("owner-bridge", "ADMIN")]


def test_channels_already_home_are_left_alone():
    bp = {"tasks": "ADMIN"}
    assert plan_rehome(bp, {"tasks": "ADMIN"}) == []


def test_matches_through_category_decoration():
    """#order-here sitting in "🛒 SHOP" is already home — decoration is
    cosmetic, and moving it would be a pointless API call."""
    assert plan_rehome({"order-here": "SHOP"}, {"order-here": "🛒 SHOP"}) == []


def test_unknown_channels_are_never_adopted():
    """A channel the blueprint doesn't know stays exactly where it is —
    re-homing must not hoover up somebody else's channel."""
    assert plan_rehome({"tasks": "ADMIN"}, {"random-chat": "SOMEWHERE"}) == []


def test_missing_channels_are_left_for_setup_shop():
    """Not yet created is a create job, not a move job."""
    assert plan_rehome({"brand-new": "ADMIN"}, {}) == []
