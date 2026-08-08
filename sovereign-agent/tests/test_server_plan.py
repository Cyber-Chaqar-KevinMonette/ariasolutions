"""Tests for server_plan — snapshot, audit vs blueprint, evolution detection."""
from __future__ import annotations

import json

from sovereign_agent.discord_admin.blueprint import (
    ChannelSpec,
    RoleSpec,
    ServerBlueprint,
    shop_blueprint,
)
from sovereign_agent.discord_admin.server_plan import (
    audit_snapshot,
    blueprint_fingerprint,
    check_plan_evolution,
    load_snapshot,
    render_audit,
    save_snapshot,
)


def _full_server(bp=None):
    """role/category/channel names exactly matching the blueprint."""
    bp = bp or shop_blueprint()
    return (bp.role_names(), [c.name for c in bp.categories],
            bp.channel_names())


# ── snapshot store ───────────────────────────────────────────────────────────
def test_snapshot_round_trip(tmp_path):
    save_snapshot(tmp_path, roles=["Aria", "VIP"], categories=["SHOP"],
                  channels=["storefront"], guild_name="BigKevs-Bot-Shop",
                  now=1000.0)
    snap = load_snapshot(tmp_path)
    assert snap is not None and snap.guild_name == "BigKevs-Bot-Shop"
    assert snap.roles == ["Aria", "VIP"] and snap.captured_at == 1000.0


def test_snapshot_corruption_degrades_to_none(tmp_path):
    (tmp_path / "discord_admin").mkdir(parents=True)
    (tmp_path / "discord_admin" / "server_snapshot.json").write_text("{broken")
    assert load_snapshot(tmp_path) is None


# ── the audit ────────────────────────────────────────────────────────────────
def test_complete_server_audits_complete(tmp_path):
    roles, cats, chans = _full_server()
    snap = save_snapshot(tmp_path, roles=roles + ["@everyone"],
                         categories=cats, channels=chans, now=1000.0)
    a = audit_snapshot(snap, now=1010.0)
    assert a.complete and a.coverage == 1.0 and a.missing_total == 0
    assert "@everyone" not in a.extra_roles         # house role never "extra"
    assert "✅ COMPLETE" in render_audit(a)


def test_missing_items_are_named_specifically(tmp_path):
    roles, cats, chans = _full_server()
    chans = [c for c in chans if c not in ("ask-aria", "welcome")]
    roles = [r for r in roles if r != "Veteran"]
    snap = save_snapshot(tmp_path, roles=roles, categories=cats,
                         channels=chans, now=1000.0)
    a = audit_snapshot(snap, now=1010.0)
    assert not a.complete and a.missing_total == 3
    assert a.missing_channels == ["ask-aria", "welcome"]
    assert a.missing_roles == ["Veteran"]
    out = render_audit(a)
    assert "+ channel: ask-aria" in out and "+ role: Veteran" in out
    assert "/setup-shop" in out                     # tells you the fix


def test_extra_items_are_reported_never_threatened(tmp_path):
    roles, cats, chans = _full_server()
    snap = save_snapshot(tmp_path, roles=roles,
                         categories=cats + ["KEVIN-LAB"],
                         channels=chans + ["memes"], now=1000.0)
    a = audit_snapshot(snap, now=1010.0)
    assert a.complete                               # extras don't hurt coverage
    assert a.extra_categories == ["KEVIN-LAB"] and a.extra_channels == ["memes"]
    out = render_audit(a)
    assert "never touched" in out and "memes" in out


# ── fingerprint + evolution detection ────────────────────────────────────────
def test_fingerprint_stable_and_sensitive():
    assert blueprint_fingerprint() == blueprint_fingerprint()
    grown = shop_blueprint()
    grown.categories[0].channels.append(ChannelSpec("mod-log"))
    assert blueprint_fingerprint(grown) != blueprint_fingerprint()
    # permission-intent changes count as evolution too
    perms = shop_blueprint()
    perms.categories[0].channels[0].allow_send_everyone = True
    assert blueprint_fingerprint(perms) != blueprint_fingerprint()


def test_evolution_announced_exactly_once_per_change(tmp_path):
    # first sighting ever: baseline quietly recorded, no announcement
    assert check_plan_evolution(tmp_path) is None
    assert check_plan_evolution(tmp_path) is None       # unchanged → quiet
    grown = ServerBlueprint(roles=[RoleSpec("Aria")], categories=[])
    note = check_plan_evolution(tmp_path, grown)        # changed → announce
    assert note is not None and "EVOLVED" in note
    assert check_plan_evolution(tmp_path, grown) is None  # once, not nagging
    # and switching back is itself a change (any drift is surfaced)
    assert check_plan_evolution(tmp_path) is not None


def test_evolution_state_survives_corruption(tmp_path):
    (tmp_path / "discord_admin").mkdir(parents=True)
    (tmp_path / "discord_admin" / "plan_state.json").write_text("not json")
    assert check_plan_evolution(tmp_path) is None       # recovers as baseline
    state = json.loads(
        (tmp_path / "discord_admin" / "plan_state.json").read_text())
    assert state["blueprint_fingerprint"] == blueprint_fingerprint()


# ── decoration tolerance (Kevin's real server: "🛒 SHOP", "📢 WELCOME") ──────
def test_decorated_names_are_never_drift(tmp_path):
    from sovereign_agent.discord_admin.blueprint import canon_name
    assert canon_name("🛒 SHOP") == canon_name("SHOP")
    assert canon_name("📢 WELCOME") == canon_name("Welcome")
    assert canon_name("order-here") == canon_name("order_here")
    assert canon_name("🔧 BACKEND") != canon_name("SHOP")   # real difference stays

    bp = shop_blueprint()
    roles, _, chans = _full_server(bp)
    decorated_cats = [f"🛒 {c.name}" if c.name == "SHOP" else f"✨ {c.name}"
                      for c in bp.categories]
    snap = save_snapshot(tmp_path, roles=roles, categories=decorated_cats,
                         channels=chans, now=1000.0)
    a = audit_snapshot(snap, now=1010.0)
    assert a.complete and a.coverage == 1.0          # decorated == present
    assert a.extra_categories == []                  # and NOT counted as extra


def test_planner_skips_decorated_existing_categories():
    from sovereign_agent.discord_admin.planner import CurrentState, plan
    bp = shop_blueprint()
    current = CurrentState(
        roles=set(bp.role_names()),
        categories={f"🛒 {c.name}" for c in bp.categories},
        channels=set(bp.channel_names()) - {"ask-aria"})
    actions = plan(bp, current)
    creates = [a for a in actions if a.op.startswith("create")]
    # ONLY the genuinely-missing channel — no duplicate plain categories
    assert [(a.op, a.name) for a in creates] == [("create_channel", "ask-aria")]


# ── consolidation view (N2) ─────────────────────────────────────────────────
def test_render_orphans_lists_everything_and_gates_deletion(tmp_path):
    """consolidation-d: the orphan worksheet names EVERY extra item, tells
    the owner the exact typed phrase, and promises roles are never touched."""
    from sovereign_agent.discord_admin.server_plan import (
        CLEANUP_CONFIRM_PHRASE, render_orphans)
    roles, cats, chans = _full_server()
    snap = save_snapshot(
        tmp_path, roles=roles + ["Cool-Kids"],
        categories=cats + ["OLD STUFF"],
        channels=chans + ["track-consoles", "track-freegames", "random-chat"],
        guild_name="BigKevs-Bot-Shop", now=1000.0)
    out = render_orphans(audit_snapshot(snap, now=1000.0))
    for orphan in ("#track-consoles", "#track-freegames", "#random-chat",
                   "OLD STUFF", "Cool-Kids"):
        assert orphan in out, f"{orphan} missing from the worksheet"
    assert CLEANUP_CONFIRM_PHRASE in out          # the typed gate is taught
    assert "NEVER deleted" in out                  # roles promise, verbatim


def test_render_orphans_clean_server_celebrates(tmp_path):
    from sovereign_agent.discord_admin.server_plan import render_orphans
    roles, cats, chans = _full_server()
    snap = save_snapshot(tmp_path, roles=roles, categories=cats,
                         channels=chans, guild_name="x", now=1000.0)
    out = render_orphans(audit_snapshot(snap, now=1000.0))
    assert "CLEAN" in out and "DELETE ORPHANS" not in out
